"""Worker de descarga a MP3 y gestión de la cola con progreso en vivo.

Un único hilo daemon procesa la cola secuencialmente. El progreso del ítem en
curso se mantiene en memoria (``PROGRESO_ACTIVO``) y se difunde por SSE; la cola
persistente vive en ``db``. Reutiliza la configuración de yt-dlp del CLI: mejor
audio, extracción a MP3 con bitrate fijo, metadatos y carátula incrustados.
"""

from __future__ import annotations

import threading
from pathlib import Path

from .. import db, ffmpeg, sse
from ..paths import CARPETA_DESCARGAS, rel_descargas, resolver_dentro_descargas
from ..utils import ahora_iso, colapsar_error

import yt_dlp
from yt_dlp.utils import DownloadError

# Progreso vivo del ítem que se está descargando: {id: progreso_float_0_100}.
PROGRESO_ACTIVO: dict[str, float] = {}
_LOCK_PROGRESO = threading.Lock()

# Control del worker: un único hilo daemon procesa la cola.
_HILO_WORKER: threading.Thread | None = None
_LOCK_WORKER = threading.Lock()


# --------------------------------------------------------------------------- #
# Cola con progreso (mezcla la BD con el progreso vivo)
# --------------------------------------------------------------------------- #

def listar_cola_con_progreso() -> list[dict]:
    """Devuelve la cola de ``db`` con el campo 'progreso' vivo mezclado."""
    items = db.cola_listar()
    with _LOCK_PROGRESO:
        progreso = dict(PROGRESO_ACTIVO)
    for item in items:
        vivo = progreso.get(item.get("id", ""))
        if vivo is not None:
            item["progreso"] = float(vivo)
        else:
            item["progreso"] = float(item.get("progreso", 0.0) or 0.0)
    return items


def emitir_cola_actualizada() -> None:
    """Emite el evento ``cola_actualizada`` con la cola actual (progreso vivo)."""
    sse.emitir({"tipo": "cola_actualizada", "items": listar_cola_con_progreso()})


def bitrate_por_defecto() -> str:
    """Bitrate configurado por el usuario, o '320' por defecto."""
    return db.config_obtener("bitrate_por_defecto", "320") or "320"


# --------------------------------------------------------------------------- #
# Opciones de yt-dlp y resolución del fichero resultante
# --------------------------------------------------------------------------- #

def _construir_opciones_descarga(carpeta_rel: str, bitrate: str, hook) -> dict:
    """Construye las opciones de yt-dlp para descargar un ítem a MP3."""
    destino = CARPETA_DESCARGAS
    carpeta_rel = (carpeta_rel or "").strip().replace("\\", "/").strip("/")
    if carpeta_rel:
        validado = resolver_dentro_descargas(carpeta_rel)
        destino = validado if validado is not None else CARPETA_DESCARGAS
    destino.mkdir(parents=True, exist_ok=True)

    opciones: dict = {
        "format": "bestaudio/best",
        "outtmpl": str(destino / "%(title)s.%(ext)s"),
        "writethumbnail": True,
        "ignoreerrors": False,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "postprocessors": [
            # 1) Extrae el audio y lo convierte a MP3 con bitrate fijo (CBR).
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(bitrate or "320"),
            },
            # 2) Escribe los metadatos (título, artista, etc.) en el MP3.
            {"key": "FFmpegMetadata", "add_metadata": True},
            # 3) Incrusta la carátula (convierte la miniatura si hace falta).
            {"key": "EmbedThumbnail", "already_have_thumbnail": False},
        ],
    }
    ffmpeg_loc = ffmpeg.localizacion()
    if ffmpeg_loc is not None:
        opciones["ffmpeg_location"] = str(ffmpeg_loc)
    return opciones


def _resolver_mp3_resultante(info_dict: dict, carpeta_rel: str) -> str:
    """Intenta resolver la ruta relativa del MP3 generado tras la conversión.

    Busca primero en ``info_dict`` ('filepath' / 'requested_downloads'); si no,
    recompone a partir del título (outtmpl) reemplazando la extensión por '.mp3'.
    Devuelve la ruta relativa bajo descargas (con '/') o '' si no se resuelve.
    """
    candidatos: list[str] = []

    descargas = info_dict.get("requested_downloads") or []
    for d in descargas:
        if isinstance(d, dict):
            for clave in ("filepath", "_filename", "filename"):
                valor = d.get(clave)
                if valor:
                    candidatos.append(valor)

    for clave in ("filepath", "_filename", "filename"):
        valor = info_dict.get(clave)
        if valor:
            candidatos.append(valor)

    for candidato in candidatos:
        p = Path(candidato)
        if p.suffix.lower() == ".mp3" and p.is_file():
            rel = rel_descargas(p)
            if rel:
                return rel
        mp3 = p.with_suffix(".mp3")
        if mp3.is_file():
            rel = rel_descargas(mp3)
            if rel:
                return rel

    titulo = info_dict.get("title")
    if titulo:
        destino = resolver_dentro_descargas(carpeta_rel) or CARPETA_DESCARGAS
        mp3 = destino / f"{titulo}.mp3"
        if mp3.is_file():
            rel = rel_descargas(mp3)
            if rel:
                return rel
    return ""


# --------------------------------------------------------------------------- #
# Worker (hilo daemon)
# --------------------------------------------------------------------------- #

def _procesar_item(item: dict) -> None:
    """Descarga un único ítem de la cola, emitiendo eventos SSE de progreso.

    Nunca propaga excepciones: cualquier fallo se traduce en estado 'error' del
    ítem para no abortar el resto del lote.
    """
    item_id = item["id"]
    url = item["url"]
    titulo = item.get("titulo") or url
    carpeta_rel = item.get("carpeta") or ""
    bitrate = item.get("bitrate") or "320"

    db.cola_actualizar_estado(item_id, "descargando")
    with _LOCK_PROGRESO:
        PROGRESO_ACTIVO[item_id] = 0.0
    sse.emitir({"tipo": "descargando", "id": item_id, "titulo": titulo})
    emitir_cola_actualizada()

    def hook(d: dict) -> None:
        """progress_hook de yt-dlp: traduce el estado a eventos SSE."""
        try:
            estado = d.get("status")
            if estado == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                descargado = d.get("downloaded_bytes") or 0
                pct = max(0.0, min(100.0, descargado / total * 100.0)) if total else 0.0
                with _LOCK_PROGRESO:
                    PROGRESO_ACTIVO[item_id] = pct
                sse.emitir({
                    "tipo": "progreso",
                    "id": item_id,
                    "progreso": round(pct, 1),
                    "titulo": titulo,
                })
            elif estado == "finished":
                # Descarga del audio terminada; queda la conversión a MP3.
                with _LOCK_PROGRESO:
                    PROGRESO_ACTIVO[item_id] = 100.0
                sse.emitir({
                    "tipo": "progreso",
                    "id": item_id,
                    "progreso": 100.0,
                    "titulo": titulo,
                    "mensaje": "Convirtiendo a MP3…",
                })
        except Exception:  # noqa: BLE001 - el hook nunca debe romper la descarga
            pass

    try:
        opciones = _construir_opciones_descarga(carpeta_rel, bitrate, hook)
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=True)
        if not info:
            raise RuntimeError("yt-dlp no devolvió información del vídeo.")

        archivo_rel = _resolver_mp3_resultante(info, carpeta_rel)
        db.cola_actualizar_estado(item_id, "completado")
        try:
            db.historial_agregar({
                "id": item_id,
                "url": url,
                "titulo": info.get("title") or titulo,
                "canal": info.get("uploader") or info.get("channel") or item.get("canal") or "",
                "archivo": archivo_rel,
                "carpeta": carpeta_rel,
                "completado": ahora_iso(),
            })
        except Exception:  # noqa: BLE001 - el historial no debe romper el flujo
            pass
        sse.emitir({"tipo": "completado", "id": item_id, "titulo": info.get("title") or titulo})
    except DownloadError as error:
        msg = colapsar_error(error)
        db.cola_actualizar_estado(item_id, "error", msg)
        sse.emitir({"tipo": "error", "id": item_id, "error": msg})
    except Exception as error:  # noqa: BLE001 - robustez: nunca abortar el lote
        msg = colapsar_error(repr(error))
        db.cola_actualizar_estado(item_id, "error", msg)
        sse.emitir({"tipo": "error", "id": item_id, "error": msg})
    finally:
        with _LOCK_PROGRESO:
            PROGRESO_ACTIVO.pop(item_id, None)
        emitir_cola_actualizada()


def _bucle_worker() -> None:
    """Bucle del worker: procesa la cola secuencialmente hasta vaciarla."""
    global _HILO_WORKER
    try:
        while True:
            item = db.cola_siguiente_en_cola()
            if item is None:
                break
            _procesar_item(item)
    except Exception:  # noqa: BLE001 - el worker nunca debe tirar el proceso
        pass
    finally:
        # Liberamos el hilo para que pueda relanzarse si llegan más ítems.
        with _LOCK_WORKER:
            _HILO_WORKER = None
        # Si entró un ítem nuevo justo al terminar, relanzamos el worker.
        try:
            if db.cola_siguiente_en_cola() is not None:
                arrancar_worker()
        except Exception:  # noqa: BLE001
            pass


def arrancar_worker() -> None:
    """Arranca el hilo worker si no está ya corriendo (idempotente)."""
    global _HILO_WORKER
    with _LOCK_WORKER:
        if _HILO_WORKER is not None and _HILO_WORKER.is_alive():
            return
        _HILO_WORKER = threading.Thread(
            target=_bucle_worker,
            name="worker-descargas",
            daemon=True,
        )
        _HILO_WORKER.start()
