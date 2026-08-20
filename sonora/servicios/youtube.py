"""Búsqueda e información de YouTube mediante yt-dlp (sin descargar)."""

from __future__ import annotations

import re

# Si falta yt-dlp, el ImportError se propaga hasta el punto de entrada
# (sonora.escritorio / sonora.cli), que es quien sabe mostrar el error al
# usuario. Un módulo de biblioteca nunca debe terminar el proceso al importarse.
import yt_dlp

from .. import ffmpeg
from ..utils import formatear_duracion, thumbnail_desde_id

# Tope de seguridad de canciones que se traen al expandir una playlist.
# Generoso para cubrir playlists grandes; luego se descargan en lotes pequeños.
MAX_PLAYLIST = 1000


def es_url(texto: str) -> bool:
    """Indica si el texto parece una URL http(s)."""
    t = (texto or "").strip().lower()
    return t.startswith(("http://", "https://"))


def es_url_playlist(texto: str) -> bool:
    """Heurística: la URL apunta a una playlist de YouTube."""
    t = (texto or "").lower()
    return "list=" in t or "/playlist" in t


def es_url_canal(texto: str) -> bool:
    """Heurística: la URL apunta a un CANAL (no a un vídeo ni a una playlist).

    Si la URL ya trae una playlist explícita (``list=`` o ``/playlist``) NO se
    considera canal: se gestiona como playlist. Reconoce las formas de canal:
    ``/@handle``, ``/channel/UC…``, ``/c/Nombre`` y ``/user/Nombre`` (con o sin
    pestaña ``/videos``, ``/shorts``, etc.).
    """
    t = (texto or "").lower()
    if "list=" in t or "/playlist" in t:
        return False
    return ("/@" in t) or ("/channel/" in t) or ("/c/" in t) or ("/user/" in t)


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
        "canal": (
            entrada.get("uploader")
            or entrada.get("channel")
            or entrada.get("uploader_id")
            or ""
        ),
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


def _expandir_flat(url_objetivo: str, fallback: str) -> tuple[str, list[dict], int]:
    """Extrae (flat) una colección de YouTube. Devuelve ``(titulo, items, total)``.

    ``total`` es cuántos ítems dice YouTube que contiene (``playlist_count``).
    Puede ser MAYOR que ``len(items)`` cuando yt-dlp solo consigue extraer una
    parte: algunas listas limitan la paginación anónima (~100 por página) y
    devuelven menos ítems de los que realmente contienen. Devolver el total
    permite avisar al usuario en lugar de mentirle con las que sí se obtuvieron.
    """
    opciones = _opciones_extraccion(flat=True)
    opciones["playlistend"] = MAX_PLAYLIST  # no traer más de N de golpe
    items: list[dict] = []
    with yt_dlp.YoutubeDL(opciones) as ydl:
        info = ydl.extract_info(url_objetivo, download=False)
    if info is None:
        # Con ignoreerrors=True yt-dlp devuelve None en vez de lanzar; sin esto
        # el fallo se convertiría en una lista vacía silenciosa con HTTP 200.
        raise RuntimeError(
            "YouTube no devolvió datos: la URL no existe, es privada o está bloqueada."
        )
    titulo = (info.get("title") or "").strip()
    for entrada in info.get("entries", []) or []:
        if entrada:
            items.append(_entrada_a_resultado(entrada))
    # Algunas URLs (p. ej. un Mix extraído en modo flat) devuelven un único
    # vídeo sin 'entries'. Antes que devolver vacío, mostramos ese vídeo.
    # Solo si el resultado ES un vídeo: una playlist/canal legítimamente vacío
    # trae 'entries' (vacío) o _type 'playlist' y no debe disfrazarse de canción.
    if (
        not items
        and "entries" not in info
        and info.get("_type") in (None, "url", "video")
        and (info.get("id") or info.get("url"))
    ):
        items.append(_entrada_a_resultado(info))
    try:
        total = int(info.get("playlist_count") or 0)
    except (TypeError, ValueError):
        total = 0
    total = max(total, len(items))
    # Respaldo solo si YouTube no da un título usable. OJO: hay listas cuyo
    # nombre real empieza por "/" (p. ej. "/no playlist", una temática del canal),
    # así que NO descartamos esos; solo el vacío o un guion suelto.
    if not titulo or titulo == "-":
        titulo = fallback
    return titulo, items, total


def es_mix(url: str) -> bool:
    """Indica si la URL apunta a un Mix/Radio de YouTube (``list=RD…``).

    Los Mix son playlists sintéticas generadas a partir de un vídeo semilla:
    solo existen con el ``v=`` presente, así que no se pueden reescribir a
    ``playlist?list=<ID>`` como una playlist normal.
    """
    return _id_playlist(url).upper().startswith("RD")


def expandir_playlist(url: str) -> tuple[str, list[dict], int]:
    """Expande una playlist (flat). Devuelve ``(titulo, items, total_real)``.

    Importante: con una URL del tipo ``watch?v=...&list=...`` y ``extract_flat``,
    yt-dlp NO expande la playlist (devuelve un único ``_type: url`` sin entries).
    Por eso, si la URL trae un ``list=``, reconstruimos una URL limpia
    ``playlist?list=<ID>`` que yt-dlp sí expande correctamente.

    Excepción: los Mix (``list=RD…``) NO admiten esa reescritura (necesitan el
    vídeo semilla ``v=``), así que se extraen con la URL original tal cual; si
    yt-dlp no consigue expandirlos, ``_expandir_flat`` devuelve al menos el
    vídeo semilla en vez de una lista vacía.
    """
    pid = _id_playlist(url)
    if pid and not es_mix(url):
        url_objetivo = f"https://www.youtube.com/playlist?list={pid}"
    else:
        url_objetivo = url
    fallback = "Mix de YouTube" if es_mix(url) else "Playlist"
    return _expandir_flat(url_objetivo, fallback=fallback)


def _url_canal_videos(url: str) -> str:
    """Normaliza una URL de canal a su pestaña de vídeos.

    Apuntar a ``…/videos`` evita mezclar shorts, directos y playlists del canal,
    y hace que yt-dlp devuelva directamente la lista de vídeos. Si la URL ya
    apunta a una pestaña conocida, la respeta.
    """
    u = (url or "").strip().split("?")[0].split("#")[0].rstrip("/")
    for pestana in ("/videos", "/shorts", "/streams", "/featured", "/playlists"):
        if u.lower().endswith(pestana):
            return u
    return u + "/videos"


def expandir_canal(url: str) -> tuple[str, list[dict], int]:
    """Expande los vídeos de un CANAL (flat). Devuelve ``(titulo, items, total)``.

    Se trata igual que una playlist (el usuario los ve por lotes y elige cuáles
    añadir), pero apuntando a la pestaña de vídeos del canal.
    """
    return _expandir_flat(_url_canal_videos(url), fallback="Canal")


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
