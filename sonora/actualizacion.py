"""yt-dlp actualizable dentro del ejecutable empaquetado.

En el ``.exe``, yt-dlp va congelado en el binario y no hay pip. Para que la app
siga descargando cuando YouTube cambia (un yt-dlp viejo acaba en ``HTTP Error
403``), la versión nueva se baja de PyPI como *wheel* a la carpeta de datos del
usuario y, en el siguiente arranque, se pone delante en ``sys.path``. Un wheel
es un zip de Python puro y Python importa paquetes de un zip sin
descomprimirlo, así que el ``import yt_dlp`` de toda la app recoge la versión
nueva sin tocar el ejecutable.

Solo se usa empaquetada: en desarrollo yt-dlp se actualiza con pip (ver
``salud.actualizar_yt_dlp``). Este módulo no importa yt-dlp: ``activar()`` tiene
que correr antes del primer ``import yt_dlp`` (lo llama ``sonora/__main__.py``).
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from . import paths, salud

# Solo se acepta el wheel universal de yt-dlp, y solo del almacén de PyPI.
PATRON_WHEEL = re.compile(r"yt_dlp-(\d+(?:\.\d+)*)-py3-none-any\.whl")
HOST_DESCARGAS = "files.pythonhosted.org"

# El wheel pesa unos 3 MB; el tope evita llenar el disco con una respuesta rara.
TAMANO_MAXIMO = 50 * 1024 * 1024
TIMEOUT_DESCARGA = 120


class ErrorActualizacion(Exception):
    """La descarga no salió bien; el mensaje va tal cual a la interfaz."""


def carpeta() -> Path:
    """Dónde se guardan los wheels descargados (dentro de los datos del usuario)."""
    return paths.DIR_BASE / "yt-dlp"


def version_de(wheel: Path) -> str:
    """Versión que codifica el nombre del wheel, o '' si no es uno de los nuestros."""
    coincidencia = PATRON_WHEEL.fullmatch(wheel.name)
    return coincidencia.group(1) if coincidencia else ""


def version_incluida() -> str:
    """Versión de yt-dlp congelada en el ejecutable, sin importarlo.

    Se lee de sus metadatos, que el spec copia al empaquetar. Hay que llamarla
    antes de poner un wheel en ``sys.path``: después, los metadatos que se
    encuentran primero son los del wheel.
    """
    try:
        return importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        return ""


def _mas_nuevo(wheels: list[Path]) -> Path | None:
    elegido = None
    for wheel in wheels:
        if elegido is None or salud.hay_version_nueva(version_de(elegido), version_de(wheel)):
            elegido = wheel
    return elegido


def _borrar(ruta: Path) -> None:
    try:
        ruta.unlink()
    except OSError:
        pass  # se reintenta en el próximo arranque


def activar() -> str:
    """Pone delante en ``sys.path`` el yt-dlp descargado, si mejora al incluido.

    Devuelve la versión activada, o '' si se usa la del ejecutable. De paso
    borra lo que ya no sirve: wheels anteriores, los que no superan al incluido
    (tras instalar un Sonora más nuevo) y descargas a medias. Nunca lanza: ante
    cualquier problema, la app arranca con el yt-dlp que trae.
    """
    if not salud.empaquetada():
        return ""
    dir_wheels = carpeta()
    if not dir_wheels.is_dir():
        return ""
    try:
        wheels = [w for w in dir_wheels.glob("yt_dlp-*.whl") if version_de(w)]
        restos = list(dir_wheels.glob("*.part"))
    except OSError:
        return ""
    elegido = _mas_nuevo(wheels)
    incluida = version_incluida()
    # Sin metadatos no hay con qué comparar: mejor el descargado que ninguno.
    if elegido is not None and incluida and not salud.hay_version_nueva(
        incluida, version_de(elegido)
    ):
        elegido = None
    for sobrante in [w for w in wheels if w != elegido] + restos:
        _borrar(sobrante)
    if elegido is None:
        return ""
    sys.path.insert(0, str(elegido))
    return version_de(elegido)


def _wheel_publicado() -> tuple[str, str, str]:
    """(versión, URL, SHA-256) del wheel de la última yt-dlp publicada en PyPI."""
    peticion = urllib.request.Request(
        salud.URL_PYPI, headers={"User-Agent": "Sonora", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(peticion, timeout=salud.TIMEOUT_PYPI) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise ErrorActualizacion(f"No se pudo consultar PyPI: {error}") from error
    try:
        version = str(datos["info"]["version"])
        for fichero in datos["urls"]:
            if PATRON_WHEEL.fullmatch(str(fichero.get("filename", ""))):
                url = str(fichero["url"])
                sha256 = str(fichero["digests"]["sha256"]).lower()
                break
        else:
            raise ErrorActualizacion("PyPI no ofrece el paquete de yt-dlp esperado.")
    except (KeyError, TypeError, AttributeError) as error:
        raise ErrorActualizacion("PyPI respondió algo inesperado.") from error
    partes = urllib.parse.urlsplit(url)
    if partes.scheme != "https" or partes.hostname != HOST_DESCARGAS:
        raise ErrorActualizacion("PyPI ofrece la descarga desde un sitio inesperado.")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ErrorActualizacion("PyPI no publica la huella del paquete.")
    return version, url, sha256


def descargar() -> str:
    """Baja de PyPI la última yt-dlp y la deja lista para el próximo arranque.

    Comprueba la huella SHA-256 que publica PyPI y que el zip trae yt-dlp antes
    de darlo por bueno: hasta entonces vive como ``.part`` y ``activar()`` no lo
    mira. Devuelve la versión descargada; lanza ``ErrorActualizacion`` con un
    mensaje para la interfaz si algo falla.
    """
    version, url, sha256 = _wheel_publicado()
    dir_wheels = carpeta()
    nombre = Path(urllib.parse.urlsplit(url).path).name
    if version_de(Path(nombre)) != version:
        raise ErrorActualizacion("El paquete que ofrece PyPI no es el de la versión anunciada.")
    destino = dir_wheels / nombre
    parcial = dir_wheels / (nombre + ".part")
    try:
        dir_wheels.mkdir(parents=True, exist_ok=True)
        huella = hashlib.sha256()
        leidos = 0
        peticion = urllib.request.Request(url, headers={"User-Agent": "Sonora"})
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_DESCARGA) as respuesta, \
                open(parcial, "wb") as salida:
            while bloque := respuesta.read(64 * 1024):
                leidos += len(bloque)
                if leidos > TAMANO_MAXIMO:
                    raise ErrorActualizacion("La descarga de yt-dlp es demasiado grande.")
                huella.update(bloque)
                salida.write(bloque)
        if huella.hexdigest() != sha256:
            raise ErrorActualizacion("La descarga de yt-dlp llegó dañada: inténtalo de nuevo.")
        try:
            with zipfile.ZipFile(parcial) as wheel:
                wheel.getinfo("yt_dlp/__init__.py")
        except (zipfile.BadZipFile, KeyError) as error:
            raise ErrorActualizacion("El paquete descargado no contiene yt-dlp.") from error
        os.replace(parcial, destino)
    except ErrorActualizacion:
        _borrar(parcial)
        raise
    except (urllib.error.URLError, OSError) as error:
        _borrar(parcial)
        raise ErrorActualizacion(f"No se pudo descargar yt-dlp: {error}") from error
    return version
