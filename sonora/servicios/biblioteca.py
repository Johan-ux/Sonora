"""Biblioteca local: escaneo de los MP3 descargados y lectura de tags (mutagen).

Leer los tags ID3 de cada MP3 es lo caro del escaneo (abre y parsea cada
fichero), así que se cachean por ``(mtime, tamaño)``: en peticiones sucesivas
solo se releen los ficheros que cambiaron. El listado de ficheros (rglob) sí
se hace en cada petición: es barato y así las altas/bajas se ven al momento.
"""

from __future__ import annotations

import threading
from pathlib import Path

from ..paths import CARPETA_DESCARGAS, rel_descargas, resolver_dentro_descargas
from ..utils import formatear_duracion

# mutagen se usa para leer los tags de los MP3. Si falla la importación, la
# biblioteca sigue funcionando usando el nombre del fichero como título.
try:
    from mutagen.mp3 import MP3
    from mutagen.easyid3 import EasyID3
except ImportError:  # pragma: no cover
    MP3 = None
    EasyID3 = None

try:
    from mutagen.mp4 import MP4
except ImportError:  # pragma: no cover
    MP4 = None

# Extensiones de la biblioteca y su tipo (para que el frontend sepa si abrir el
# reproductor de audio o el de vídeo).
EXTENSIONES = {".mp3": "audio", ".mp4": "video"}

# Caché de tags: {ruta_absoluta: (mtime_ns, tamaño, tags)}.
_CACHE_TAGS: dict[str, tuple[int, int, dict]] = {}
_LOCK_CACHE = threading.Lock()
_MAX_CACHE = 20_000  # backstop; una biblioteca personal no debería acercarse


def leer_tags_mp3(ruta: Path) -> dict:
    """Lee los tags de un MP3 con mutagen, tolerando ficheros corruptos.

    Devuelve un dict con titulo, artista, album, duracion (M:SS). Si mutagen
    falla, usa el nombre del fichero como título y deja el resto vacío.
    """
    titulo = ruta.stem
    artista = ""
    album = ""
    duracion = ""
    if MP3 is not None:
        try:
            audio = MP3(str(ruta))
            if getattr(audio, "info", None) is not None:
                duracion = formatear_duracion(audio.info.length)
            try:
                etiquetas = EasyID3(str(ruta)) if EasyID3 is not None else {}
            except Exception:  # noqa: BLE001 - el fichero no tiene tags ID3
                etiquetas = {}
            if etiquetas:
                titulo = (etiquetas.get("title") or [titulo])[0] or titulo
                artista = (etiquetas.get("artist") or [""])[0] or ""
                album = (etiquetas.get("album") or [""])[0] or ""
        except Exception:  # noqa: BLE001 - corrupto: seguimos con el nombre
            pass
    return {"titulo": titulo, "artista": artista, "album": album, "duracion": duracion}


def leer_tags_mp4(ruta: Path) -> dict:
    """Lee los tags de un MP4 con mutagen (átomos ©nam/©ART/©alb), tolerante.

    Los MP4 descargados por yt-dlp llevan la duración y a veces título/artista
    en los metadatos; si faltan, se usa el nombre del fichero como título.
    """
    titulo = ruta.stem
    artista = ""
    album = ""
    duracion = ""
    if MP4 is not None:
        try:
            video = MP4(str(ruta))
            if getattr(video, "info", None) is not None:
                duracion = formatear_duracion(video.info.length)
            etiquetas = video.tags or {}
            titulo = (etiquetas.get("\xa9nam") or [titulo])[0] or titulo
            artista = (etiquetas.get("\xa9ART") or [""])[0] or ""
            album = (etiquetas.get("\xa9alb") or [""])[0] or ""
        except Exception:  # noqa: BLE001 - corrupto/atípico: seguimos con el nombre
            pass
    return {"titulo": titulo, "artista": artista, "album": album, "duracion": duracion}


def leer_tags(ruta: Path) -> dict:
    """Lee los tags según la extensión (mp3/mp4)."""
    if ruta.suffix.lower() == ".mp4":
        return leer_tags_mp4(ruta)
    return leer_tags_mp3(ruta)


def olvidar_cache(ruta: Path) -> None:
    """Descarta la entrada de caché de un archivo (p. ej. al eliminarlo)."""
    with _LOCK_CACHE:
        _CACHE_TAGS.pop(str(ruta), None)


def _tags_con_cache(ruta: Path, mtime_ns: int, tamano: int) -> dict:
    """Tags del fichero, releyendo solo si cambió desde la última vez."""
    clave = str(ruta)
    with _LOCK_CACHE:
        entrada = _CACHE_TAGS.get(clave)
        if entrada is not None and entrada[0] == mtime_ns and entrada[1] == tamano:
            return entrada[2]
    tags = leer_tags(ruta)
    with _LOCK_CACHE:
        if len(_CACHE_TAGS) >= _MAX_CACHE:
            _CACHE_TAGS.clear()
        _CACHE_TAGS[clave] = (mtime_ns, tamano, tags)
    return tags


def escanear(q: str = "", carpeta_rel: str = "") -> dict:
    """Escanea la biblioteca local y devuelve ``{items, carpetas}``.

    Args:
        q: filtro (case-insensitive) sobre título + artista + archivo.
        carpeta_rel: subcarpeta de descargas desde la que escanear (recursivo).
    """
    q = (q or "").strip().lower()
    base = resolver_dentro_descargas(carpeta_rel or "")
    if base is None or not base.exists():
        base = CARPETA_DESCARGAS.resolve()

    items: list[dict] = []
    subcarpetas: list[str] = []

    # Subcarpetas directas del nivel actual.
    try:
        for hijo in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if hijo.is_dir():
                rel = rel_descargas(hijo)
                if rel:
                    subcarpetas.append(rel)
    except OSError:
        pass

    # Escaneo recursivo de MP3 y MP4 bajo la carpeta actual.
    try:
        ficheros = sorted(
            (p for p in base.rglob("*") if p.suffix.lower() in EXTENSIONES),
            key=lambda p: str(p).lower(),
        )
    except OSError:
        ficheros = []

    for fichero in ficheros:
        try:
            try:
                st = fichero.stat()
            except OSError:
                continue
            rel = rel_descargas(fichero)
            if not rel:
                continue
            tags = _tags_con_cache(fichero, st.st_mtime_ns, st.st_size)
            carpeta_fichero = Path(rel).parent.as_posix()
            if carpeta_fichero == ".":
                carpeta_fichero = ""
            registro = {
                "archivo": rel,
                "titulo": tags["titulo"],
                "artista": tags["artista"],
                "album": tags["album"],
                "duracion": tags["duracion"],
                "carpeta": carpeta_fichero,
                "tamano": st.st_size,
                "tipo": EXTENSIONES.get(fichero.suffix.lower(), "audio"),
            }
            if q:
                blob = f"{registro['titulo']} {registro['artista']} {registro['archivo']}".lower()
                if q not in blob:
                    continue
            items.append(registro)
        except Exception:  # noqa: BLE001 - un fichero problemático no rompe el escaneo
            continue

    return {"items": items, "carpetas": subcarpetas}
