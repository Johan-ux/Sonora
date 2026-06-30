"""Búsqueda e información de YouTube mediante yt-dlp (sin descargar)."""

from __future__ import annotations

import re
import sys

from .. import ffmpeg
from ..utils import formatear_duracion, thumbnail_desde_id

try:
    import yt_dlp
except ImportError:  # pragma: no cover - guía al usuario si falta la dependencia
    sys.exit(
        "Falta la dependencia 'yt-dlp'.\n"
        "Instálala con: pip install -r requirements.txt"
    )

# Tope de seguridad de canciones que se traen al expandir una playlist.
MAX_PLAYLIST = 200


def es_url(texto: str) -> bool:
    """Indica si el texto parece una URL http(s)."""
    t = (texto or "").strip().lower()
    return t.startswith("http://") or t.startswith("https://")


def es_url_playlist(texto: str) -> bool:
    """Heurística: la URL apunta a una playlist de YouTube."""
    t = (texto or "").lower()
    return "list=" in t or "/playlist" in t


def _entrada_a_resultado(entrada: dict) -> dict:
    """Normaliza una entrada de yt-dlp al formato de resultado del contrato."""
    vid = entrada.get("id") or ""
    url = entrada.get("url") or entrada.get("webpage_url") or ""
    # En extracción flat 'url' puede ser solo el id; reconstruimos la URL.
    if url and not es_url(url):
        url = f"https://www.youtube.com/watch?v={vid or url}"
    if not url and vid:
        url = f"https://www.youtube.com/watch?v={vid}"
    thumbnail = entrada.get("thumbnail") or ""
    if not thumbnail:
        thumbs = entrada.get("thumbnails") or []
        if isinstance(thumbs, list) and thumbs and isinstance(thumbs[-1], dict):
            thumbnail = thumbs[-1].get("url", "")
    if not thumbnail and vid:
        thumbnail = thumbnail_desde_id(vid)
    return {
        "id": vid,
        "url": url,
        "titulo": entrada.get("title") or "(sin título)",
        "canal": entrada.get("uploader") or entrada.get("channel") or entrada.get("uploader_id") or "",
        "duracion": formatear_duracion(entrada.get("duration")),
        "thumbnail": thumbnail,
    }


def _opciones_extraccion(flat: bool) -> dict:
    """Opciones base de yt-dlp para extraer info sin descargar."""
    opciones: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ignoreerrors": True,
    }
    if flat:
        opciones["extract_flat"] = True
    ffmpeg_loc = ffmpeg.localizacion()
    if ffmpeg_loc is not None:
        opciones["ffmpeg_location"] = str(ffmpeg_loc)
    return opciones


def buscar_ytsearch(consulta: str, n: int) -> list[dict]:
    """Búsqueda rápida (flat) ``ytsearchN:<consulta>``."""
    try:
        n = max(1, min(int(n or 12), 50))
    except (TypeError, ValueError):
        n = 12
    opciones = _opciones_extraccion(flat=True)
    opciones["noplaylist"] = True
    resultados: list[dict] = []
    with yt_dlp.YoutubeDL(opciones) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{consulta}", download=False)
    for entrada in (info or {}).get("entries", []) or []:
        if entrada:
            resultados.append(_entrada_a_resultado(entrada))
    return resultados


def _id_playlist(url: str) -> str:
    """Extrae el id de la playlist (parámetro ``list=``) de una URL, si lo hay."""
    m = re.search(r"[?&]list=([^&]+)", url or "")
    return m.group(1) if m else ""


def expandir_playlist(url: str) -> tuple[str, list[dict]]:
    """Expande una playlist (flat). Devuelve ``(titulo_playlist, items)``.

    Importante: con una URL del tipo ``watch?v=...&list=...`` y ``extract_flat``,
    yt-dlp NO expande la playlist (devuelve un único ``_type: url`` sin entries).
    Por eso, si la URL trae un ``list=``, reconstruimos una URL limpia
    ``playlist?list=<ID>`` que yt-dlp sí expande correctamente.
    """
    pid = _id_playlist(url)
    url_limpia = f"https://www.youtube.com/playlist?list={pid}" if pid else url
    opciones = _opciones_extraccion(flat=True)
    opciones["playlistend"] = MAX_PLAYLIST  # no traer más de N de golpe
    items: list[dict] = []
    with yt_dlp.YoutubeDL(opciones) as ydl:
        info = ydl.extract_info(url_limpia, download=False)
    titulo = ((info or {}).get("title") or "").strip()
    for entrada in (info or {}).get("entries", []) or []:
        if entrada:
            items.append(_entrada_a_resultado(entrada))
    # Título de respaldo si yt-dlp no devuelve uno usable (p. ej. "/no playlist").
    if not titulo or titulo in ("-", "/no playlist") or titulo.startswith("/"):
        titulo = f"Playlist ({len(items)} canciones)"
    return titulo, items


def info_video(url: str) -> dict:
    """Extrae la información de un único vídeo (no flat, sin descargar)."""
    opciones = _opciones_extraccion(flat=False)
    opciones["noplaylist"] = True
    with yt_dlp.YoutubeDL(opciones) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("No se pudo obtener información del vídeo.")
    # Si por error es una playlist, tomamos la primera entrada disponible.
    if info.get("entries"):
        entradas = [e for e in info["entries"] if e]
        if not entradas:
            raise RuntimeError("La URL no contiene vídeos.")
        info = entradas[0]
    return _entrada_a_resultado(info)
