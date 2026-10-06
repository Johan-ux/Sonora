"""Búsqueda e información de YouTube mediante yt-dlp (sin descargar)."""

from __future__ import annotations

import base64
import re
from urllib.parse import quote, quote_plus, urlsplit

# Si falta yt-dlp, el ImportError se propaga hasta el punto de entrada
# (sonora.escritorio / sonora.cli), que es quien sabe mostrar el error al
# usuario. Un módulo de biblioteca nunca debe terminar el proceso al importarse.
import yt_dlp

from .. import ffmpeg
from ..utils import formatear_duracion, thumbnail_desde_id

# Tope de seguridad de canciones que se traen al expandir una playlist.
# Generoso para cubrir playlists grandes; luego se descargan en lotes pequeños.
MAX_PLAYLIST = 1000

# ---------------------------------------------------------------------------
# Filtros de búsqueda
#
# YouTube los recibe en el parámetro ``sp`` de la URL de resultados: un mensaje
# protobuf en base64 con el orden (campo 1) y un submensaje de filtros (campo
# 2). Los números de campo y sus valores están comprobados contra el servicio.
#
# Lo que NO está aquí es a propósito: YouTube ya no ordena por fecha de subida
# (acepta el parámetro y lo ignora), así que «recientes» lo ordenamos nosotros;
# y se dejan fuera las películas (de pago) y los filtros que exigen una cuenta.
#
# Los directos sí se pueden buscar: no se descargan mientras duran (lo impide
# ``descargas._rechazar_directos``), pero se ven en la vista previa de la app.
# ---------------------------------------------------------------------------

ORDENES = ("relevancia", "recientes", "popularidad")
_SP_ORDEN = {"popularidad": 3}
FECHAS = {"hoy": 2, "semana": 3, "mes": 4, "anio": 5}
TIPOS = {"video": 1, "canal": 2, "lista": 3}
# Los cortes son los de YouTube: menos de 4 min, de 4 a 20 y más de 20.
DURACIONES = {"corta": 1, "media": 3, "larga": 2}
CARACTERISTICAS = {
    "directo": 8,
    "hd": 4,
    "subtitulos": 5,
    "cc": 6,
    "3d": 7,
    "4k": 14,
    "360": 15,
    "hdr": 25,
    "vr180": 26,
}

FILTROS_POR_DEFECTO = {
    "orden": "relevancia",
    "fecha": "",
    "duracion": "",
    "tipo": "video",
    "caracteristicas": [],
}

# Para ordenar por fecha hace falta margen: se piden estos y luego se recorta.
RESULTADOS_PARA_ORDENAR = 50
# Entre los resultados se cuelan entradas de otro tipo (el canal del artista,
# un Mix…) que se descartan; se piden unas cuantas de más para compensar.
_MARGEN_DESCARTES = 6


def es_url(texto: str) -> bool:
    """Indica si el texto parece una URL http(s)."""
    t = (texto or "").strip().lower()
    return t.startswith(("http://", "https://"))


def es_url_playlist(texto: str) -> bool:
    """Heurística: la URL apunta a una playlist de YouTube.

    Lo es si lleva el parámetro ``list=`` o si su ruta es ``/playlist``. Se
    mira por partes y no como texto: buscar «/playlist» a secas casaba también
    con la pestaña ``/@canal/playlists``, que es una página de canal.
    """
    try:
        partes = urlsplit((texto or "").strip())
    except ValueError:
        return False
    if re.search(r"(?:^|&)list=", partes.query, re.IGNORECASE):
        return True
    return partes.path.rstrip("/").lower() == "/playlist"


def id_video(url: str) -> str:
    """Id del vídeo que señala la URL (``v=…`` o ``youtu.be/<id>``), o ''."""
    m = re.search(r"(?:[?&]v=|youtu\.be/)([\w-]{11})", url or "")
    return m.group(1) if m else ""


def es_url_canal(texto: str) -> bool:
    """Heurística: la URL apunta a un CANAL (no a un vídeo ni a una playlist).

    Si la URL ya trae una playlist explícita (``list=`` o ``/playlist``) NO se
    considera canal: se gestiona como playlist. Reconoce las formas de canal:
    ``/@handle``, ``/channel/UC…``, ``/c/Nombre`` y ``/user/Nombre`` (con o sin
    pestaña ``/videos``, ``/shorts``, etc.).
    """
    if es_url_playlist(texto):
        return False
    t = (texto or "").lower()
    return ("/@" in t) or ("/channel/" in t) or ("/c/" in t) or ("/user/" in t)


def normalizar_filtros(filtros: object) -> dict:
    """Devuelve los filtros con todas sus claves y solo valores conocidos.

    Tolerante: lo que no se reconoce (o no viene) cae a su valor por defecto,
    de modo que un cliente antiguo que no manda filtros busca como siempre.
    """
    datos = filtros if isinstance(filtros, dict) else {}

    def elegir(clave: str, validos, por_defecto: str) -> str:
        # isinstance antes que 'in': una lista no se puede buscar en un dict.
        valor = datos.get(clave)
        return valor if isinstance(valor, str) and valor in validos else por_defecto

    marcadas = datos.get("caracteristicas")
    if not isinstance(marcadas, (list, tuple)):
        marcadas = []
    return {
        "orden": elegir("orden", ORDENES, "relevancia"),
        "fecha": elegir("fecha", FECHAS, ""),
        "duracion": elegir("duracion", DURACIONES, ""),
        "tipo": elegir("tipo", TIPOS, "video"),
        "caracteristicas": sorted(
            {c for c in marcadas if isinstance(c, str) and c in CARACTERISTICAS}
        ),
    }


def _varint(numero: int) -> bytes:
    """Codifica un entero como varint de protobuf."""
    octetos = bytearray()
    while True:
        bajo = numero & 0x7F
        numero >>= 7
        if numero:
            octetos.append(bajo | 0x80)
        else:
            octetos.append(bajo)
            return bytes(octetos)


def _campo(numero: int, valor: int) -> bytes:
    """Campo protobuf de tipo varint: su etiqueta seguida del valor."""
    return _varint(numero << 3) + _varint(valor)


def parametro_sp(filtros: dict) -> str:
    """Construye el parámetro ``sp`` de YouTube para unos filtros normalizados."""
    campos = {2: TIPOS[filtros["tipo"]]}
    if filtros["fecha"]:
        campos[1] = FECHAS[filtros["fecha"]]
    if filtros["duracion"]:
        campos[3] = DURACIONES[filtros["duracion"]]
    for caracteristica in filtros["caracteristicas"]:
        campos[CARACTERISTICAS[caracteristica]] = 1
    cuerpo = b"".join(_campo(numero, valor) for numero, valor in sorted(campos.items()))
    mensaje = b""
    orden = _SP_ORDEN.get(filtros["orden"])
    if orden:
        mensaje += _campo(1, orden)
    # Campo 2, tipo «longitud delimitada»: el submensaje con los filtros.
    mensaje += _varint((2 << 3) | 2) + _varint(len(cuerpo)) + cuerpo
    return base64.b64encode(mensaje).decode("ascii")


def _entrada_a_resultado(entrada: dict) -> dict:
    """Normaliza una entrada de yt-dlp al formato de resultado del contrato."""
    vid = entrada.get("id") or ""
    # 'webpage_url' es la página del vídeo y manda. En una extracción completa
    # con un único formato, 'url' es la dirección firmada del stream: en la cola
    # caducaría a las horas y bajaría como un «videoplayback» sin nombre.
    url = entrada.get("webpage_url") or entrada.get("url") or ""
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
        "tipo": "video",
        # Fecha de subida (segundos Unix). En las búsquedas es aproximada: sale
        # del «hace 3 meses» que enseña YouTube. None si no se conoce.
        "timestamp": entrada.get("timestamp"),
        "directo": _estado_directo(entrada),
    }


def _estado_directo(entrada: dict) -> str:
    """Estado de emisión de un vídeo: 'en_vivo', 'programado', 'terminado' o ''.

    La interfaz lo necesita para decidir qué ofrecer: un directo en curso (o
    por empezar) se puede ver pero no descargar; uno terminado es ya un vídeo
    como cualquier otro.
    """
    estado = entrada.get("live_status")
    if estado == "is_live" or entrada.get("is_live"):
        return "en_vivo"
    if estado == "is_upcoming":
        return "programado"
    if estado in ("was_live", "post_live") or entrada.get("was_live"):
        return "terminado"
    return ""


def _tipo_de_entrada(entrada: dict) -> str:
    """Clasifica un resultado de búsqueda: 'video', 'lista' o 'canal'."""
    url = (entrada.get("url") or "").lower()
    if es_url_playlist(url):
        return "lista"
    if es_url_canal(url):
        return "canal"
    return "video"


def _coleccion_a_resultado(entrada: dict, tipo: str) -> dict:
    """Normaliza una lista o un canal encontrados en una búsqueda.

    No son descargables tal cual: la interfaz los abre volviendo a buscar por
    su URL, que es el camino de siempre para expandir playlists y canales.
    """
    thumbnail = ""
    thumbs = entrada.get("thumbnails") or []
    if isinstance(thumbs, list) and thumbs and isinstance(thumbs[-1], dict):
        thumbnail = thumbs[-1].get("url", "")
    if thumbnail.startswith("//"):
        # Los avatares de canal llegan sin esquema.
        thumbnail = "https:" + thumbnail
    nombre_canal = entrada.get("channel") or entrada.get("uploader") or ""
    return {
        "id": "",
        "url": entrada.get("url") or "",
        "titulo": entrada.get("title") or nombre_canal or "(sin título)",
        # En un canal el título ya es su nombre: debajo va su identificador.
        "canal": (entrada.get("uploader_id") or "") if tipo == "canal" else nombre_canal,
        "duracion": "",
        "thumbnail": thumbnail,
        "tipo": tipo,
        "timestamp": None,
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


def _acotar_n(n: int) -> int:
    """Número de resultados pedido, entre 1 y 50 (12 si no es un número)."""
    try:
        return max(1, min(int(n or 12), 50))
    except (TypeError, ValueError):
        return 12


def _opciones_busqueda() -> dict:
    """Opciones de yt-dlp para una búsqueda (flat, con fecha aproximada)."""
    opciones = _opciones_extraccion(flat=True)
    opciones["noplaylist"] = True
    # Sin esto los resultados no traen fecha. Con ello yt-dlp la deduce del
    # «hace 3 meses» de YouTube: aproximada, pero basta para ordenar y enseñar.
    opciones["extractor_args"] = {"youtubetab": {"approximate_date": [""]}}
    return opciones


def buscar(consulta: str, n: int, filtros: object = None) -> list[dict]:
    """Busca por texto aplicando los filtros (orden, fecha, duración, tipo…).

    Sin filtros delega en ``buscar_ytsearch``, el camino de siempre. Con ellos
    usa la URL de resultados de YouTube con su parámetro ``sp``.

    «Más recientes» no existe ya en YouTube: se piden más resultados de los
    necesarios y se ordenan aquí por su fecha aproximada. No es, por tanto,
    «lo último subido a YouTube», sino lo más nuevo entre lo más relevante;
    combinado con el filtro de fecha sí acota de verdad.
    """
    f = normalizar_filtros(filtros)
    if f == FILTROS_POR_DEFECTO:
        return buscar_ytsearch(consulta, n)
    n = _acotar_n(n)
    recientes = f["orden"] == "recientes"
    url = (
        "https://www.youtube.com/results?search_query="
        + quote_plus(consulta)
        + "&sp="
        + quote(parametro_sp(f))
    )
    opciones = _opciones_busqueda()
    opciones["playlistend"] = (
        max(RESULTADOS_PARA_ORDENAR, n) if recientes else n + _MARGEN_DESCARTES
    )
    with yt_dlp.YoutubeDL(opciones) as ydl:
        info = ydl.extract_info(url, download=False)
    resultados: list[dict] = []
    for entrada in (info or {}).get("entries", []) or []:
        if not entrada or _tipo_de_entrada(entrada) != f["tipo"]:
            continue
        if f["tipo"] == "video":
            resultados.append(_entrada_a_resultado(entrada))
        else:
            resultados.append(_coleccion_a_resultado(entrada, f["tipo"]))
    if recientes:
        # Orden estable: lo que no trae fecha se queda al final, en su orden.
        resultados.sort(key=lambda r: r["timestamp"] or 0, reverse=True)
    return resultados[:n]


def buscar_ytsearch(consulta: str, n: int) -> list[dict]:
    """Búsqueda rápida (flat) ``ytsearchN:<consulta>``."""
    n = _acotar_n(n)
    opciones = _opciones_busqueda()
    resultados: list[dict] = []
    with yt_dlp.YoutubeDL(opciones) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{consulta}", download=False)
    for entrada in (info or {}).get("entries", []) or []:
        # Aunque se piden vídeos, YouTube cuela a veces el canal del artista:
        # como «vídeo» saldría una tarjeta que ni se escucha ni se descarga.
        if entrada and _tipo_de_entrada(entrada) == "video":
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
        if not entrada:
            continue
        # La pestaña «Listas» de un canal no trae vídeos sino playlists. Como
        # canción saldría una tarjeta sin miniatura que, al añadirla, bajaría
        # solo el primer vídeo de la lista con el nombre de esta.
        tipo = _tipo_de_entrada(entrada)
        if tipo == "video":
            items.append(_entrada_a_resultado(entrada))
        else:
            items.append(_coleccion_a_resultado(entrada, tipo))
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
