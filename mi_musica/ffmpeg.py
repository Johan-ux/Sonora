"""Localización robusta del ejecutable de ffmpeg.

Compartida por la CLI (``descargar_musica.py``) y por la app de escritorio. No
depende de Flask ni de yt-dlp, de modo que la CLI puede importarla sin arrastrar
el resto del paquete.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def localizar_ffmpeg(ruta_explicita: Path | None = None) -> Path | None:
    """Localiza el ejecutable de ffmpeg de forma robusta.

    Orden de búsqueda:
        1. Ruta indicada explícitamente.
        2. El PATH del sistema (``shutil.which``).
        3. Ubicaciones habituales en Windows, incluida la de winget. Esto permite
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
_LOC_CALCULADA = False


def localizacion() -> Path | None:
    """Localización de ffmpeg cacheada para la app (se calcula una sola vez).

    La búsqueda recorre el disco, así que la memorizamos. La CLI usa directamente
    ``localizar_ffmpeg`` con su propio argumento y no pasa por aquí.
    """
    global _LOC_CACHE, _LOC_CALCULADA
    if not _LOC_CALCULADA:
        _LOC_CACHE = localizar_ffmpeg()
        _LOC_CALCULADA = True
    return _LOC_CACHE
