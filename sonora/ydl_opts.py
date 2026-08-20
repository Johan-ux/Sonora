"""Opciones comunes de yt-dlp para la extracción de audio a MP3.

Único punto de verdad para la CLI (``sonora.cli``) y el worker de la
app (``servicios/descargas.py``): mismo formato, misma plantilla de nombre y
los mismos postprocesadores. No importa Flask ni yt-dlp (construye dicts
planos), de modo que cualquiera puede usarlo sin arrastrar dependencias.
"""

from __future__ import annotations

from pathlib import Path

# Plantilla del nombre de salida. Incluye el id del vídeo para que dos vídeos
# distintos con el mismo título no se sobrescriban entre sí (p. ej. dos
# canciones tituladas "Intro" de canales diferentes).
PLANTILLA_SALIDA = "%(title)s [%(id)s].%(ext)s"

# Bitrates permitidos para el MP3 (kbps, CBR). Se valida en la API y en la CLI.
BITRATES_VALIDOS = ("128", "192", "256", "320")
BITRATE_POR_DEFECTO = "320"

# Formatos de descarga: 'audio' (MP3) o 'video' (MP4).
FORMATOS_VALIDOS = ("audio", "video")
FORMATO_POR_DEFECTO = "audio"

# Resoluciones de vídeo permitidas: 'best' = la mejor disponible; el resto es
# el alto máximo en píxeles. Se valida en la API.
RESOLUCIONES_VALIDAS = ("best", "2160", "1440", "1080", "720", "480", "360")
RESOLUCION_POR_DEFECTO = "1080"


def normalizar_bitrate(valor) -> str:
    """Devuelve ``valor`` como bitrate válido, o el bitrate por defecto."""
    v = str(valor or "").strip()
    return v if v in BITRATES_VALIDOS else BITRATE_POR_DEFECTO


def normalizar_formato(valor) -> str:
    """Devuelve ``valor`` como formato válido ('audio'/'video'), o 'audio'."""
    v = str(valor or "").strip().lower()
    return v if v in FORMATOS_VALIDOS else FORMATO_POR_DEFECTO


def normalizar_resolucion(valor) -> str:
    """Devuelve ``valor`` como resolución válida, o la resolución por defecto."""
    v = str(valor or "").strip().lower()
    return v if v in RESOLUCIONES_VALIDAS else RESOLUCION_POR_DEFECTO


def opciones_mp3(destino: Path, bitrate: str = BITRATE_POR_DEFECTO) -> dict:
    """Opciones base de yt-dlp: mejor audio → MP3 CBR con carátula y metadatos.

    Los consumidores añaden encima sus opciones propias (cookies en la CLI;
    progress_hooks, quiet y ffmpeg_location en la app).
    """
    return {
        # Mejor pista de audio disponible (con respaldo al mejor formato).
        "format": "bestaudio/best",
        "outtmpl": str(destino / PLANTILLA_SALIDA),
        # Necesario para poder incrustar la carátula posteriormente.
        "writethumbnail": True,
        # Gestionamos los errores nosotros (uno por URL); no los silenciamos.
        "ignoreerrors": False,
        # No expandir listas de reproducción accidentalmente.
        "noplaylist": True,
        "postprocessors": [
            # 1) Extrae el audio y lo convierte a MP3 con bitrate fijo (CBR).
            #    Un valor > 10 hace que yt-dlp use '-b:a <valor>k' (bitrate
            #    fijo) en lugar de VBR ('-q:a'). 320 => 320 kbps constantes.
            # La CLI admite cualquier bitrate numérico; la whitelist
            # (normalizar_bitrate) se aplica en la capa API, no aquí.
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(bitrate or BITRATE_POR_DEFECTO),
            },
            # 2) Escribe los metadatos (título, artista, etc.) en el MP3.
            {"key": "FFmpegMetadata", "add_metadata": True},
            # 3) Incrusta la carátula (convierte la miniatura si hace falta).
            {"key": "EmbedThumbnail", "already_have_thumbnail": False},
        ],
    }


def opciones_video(destino: Path, resolucion: str = RESOLUCION_POR_DEFECTO) -> dict:
    """Opciones base de yt-dlp: mejor vídeo+audio → MP4 con metadatos.

    ``resolucion`` limita el alto máximo ('720', '1080'…) o 'best' para la
    mejor disponible. Requiere ffmpeg para fusionar las pistas de vídeo y audio
    (que YouTube sirve por separado en alta calidad). No se incrusta carátula:
    el propio vídeo es su miniatura, y el EmbedThumbnail sobre MP4 es la fuente
    más común de fallos de postprocesado.
    """
    res = normalizar_resolucion(resolucion)
    if res == "best":
        formato = "bestvideo+bestaudio/best"
    else:
        # Vídeo hasta esa altura + mejor audio; si no hay stream separable, cae
        # a un progresivo de esa altura y, en último caso, al mejor disponible.
        formato = (
            f"bestvideo[height<={res}]+bestaudio/"
            f"best[height<={res}]/best"
        )
    return {
        "format": formato,
        "outtmpl": str(destino / PLANTILLA_SALIDA),
        # Contenedor final uniforme (yt-dlp fusiona vídeo+audio con ffmpeg).
        "merge_output_format": "mp4",
        "ignoreerrors": False,
        "noplaylist": True,
        "postprocessors": [
            {"key": "FFmpegMetadata", "add_metadata": True},
        ],
    }
