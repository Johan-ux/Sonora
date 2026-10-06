"""Reproducción propia de un vídeo de YouTube, sin descargarlo.

Es el respaldo de la vista previa. Lo normal es ver el vídeo en el reproductor
incrustado de YouTube, pero hay vídeos que YouTube se niega a servir fuera de
su web («Este vídeo no está disponible / Ver en YouTube») aunque sean públicos
y se puedan descargar. Para esos, la ventana de vídeo de la app pasa a un
``<video>`` propio que se alimenta de aquí.

YouTube ya no da formatos con audio y vídeo juntos: se piden por separado y
ffmpeg los une al vuelo en un MP4 fragmentado, que se va enviando conforme
sale. Nada toca el disco, y para saltar a otro punto se abre un flujo nuevo
desde ese segundo.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time

import yt_dlp

from .. import ffmpeg
from ..ydl_opts import opciones_runtime_js
from .youtube import _opciones_extraccion

_ID_VIDEO = re.compile(r"^[A-Za-z0-9_-]{11}$")

# La mejor resolución que haya, sin tope. No se exige un códec concreto: a
# partir de 1080p YouTube solo ofrece VP9 o AV1, y tanto esos como el audio
# Opus caben en un MP4 y los entiende la ventana, que es un Chromium.
_FORMATO = "bestvideo+bestaudio/best"

# Las URLs que da YouTube van firmadas y caducan a las pocas horas: se guardan
# un rato para que saltar de un punto a otro no repita la consulta cada vez.
_CADUCIDAD_SEGUNDOS = 3600
_MAX_RECORDADOS = 8
_recordados: dict[str, tuple[float, dict]] = {}
_cerrojo = threading.Lock()


def es_id_valido(video_id: object) -> bool:
    """Indica si ``video_id`` tiene la forma de un id de vídeo de YouTube."""
    return isinstance(video_id, str) and bool(_ID_VIDEO.match(video_id))


def resolver(video_id: str) -> dict:
    """Devuelve de dónde leer el vídeo: ``{entradas, agente, duracion}``.

    ``entradas`` son las URLs que ffmpeg debe abrir (vídeo y audio, o una sola
    si YouTube aún da ambos juntos). Lanza ``ValueError`` si el id no es válido
    y ``RuntimeError`` si no se puede reproducir (privado, directo en curso…).
    """
    if not es_id_valido(video_id):
        raise ValueError("Identificador de vídeo no válido.")
    ahora = time.monotonic()
    with _cerrojo:
        guardado = _recordados.get(video_id)
        if guardado and ahora - guardado[0] < _CADUCIDAD_SEGUNDOS:
            return guardado[1]

    opciones = _opciones_extraccion(flat=False)
    opciones.update(opciones_runtime_js())
    opciones["noplaylist"] = True
    opciones["format"] = _FORMATO
    with yt_dlp.YoutubeDL(opciones) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    if not info:
        raise RuntimeError("YouTube no devolvió datos de este vídeo.")
    if info.get("is_live"):
        raise RuntimeError("Es un directo en curso: solo se puede ver en YouTube.")
    formatos = info.get("requested_formats") or [info]
    entradas = [f["url"] for f in formatos if f.get("url")]
    if not entradas:
        raise RuntimeError("YouTube no ofrece ningún formato reproducible de este vídeo.")
    cabeceras = formatos[0].get("http_headers") or {}
    flujo = {
        "entradas": entradas,
        "agente": cabeceras.get("User-Agent", ""),
        "duracion": float(info.get("duration") or 0),
    }
    with _cerrojo:
        if len(_recordados) >= _MAX_RECORDADOS:
            # Fuera el más antiguo: basta con recordar los últimos que se vieron.
            del _recordados[min(_recordados, key=lambda clave: _recordados[clave][0])]
        _recordados[video_id] = (ahora, flujo)
    return flujo


def orden_ffmpeg(ejecutable: str, flujo: dict, inicio: float) -> list[str]:
    """Orden de ffmpeg que une las entradas y escribe el MP4 en su salida estándar."""
    orden = [ejecutable, "-hide_banner", "-loglevel", "error", "-nostdin"]
    for url in flujo["entradas"]:
        if flujo["agente"]:
            orden += ["-user_agent", flujo["agente"]]
        # Un corte de red a mitad no debe acabar con la reproducción.
        orden += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
        if inicio > 0:
            # Antes de -i: salta leyendo el índice, sin bajarse lo anterior.
            orden += ["-ss", f"{inicio:.3f}"]
        orden += ["-i", url]
    if len(flujo["entradas"]) > 1:
        orden += ["-map", "0:v:0", "-map", "1:a:0"]
    orden += [
        # Sin recodificar: se copia tal cual, que es instantáneo.
        "-c", "copy",
        # MP4 fragmentado: se puede reproducir mientras se sigue escribiendo.
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "-f", "mp4",
        "pipe:1",
    ]
    return orden


def abrir_flujo(video_id: str, inicio: float = 0.0) -> subprocess.Popen:
    """Arranca ffmpeg para ``video_id`` desde el segundo ``inicio``.

    Quien llama lee ``stdout`` y es responsable de matar el proceso al acabar.
    Lanza ``RuntimeError`` si falta ffmpeg.
    """
    carpeta = ffmpeg.localizacion()
    if carpeta is None:
        raise RuntimeError("Falta ffmpeg: sin él no se puede reproducir desde la app.")
    ejecutable = str(carpeta / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg"))
    flujo = resolver(video_id)
    # La orden es una lista construida aquí (sin shell): la URL no se interpreta.
    return subprocess.Popen(
        orden_ffmpeg(ejecutable, flujo, max(0.0, inicio)),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        # Empaquetada sin consola, cada ffmpeg abriría una ventana negra.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
