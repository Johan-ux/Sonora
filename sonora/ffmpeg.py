"""Localización robusta del ejecutable de ffmpeg.

Compartida por la CLI (``sonora.cli``) y por la app de escritorio. No
depende de Flask ni de yt-dlp, de modo que la CLI puede importarla sin arrastrar
el resto del paquete.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path

from . import paths


def localizar_ffmpeg(ruta_explicita: Path | None = None) -> Path | None:
    """Localiza el ejecutable de ffmpeg de forma robusta.

    Orden de búsqueda:
        1. Ruta indicada explícitamente.
        2. El que viaja con el ejecutable empaquetado (``paths.DIR_HERRAMIENTAS``):
           una versión conocida, y así nadie tiene que instalar ffmpeg.
        3. El PATH del sistema (``shutil.which``).
        4. Ubicaciones habituales en Windows, incluida la de winget. Esto permite
           que funcione aunque la terminal se abriera antes de instalar ffmpeg y
           todavía no haya recargado el PATH.

    Args:
        ruta_explicita: Ruta a ffmpeg (binario o carpeta) indicada por el usuario.

    Returns:
        Carpeta que contiene ffmpeg (apta para ``ffmpeg_location`` de yt-dlp), o
        ``None`` si no se encuentra.
    """
    candidatos: list[Path] = []

    if ruta_explicita is not None:
        candidatos.append(ruta_explicita)

    candidatos.append(paths.DIR_HERRAMIENTAS)

    en_path = shutil.which("ffmpeg")
    if en_path:
        candidatos.append(Path(en_path))

    # Ubicaciones habituales en Windows (p. ej. cuando el PATH aún no se recargó).
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        winget = Path(local_appdata) / "Microsoft" / "WinGet"
        candidatos.append(winget / "Links" / "ffmpeg.exe")
        candidatos.extend((winget / "Packages").glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"))

    for candidato in candidatos:
        # El usuario pudo indicar el binario directamente o su carpeta.
        if candidato.is_file():
            return candidato.parent
        if candidato.is_dir():
            for nombre in ("ffmpeg.exe", "ffmpeg"):
                if (candidato / nombre).is_file():
                    return candidato
    return None


_LOC_CACHE: Path | None = None
_ULTIMO_INTENTO: float = 0.0
_REINTENTO_SEGUNDOS = 30.0
_LOCK_CACHE = threading.Lock()


def localizacion() -> Path | None:
    """Localización de ffmpeg cacheada para la app.

    La búsqueda recorre el disco, así que un resultado positivo se memoriza para
    siempre. Un resultado negativo solo se cachea ``_REINTENTO_SEGUNDOS``: si el
    usuario instala ffmpeg con la app abierta, se detecta sin reiniciar. La CLI
    usa directamente ``localizar_ffmpeg`` con su propio argumento y no pasa por
    aquí.
    """
    global _LOC_CACHE, _ULTIMO_INTENTO
    with _LOCK_CACHE:
        if _LOC_CACHE is not None:
            return _LOC_CACHE
        ahora = time.monotonic()
        if _ULTIMO_INTENTO and (ahora - _ULTIMO_INTENTO) < _REINTENTO_SEGUNDOS:
            return None
        _ULTIMO_INTENTO = ahora
        _LOC_CACHE = localizar_ffmpeg()
        return _LOC_CACHE
