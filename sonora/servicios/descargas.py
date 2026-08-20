"""Worker de descarga a MP3 y gestión de la cola con progreso en vivo.

Un único hilo daemon procesa la cola secuencialmente. El progreso del ítem en
curso se mantiene en memoria (``PROGRESO_ACTIVO``) y se difunde por SSE; la cola
persistente vive en ``db``. Las opciones de yt-dlp (mejor audio, extracción a
MP3 con bitrate fijo, metadatos y carátula) se comparten con la CLI a través de
``sonora.ydl_opts``.
"""

from __future__ import annotations

import threading
from pathlib import Path

from .. import db, ffmpeg, sse
from ..paths import CARPETA_DESCARGAS, rel_descargas, resolver_dentro_descargas
from ..utils import ahora_iso, colapsar_error
from ..ydl_opts import (
    normalizar_bitrate,
    normalizar_formato,
    normalizar_resolucion,
    opciones_mp3,
    opciones_video,
)

import yt_dlp
from yt_dlp.utils import DownloadError

# Progreso vivo del ítem que se está descargando: {id: progreso_float_0_100}.
PROGRESO_ACTIVO: dict[str, float] = {}
_LOCK_PROGRESO = threading.Lock()

# Ids cuya cancelación ha pedido el usuario mientras se descargaban.
_CANCELACIONES: set[str] = set()

# Control del worker: un único hilo daemon procesa la cola.
_HILO_WORKER: threading.Thread | None = None
_LOCK_WORKER = threading.Lock()

MENSAJE_CANCELADA = "Cancelada por el usuario"


class DescargaCancelada(Exception):
    """El usuario canceló la descarga en curso (no es un error real)."""


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
    return normalizar_bitrate(db.config_obtener("bitrate_por_defecto", "320"))


def formato_por_defecto() -> str:
    """Formato configurado por el usuario ('audio'/'video'), o 'audio'."""
    return normalizar_formato(db.config_obtener("formato_por_defecto", "audio"))


def resolucion_por_defecto() -> str:
    """Resolución de vídeo configurada por el usuario, o '1080'."""
    return normalizar_resolucion(db.config_obtener("resolucion_por_defecto", "1080"))


# --------------------------------------------------------------------------- #
# Cancelación
# --------------------------------------------------------------------------- #

def cancelar_item(item_id: str) -> bool:
    """Pide cancelar el ítem que se está descargando ahora mismo.

    Devuelve True si el ítem estaba descargándose y se anotó la cancelación
    (el worker la aplicará en el siguiente tick de progreso). Para los ítems
    'en_cola' basta con eliminarlos de la cola (``db.cola_eliminar``).
    """
    with _LOCK_PROGRESO:
        if item_id in PROGRESO_ACTIVO:
            _CANCELACIONES.add(item_id)
            return True
    return False


def _cancelacion_pedida(item_id: str) -> bool:
    with _LOCK_PROGRESO:
        return item_id in _CANCELACIONES


# --------------------------------------------------------------------------- #
# Opciones de yt-dlp y resolución del fichero resultante
# --------------------------------------------------------------------------- #

def _construir_opciones_descarga(
    carpeta_rel: str, formato: str, bitrate: str, resolucion: str, hook, pp_hook
) -> dict:
    """Opciones de yt-dlp para descargar un ítem (base compartida + app).

    Según ``formato`` construye la base de audio (MP3) o de vídeo (MP4) y le
    añade las opciones propias de la app (blindaje anti-colección, hooks…).
    """
    destino = CARPETA_DESCARGAS
    carpeta_rel = (carpeta_rel or "").strip().replace("\\", "/").strip("/")
    if carpeta_rel:
        validado = resolver_dentro_descargas(carpeta_rel)
        destino = validado if validado is not None else CARPETA_DESCARGAS
    destino.mkdir(parents=True, exist_ok=True)

    if normalizar_formato(formato) == "video":
        opciones = opciones_video(destino, resolucion)
    else:
        opciones = opciones_mp3(destino, bitrate)
    opciones.update({
        # Blindaje: un ítem de la cola es SIEMPRE una sola canción. 'noplaylist'
        # (de la base) cubre watch?v=X&list=Y (baja solo X); si por lo que sea
        # la URL fuese un canal/playlist a secas, 'playlist_items=1' impide que
        # se descargue la colección entera: como mucho baja un único vídeo.
        "playlist_items": "1",
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "postprocessor_hooks": [pp_hook],
    })
    ffmpeg_loc = ffmpeg.localizacion()
    if ffmpeg_loc is not None:
        opciones["ffmpeg_location"] = str(ffmpeg_loc)
    return opciones


def _resolver_archivo_resultante(info_dict: dict, carpeta_rel: str, formato: str) -> str:
    """Intenta resolver la ruta relativa del fichero generado tras la descarga.

    ``formato`` decide la extensión objetivo: '.mp3' (audio) o '.mp4' (vídeo).
    Busca primero en ``info_dict`` ('filepath' / 'requested_downloads'), que es
    lo más fiable tras el postprocesado; si no, recompone a partir del título y
    el id (la plantilla de ``ydl_opts``). Devuelve la ruta relativa bajo
    descargas (con '/') o '' si no se resuelve.
    """
    ext = ".mp4" if normalizar_formato(formato) == "video" else ".mp3"
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
        if p.suffix.lower() == ext and p.is_file():
            rel = rel_descargas(p)
            if rel:
                return rel
        alterno = p.with_suffix(ext)
        if alterno.is_file():
            rel = rel_descargas(alterno)
            if rel:
                return rel

    titulo = info_dict.get("title")
    vid = info_dict.get("id")
    if titulo:
        destino = resolver_dentro_descargas(carpeta_rel) or CARPETA_DESCARGAS
        nombres = [f"{titulo} [{vid}]{ext}"] if vid else []
        nombres.append(f"{titulo}{ext}")  # plantilla antigua (compatibilidad)
        for nombre in nombres:
            archivo = destino / nombre
            if archivo.is_file():
                rel = rel_descargas(archivo)
                if rel:
                    return rel
    return ""


# --------------------------------------------------------------------------- #
# Worker (hilo daemon)
# --------------------------------------------------------------------------- #

def _procesar_item(item: dict) -> None:
    """Descarga un único ítem de la cola, emitiendo eventos SSE de progreso.

    Nunca propaga excepciones: cualquier fallo se traduce en estado 'error' del
    ítem para no abortar el resto del lote. El ítem llega ya reclamado (estado
    'descargando') por ``_bucle_worker``.
    """
    item_id = item["id"]
    url = item["url"]
    titulo = item.get("titulo") or url
    carpeta_rel = item.get("carpeta") or ""
    bitrate = item.get("bitrate") or "320"
    formato = normalizar_formato(item.get("formato"))
    resolucion = item.get("resolucion") or "1080"

    def hook(d: dict) -> None:
        """progress_hook de yt-dlp: progreso a SSE + punto de cancelación."""
        if _cancelacion_pedida(item_id):
            raise DescargaCancelada()
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
                # Descarga terminada; queda el postprocesado (MP3 o fusión MP4).
                with _LOCK_PROGRESO:
                    PROGRESO_ACTIVO[item_id] = 100.0
                sse.emitir({
                    "tipo": "progreso",
                    "id": item_id,
                    "progreso": 100.0,
                    "titulo": titulo,
                    "mensaje": "Procesando…" if formato == "video" else "Convirtiendo a MP3…",
                })
        except DescargaCancelada:
            raise
        except Exception:  # noqa: BLE001 - el hook nunca debe romper la descarga
            pass

    def pp_hook(d: dict) -> None:
        """postprocessor_hook: permite cancelar también entre conversiones."""
        if _cancelacion_pedida(item_id):
            raise DescargaCancelada()

    try:
        # El alta en PROGRESO_ACTIVO y las emisiones van DENTRO del try: si
        # algo falla aquí (p. ej. la BD al listar la cola), el finally limpia
        # el progreso y el flag de cancelación en vez de dejarlos huérfanos.
        with _LOCK_PROGRESO:
            PROGRESO_ACTIVO[item_id] = 0.0
        sse.emitir({"tipo": "descargando", "id": item_id, "titulo": titulo})
        emitir_cola_actualizada()

        opciones = _construir_opciones_descarga(
            carpeta_rel, formato, bitrate, resolucion, hook, pp_hook
        )
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=True)
        if not info:
            raise RuntimeError("yt-dlp no devolvió información del vídeo.")

        archivo_rel = _resolver_archivo_resultante(info, carpeta_rel, formato)
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
    except DescargaCancelada:
        db.cola_actualizar_estado(item_id, "error", MENSAJE_CANCELADA)
        sse.emitir({"tipo": "cancelado", "id": item_id, "titulo": titulo})
    except DownloadError as error:
        # La cancelación puede aflorar envuelta en el DownloadError de yt-dlp.
        if _cancelacion_pedida(item_id):
            db.cola_actualizar_estado(item_id, "error", MENSAJE_CANCELADA)
            sse.emitir({"tipo": "cancelado", "id": item_id, "titulo": titulo})
        else:
            msg = colapsar_error(error)
            db.cola_actualizar_estado(item_id, "error", msg)
            sse.emitir({"tipo": "error", "id": item_id, "error": msg})
    except Exception as error:  # noqa: BLE001 - robustez: nunca abortar el lote
        if _cancelacion_pedida(item_id):
            db.cola_actualizar_estado(item_id, "error", MENSAJE_CANCELADA)
            sse.emitir({"tipo": "cancelado", "id": item_id, "titulo": titulo})
        else:
            msg = colapsar_error(repr(error))
            db.cola_actualizar_estado(item_id, "error", msg)
            sse.emitir({"tipo": "error", "id": item_id, "error": msg})
    finally:
        with _LOCK_PROGRESO:
            PROGRESO_ACTIVO.pop(item_id, None)
            _CANCELACIONES.discard(item_id)
        emitir_cola_actualizada()


def _bucle_worker() -> None:
    """Bucle del worker: procesa la cola secuencialmente hasta vaciarla."""
    global _HILO_WORKER
    try:
        while True:
            item = db.cola_siguiente_en_cola()
            if item is None:
                break
            # Reclamo atómico: si el usuario eliminó el ítem entre el SELECT y
            # aquí, cola_reclamar no afecta a ninguna fila y pasamos al
            # siguiente en vez de descargar un ítem ya borrado.
            if not db.cola_reclamar(item["id"]):
                continue
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
