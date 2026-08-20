"""Chequeo de salud del entorno: yt-dlp, ffmpeg y runtime de JavaScript.

Sirve para prevenir el fallo más habitual de la app: un yt-dlp viejo deja de
superar las protecciones de YouTube y las descargas mueren con ``HTTP Error
403: Forbidden``. Al abrir la app se comprueba si hay una versión más nueva en
PyPI y, si la hay, la interfaz ofrece actualizar en un clic.

No importa Flask ni yt-dlp al cargarse (la versión se lee de forma perezosa),
de modo que la CLI puede usarlo sin arrastrar la app entera. La consulta a PyPI
usa solo la biblioteca estándar.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from . import ffmpeg
from .ydl_opts import RUNTIMES_JS, detectar_runtime_js

URL_PYPI = "https://pypi.org/pypi/yt-dlp/json"

# Tiempo máximo de espera de PyPI. Corto a propósito: es una comprobación
# accesoria, y sin red la app tiene que abrirse igual de rápido.
TIMEOUT_PYPI = 6.0

# Cuánto vale una consulta a PyPI antes de repetirla. La app se abre y cierra
# muchas veces al día; sin esto, cada arranque golpearía PyPI sin necesidad.
TTL_CACHE = 6 * 3600.0

# Margen de antigüedad a partir del cual yt-dlp avisa de que la versión es
# vieja. Se replica aquí para poder avisar aunque PyPI no conteste.
DIAS_PARA_CADUCAR = 90

# Tope de espera de 'pip install --upgrade'. Generoso: descarga de la red.
TIMEOUT_PIP = 300

_cache_pypi: tuple[float, str] | None = None
_LOCK_CACHE = threading.Lock()


def empaquetada() -> bool:
    """Indica si corremos dentro del ejecutable de PyInstaller.

    Importa porque ahí yt-dlp va **congelado** dentro del binario: pip no puede
    actualizarlo y la única salida es reconstruir el ejecutable.
    """
    return bool(getattr(sys, "frozen", False))


def version_instalada() -> str:
    """Versión de yt-dlp instalada, o '' si no se puede determinar."""
    try:
        import yt_dlp  # noqa: PLC0415 - perezoso: este módulo no debe exigirlo

        return str(yt_dlp.version.__version__)
    except Exception:  # noqa: BLE001 - sin yt-dlp el resto del chequeo sigue
        return ""


def _tupla_version(version: str) -> tuple[int, ...]:
    """Convierte '2026.08.19' en (2026, 8, 19) para poder comparar.

    Tolerante con las versiones de desarrollo de yt-dlp
    ('2026.08.19.232030') y con cualquier sufijo no numérico, que se ignora:
    ante algo irreconocible devuelve una tupla vacía y el llamador trata la
    comparación como no concluyente en vez de dar un falso positivo.
    """
    partes: list[int] = []
    for trozo in str(version or "").split("."):
        trozo = trozo.strip()
        if not trozo.isdigit():
            break
        partes.append(int(trozo))
    return tuple(partes)


def hay_version_nueva(instalada: str, ultima: str) -> bool:
    """Indica si ``ultima`` es estrictamente posterior a ``instalada``."""
    v_inst = _tupla_version(instalada)
    v_ult = _tupla_version(ultima)
    if not v_inst or not v_ult:
        return False
    return v_ult > v_inst


def dias_de_antiguedad(version: str) -> int:
    """Días transcurridos desde la fecha que codifica la versión de yt-dlp.

    yt-dlp versiona por fecha ('2026.08.19'), así que la propia versión dice
    cuándo se publicó. Devuelve -1 si no se puede interpretar.
    """
    partes = _tupla_version(version)
    if len(partes) < 3:
        return -1
    try:
        import datetime  # noqa: PLC0415 - solo hace falta aquí

        publicada = datetime.date(partes[0], partes[1], partes[2])
    except (ValueError, TypeError):
        return -1
    return max(0, (datetime.date.today() - publicada).days)


def ultima_version_pypi(forzar: bool = False) -> str:
    """Última versión estable de yt-dlp publicada en PyPI, o '' si falla.

    El resultado se cachea ``TTL_CACHE``. Nunca lanza: sin conexión, con PyPI
    caído o con una respuesta inesperada devuelve '' y el chequeo se limita a
    lo que puede saber sin red.
    """
    global _cache_pypi
    with _LOCK_CACHE:
        if not forzar and _cache_pypi is not None:
            momento, valor = _cache_pypi
            if (time.monotonic() - momento) < TTL_CACHE:
                return valor
    version = ""
    try:
        peticion = urllib.request.Request(
            URL_PYPI,
            headers={"User-Agent": "Sonora", "Accept": "application/json"},
        )
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_PYPI) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
        version = str(datos.get("info", {}).get("version", "") or "")
    except (urllib.error.URLError, OSError, ValueError, TypeError):
        version = ""
    if version:
        with _LOCK_CACHE:
            _cache_pypi = (time.monotonic(), version)
    return version


def estado(consultar_red: bool = True) -> dict:
    """Fotografía del entorno para que la interfaz avise de lo que falta.

    ``consultar_red=False`` evita la consulta a PyPI (útil en tests y para un
    chequeo instantáneo): entonces solo se informa de la antigüedad.
    """
    instalada = version_instalada()
    ultima = ultima_version_pypi() if consultar_red else ""
    antiguedad = dias_de_antiguedad(instalada)
    nueva = hay_version_nueva(instalada, ultima)
    runtime = detectar_runtime_js()
    return {
        "yt_dlp": {
            "instalada": instalada,
            "ultima": ultima,
            "hay_actualizacion": nueva,
            "dias": antiguedad,
            # Vieja de más aunque PyPI no conteste: mismo criterio que yt-dlp.
            "caducada": antiguedad >= DIAS_PARA_CADUCAR,
            # Congelado dentro del .exe: pip no puede tocarlo.
            "actualizable": not empaquetada(),
        },
        "ffmpeg": {"disponible": ffmpeg.localizacion() is not None},
        "runtime_js": {"nombre": runtime or "", "disponible": runtime is not None,
                       "soportados": list(RUNTIMES_JS)},
        "empaquetada": empaquetada(),
    }


def actualizar_yt_dlp() -> dict:
    """Actualiza yt-dlp con pip. Devuelve ``{ok, mensaje, version}``.

    Se invoca a pip como módulo del intérprete actual (``sys.executable -m
    pip``) y sin shell: los argumentos son fijos, nada procede del usuario.

    Nota: el yt-dlp ya importado sigue en memoria, así que la versión nueva no
    entra en vigor hasta reiniciar la app; el mensaje lo deja claro.
    """
    if empaquetada():
        return {
            "ok": False,
            "mensaje": (
                "La app empaquetada lleva yt-dlp dentro del ejecutable: no se "
                "puede actualizar desde aquí, hay que reconstruirla."
            ),
            "version": version_instalada(),
        }
    try:
        proceso = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_PIP,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "mensaje": "La actualización tardó demasiado.",
                "version": version_instalada()}
    except OSError as error:
        return {"ok": False, "mensaje": f"No se pudo ejecutar pip: {error}",
                "version": version_instalada()}

    if proceso.returncode != 0:
        salida = (proceso.stderr or proceso.stdout or "").strip()
        # Última línea: pip resume ahí el error y el diálogo no da para más.
        detalle = salida.splitlines()[-1] if salida else "error desconocido"
        return {"ok": False, "mensaje": f"pip falló: {detalle}",
                "version": version_instalada()}

    # La versión recién instalada se lee de PyPI (la cacheada), no del proceso
    # en marcha: 'import yt_dlp' seguiría devolviendo la vieja hasta reiniciar.
    nueva = ultima_version_pypi(forzar=True) or ""
    return {
        "ok": True,
        "mensaje": "yt-dlp actualizado. Reinicia Sonora para usar la versión nueva.",
        "version": nueva,
    }
