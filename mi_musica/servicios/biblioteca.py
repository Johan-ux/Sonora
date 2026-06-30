"""Biblioteca local: escaneo de los MP3 descargados y lectura de tags (mutagen)."""

from __future__ import annotations

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

    # Escaneo recursivo de MP3 bajo la carpeta actual.
    try:
        ficheros = sorted(base.rglob("*.mp3"), key=lambda p: str(p).lower())
    except OSError:
        ficheros = []

    for fichero in ficheros:
        try:
            if not fichero.is_file():
                continue
            tags = leer_tags_mp3(fichero)
            rel = rel_descargas(fichero)
            if not rel:
                continue
            carpeta_fichero = Path(rel).parent.as_posix()
            if carpeta_fichero == ".":
                carpeta_fichero = ""
            try:
                tamano = fichero.stat().st_size
            except OSError:
                tamano = 0
            registro = {
                "archivo": rel,
                "titulo": tags["titulo"],
                "artista": tags["artista"],
                "album": tags["album"],
                "duracion": tags["duracion"],
                "carpeta": carpeta_fichero,
                "tamano": tamano,
            }
            if q:
                blob = f"{registro['titulo']} {registro['artista']} {registro['archivo']}".lower()
                if q not in blob:
                    continue
            items.append(registro)
        except Exception:  # noqa: BLE001 - un fichero problemático no rompe el escaneo
            continue

    return {"items": items, "carpetas": subcarpetas}
