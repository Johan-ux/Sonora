"""Worker de descarga a MP3 y gestión de la cola con progreso en vivo.

Varios hilos daemon procesan la cola en paralelo (tres por defecto); el
reparto lo resuelve el reclamo atómico de la BD, no un reparto previo. Los
fallos pasajeros se reintentan solos, y los definitivos (vídeo privado,
bloqueado por región…) se dan por perdidos sin gastar intentos. Una descarga
interrumpida se lleva por delante sus propios ficheros a medias.

yt-dlp no trabaja en la carpeta de música sino en una temporal por ítem, y
solo al terminar mueve allí el resultado: la biblioteca nunca ve un fichero a
medio hacer.

El progreso de cada ítem en curso se mantiene en memoria (``PROGRESO_ACTIVO``)
y se difunde por SSE; la cola persistente vive en ``db``. Las opciones de
yt-dlp (mejor audio, extracción a MP3 con bitrate fijo, metadatos y carátula)
se comparten con la CLI a través de ``sonora.ydl_opts``.
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError

from .. import db, ffmpeg, sse
from ..paths import CARPETA_DESCARGAS, rel_descargas, resolver_dentro_descargas
from ..utils import ahora_iso, colapsar_error
from ..ydl_opts import (
    PLANTILLA_SALIDA,
    normalizar_bitrate,
    normalizar_formato,
    normalizar_resolucion,
    opciones_mp3,
    opciones_video,
)

# Progreso vivo del ítem que se está descargando: {id: progreso_float_0_100}.
PROGRESO_ACTIVO: dict[str, float] = {}
_LOCK_PROGRESO = threading.Lock()

# Ids cuya cancelación ha pedido el usuario mientras se descargaban.
_CANCELACIONES: set[str] = set()

# Workers vivos. Varios hilos daemon procesan la cola en paralelo; el
# reparto lo resuelve el reclamo atómico de la BD, no un reparto previo.
_HILOS: set[threading.Thread] = set()
_LOCK_WORKER = threading.Lock()

# Descargas simultáneas. Tres aprovechan bien la línea sin que YouTube empiece
# a estrangular la conexión; el tope evita que un valor absurdo en la config
# convierta la cola en una tormenta de peticiones.
SIMULTANEAS_POR_DEFECTO = 3
MAX_SIMULTANEAS = 5

MENSAJE_CANCELADA = "Cancelada por el usuario"

# Reintentos automáticos ante fallos pasajeros (cortes de red, 5xx, una firma
# que caducó a mitad). Sin esto, un parpadeo de la conexión deja el ítem en
# error esperando a que el usuario pulse reintentar a mano.
MAX_INTENTOS = 3
ESPERA_REINTENTO = 3.0  # segundos antes del 2º intento; se dobla en cada uno

# Fragmentos que delatan un fallo definitivo: el vídeo no se va a poder
# descargar ahora ni dentro de diez segundos, así que reintentar solo gasta
# tiempo y hace esperar al resto de la cola.
ERRORES_PERMANENTES = (
    "private video",
    "video unavailable",
    "has been removed",
    "removed by the uploader",
    "members-only",
    "join this channel",
    "sign in to confirm your age",
    "age-restricted",
    # Cubre las dos formas que usa yt-dlp: "not available in your country" y
    # "has not made this video available in your country".
    "available in your country",
    "blocked it in your country",
    "who has blocked it",
    "copyright",
    "has been terminated",
    "no video formats found",
    "unsupported url",
    "is not a valid url",
    # Directos: el que aún no ha empezado y el que sigue en emisión (este
    # último lo rechaza _rechazar_directos con MENSAJE_DIRECTO).
    "live event will begin",
    "emisión en directo",
    # Sin ffmpeg no hay conversión ni fusión que valga, se intente las veces
    # que se intente.
    "ffmpeg not found",
    "ffmpeg is not installed",
)

# Texto con el que se rechaza un directo en curso.
MENSAJE_DIRECTO = (
    "Es una emisión en directo que aún no ha terminado: se podrá descargar cuando acabe."
)


def _rechazar_directos(info: dict, *, incomplete: bool = False) -> None:
    """``match_filter`` de yt-dlp: un directo en curso no se descarga.

    yt-dlp sí sabe bajarlos, pero graba desde ahora hasta que la emisión acabe:
    con una radio de 24 horas eso es un hueco de la cola ocupado para siempre.
    Se lanza el error en vez de devolver un motivo porque un motivo solo hace
    que yt-dlp se salte el vídeo en silencio, y el ítem se daría por descargado.
    """
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
        raise DownloadError(MENSAJE_DIRECTO)


def _es_error_permanente(mensaje: str) -> bool:
    """Indica si el error no tiene arreglo reintentando."""
    texto = (mensaje or "").lower()
    return any(fragmento in texto for fragmento in ERRORES_PERMANENTES)


# Carpeta de trabajo de las descargas en curso, hermana de la de música.
NOMBRE_TEMPORAL = "temporal"


def _raiz_temporal() -> Path:
    """Carpeta donde yt-dlp trabaja mientras baja y convierte.

    Va JUNTO a la de descargas y no dentro. Lo que hay a medias —el '.part',
    la pista de vídeo esperando a su audio, el original antes de pasar a MP3,
    la miniatura— tiene extensiones de música de verdad ('.f399.mp4',
    '.temp.mp4', '.m4a'): dentro, la biblioteca lo enseñaría como una pista
    más y, si la descarga se cancela, se quedaría allí para siempre. Al estar
    en el mismo disco, mover el resultado a su sitio es instantáneo.
    """
    return CARPETA_DESCARGAS.parent / NOMBRE_TEMPORAL


def _carpeta_temporal(item_id: str) -> Path:
    """Carpeta de trabajo de un ítem (los ids los genera la app: son seguros)."""
    return _raiz_temporal() / item_id


def _borrar_temporal(carpeta: Path) -> None:
    """Borra la carpeta de trabajo de un ítem con todo lo que contenga.

    Si otro proceso aún tiene abierto algún fichero (ffmpeg recién
    interrumpido), se queda; lo recoge el barrido del siguiente arranque.
    """
    shutil.rmtree(carpeta, ignore_errors=True)


def limpiar_temporales_huerfanos() -> int:
    """Borra, al arrancar, las carpetas de trabajo que ya no son de nadie.

    Se conservan las de los ítems que siguen pendientes: una descarga cortada
    por un cierre inesperado vuelve a la cola y, con su '.part' intacto,
    continúa por donde iba en vez de empezar de cero. Devuelve cuántas borró.
    """
    try:
        carpetas = [c for c in _raiz_temporal().iterdir() if c.is_dir()]
    except OSError:
        return 0
    pendientes = {
        item["id"] for item in db.cola_listar()
        if item.get("estado") in ("en_cola", "descargando")
    }
    borradas = 0
    for carpeta in carpetas:
        if carpeta.name not in pendientes:
            _borrar_temporal(carpeta)
            borradas += 1
    return borradas


def _esperar_cancelable(segundos: float, item_id: str) -> None:
    """Espera ``segundos`` comprobando la cancelación a intervalos cortos.

    Un ``sleep`` largo dejaría el botón de cancelar sin efecto aparente durante
    toda la espera entre reintentos.
    """
    fin = time.monotonic() + max(0.0, segundos)
    while time.monotonic() < fin:
        if _cancelacion_pedida(item_id):
            raise DescargaCancelada()
        time.sleep(min(0.25, max(0.0, fin - time.monotonic())))


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


def emitir_item_actualizado(item_id: str) -> None:
    """Emite el estado de UN ítem (evento ``item_actualizado``).

    Para los cambios que solo tocan una fila: empieza a bajar, termina, falla.
    Mandar la cola entera en cada uno hace que una playlist de mil canciones
    se serialice y se repinte entera dos mil veces. Si el ítem ya no existe,
    se manda la cola completa para que la interfaz se ponga al día.
    """
    item = db.cola_obtener(item_id)
    if item is None:
        emitir_cola_actualizada()
        return
    with _LOCK_PROGRESO:
        vivo = PROGRESO_ACTIVO.get(item_id)
    item["progreso"] = float(vivo) if vivo is not None else 0.0
    sse.emitir({"tipo": "item_actualizado", "item": item})


def bitrate_por_defecto() -> str:
    """Bitrate configurado por el usuario, o '320' por defecto."""
    return normalizar_bitrate(db.config_obtener("bitrate_por_defecto", "320"))


def formato_por_defecto() -> str:
    """Formato configurado por el usuario ('audio'/'video'), o 'audio'."""
    return normalizar_formato(db.config_obtener("formato_por_defecto", "audio"))


def resolucion_por_defecto() -> str:
    """Resolución de vídeo configurada por el usuario, o '1080'."""
    return normalizar_resolucion(db.config_obtener("resolucion_por_defecto", "1080"))


def normalizar_simultaneas(valor) -> int:
    """Devuelve ``valor`` como número de descargas simultáneas válido.

    Se acota a 1..``MAX_SIMULTANEAS``; cualquier cosa que no sea un número cae
    al valor por defecto.
    """
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        return SIMULTANEAS_POR_DEFECTO
    return max(1, min(MAX_SIMULTANEAS, numero))


def descargas_simultaneas() -> int:
    """Cuántas descargas se procesan a la vez, según la configuración.

    Si la configuración no se puede leer (BD aún sin inicializar, por ejemplo)
    se usa el valor por defecto: quedarse sin workers por no poder leer una
    preferencia sería mucho peor que ignorarla.
    """
    try:
        valor = db.config_obtener("descargas_simultaneas", str(SIMULTANEAS_POR_DEFECTO))
    except Exception:  # noqa: BLE001
        return SIMULTANEAS_POR_DEFECTO
    return normalizar_simultaneas(valor)


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


def hay_descargas_en_curso() -> bool:
    """Indica si algún ítem se está descargando o convirtiendo ahora mismo."""
    with _LOCK_PROGRESO:
        return bool(PROGRESO_ACTIVO)


# --------------------------------------------------------------------------- #
# Opciones de yt-dlp y resolución del fichero resultante
# --------------------------------------------------------------------------- #

def _construir_opciones_descarga(
    carpeta_rel: str, formato: str, bitrate: str, resolucion: str, hook, pp_hook,
    temporal: Path,
) -> dict:
    """Opciones de yt-dlp para descargar un ítem (base compartida + app).

    Según ``formato`` construye la base de audio (MP3) o de vídeo (MP4) y le
    añade las opciones propias de la app (blindaje anti-colección, hooks…).
    ``temporal`` es la carpeta de trabajo del ítem (ver ``_raiz_temporal``).
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
        # yt-dlp baja y convierte en 'temp' y solo al acabar mueve el
        # resultado a 'home'. La plantilla va sin carpeta: con una ruta
        # absoluta, 'paths' se ignora.
        "outtmpl": PLANTILLA_SALIDA,
        "paths": {"home": str(destino), "temp": str(temporal)},
        # Blindaje: un ítem de la cola es SIEMPRE una sola canción. 'noplaylist'
        # (de la base) cubre watch?v=X&list=Y (baja solo X); si por lo que sea
        # la URL fuese un canal/playlist a secas, 'playlist_items=1' impide que
        # se descargue la colección entera: como mucho baja un único vídeo.
        "playlist_items": "1",
        # Un directo en curso no acabaría nunca de descargarse: se rechaza.
        "match_filter": _rechazar_directos,
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

    # Todo lo que yt-dlp escribe a medias va aquí; se borra entero al salir.
    temporal = _carpeta_temporal(item_id)

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
                    "mensaje": "Procesando…" if formato == "video" else "Convirtiendo…",
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
        emitir_item_actualizado(item_id)

        opciones = _construir_opciones_descarga(
            carpeta_rel, formato, bitrate, resolucion, hook, pp_hook, temporal
        )
        info = None
        for intento in range(1, MAX_INTENTOS + 1):
            try:
                with yt_dlp.YoutubeDL(opciones) as ydl:
                    info = ydl.extract_info(url, download=True)
                break
            except DownloadError as error:
                # Una cancelación pedida durante la descarga aflora envuelta en
                # DownloadError: no es un fallo que reintentar.
                if _cancelacion_pedida(item_id):
                    raise DescargaCancelada() from error
                mensaje = colapsar_error(error)
                if intento >= MAX_INTENTOS or _es_error_permanente(mensaje):
                    raise
                espera = ESPERA_REINTENTO * (2 ** (intento - 1))
                sse.emitir({
                    "tipo": "progreso",
                    "id": item_id,
                    "progreso": 0.0,
                    "titulo": titulo,
                    "mensaje": f"Reintentando ({intento + 1}/{MAX_INTENTOS})…",
                })
                _esperar_cancelable(espera, item_id)
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
        # Acabe como acabe: terminada, lo suyo ya está en la carpeta de música;
        # cancelada o fallida, no va a quedar nada aprovechable.
        _borrar_temporal(temporal)
        with _LOCK_PROGRESO:
            PROGRESO_ACTIVO.pop(item_id, None)
            _CANCELACIONES.discard(item_id)
        emitir_item_actualizado(item_id)


def _bucle_worker() -> None:
    """Bucle de un worker: toma ítems de la cola hasta vaciarla.

    Varios hilos ejecutan este bucle a la vez. No hace falta repartir el
    trabajo entre ellos: ``db.cola_reclamar`` es atómico, así que si dos
    workers miran el mismo ítem solo uno se lo queda y el otro sigue buscando.
    """
    try:
        while True:
            item = db.cola_siguiente_en_cola()
            if item is None:
                break
            # Reclamo atómico: cubre tanto al usuario que eliminó el ítem entre
            # el SELECT y el UPDATE como al worker vecino que se le adelantó.
            if not db.cola_reclamar(item["id"]):
                continue
            _procesar_item(item)
    except Exception:  # noqa: BLE001 - un worker nunca debe tirar el proceso
        pass
    finally:
        with _LOCK_WORKER:
            _HILOS.discard(threading.current_thread())
        # Si entró un ítem nuevo justo al terminar, se repuebla la plantilla.
        try:
            if db.cola_siguiente_en_cola() is not None:
                arrancar_worker()
        except Exception:  # noqa: BLE001
            pass


def arrancar_worker() -> None:
    """Asegura que haya tantos workers vivos como descargas simultáneas.

    Idempotente: se puede llamar en cada alta de la cola. Solo crea los hilos
    que falten para llegar al número configurado, nunca de más.
    """
    with _LOCK_WORKER:
        # Los hilos que ya terminaron no cuentan para el cupo.
        for hilo in [h for h in _HILOS if not h.is_alive()]:
            _HILOS.discard(hilo)
        faltan = descargas_simultaneas() - len(_HILOS)
        for _ in range(max(0, faltan)):
            hilo = threading.Thread(
                target=_bucle_worker,
                name="worker-descargas",
                daemon=True,
            )
            _HILOS.add(hilo)
            hilo.start()


def hay_tanda_en_marcha() -> bool:
    """Indica si queda algún worker vivo (es decir, si se está descargando)."""
    with _LOCK_WORKER:
        return any(hilo.is_alive() for hilo in _HILOS)


def reponer_workers() -> None:
    """Completa la plantilla de workers si ya hay una tanda en marcha.

    Los workers que encuentran la cola vacía terminan. Si la tanda empezó con
    una sola canción, queda un único worker; lo que se añada después lo iría
    bajando él solo, de una en una, por muchas descargas simultáneas que haya
    configuradas. Se llama en cada alta. Sin tanda en marcha no hace nada: las
    descargas las arranca el usuario.
    """
    if hay_tanda_en_marcha():
        arrancar_worker()
