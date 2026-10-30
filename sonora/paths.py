"""Rutas de datos y recursos, y validación de rutas (anti path-traversal).

Funciona tanto en desarrollo como empaquetado con PyInstaller:

* ``DIR_BASE``        Carpeta de datos del usuario (descargas + base de datos).
                      En desarrollo es ``datos/`` en la raíz del repositorio,
                      para no mezclar datos personales con el código;
                      empaquetado, la carpeta de datos del usuario
                      (``%LOCALAPPDATA%/Sonora`` en Windows), que siempre es
                      escribible aunque el .exe viva en una ruta protegida
                      como ``Program Files``.
* ``RUTA_RECURSOS``   Carpeta con ``templates/`` y ``static/``. En desarrollo es
                      el propio paquete; empaquetado, ``sys._MEIPASS``.
* ``DIR_HERRAMIENTAS`` Programas que viajan con el ejecutable (ffmpeg, ffprobe
                      y deno), para que funcione sin instalar nada. Solo existe
                      empaquetado; en desarrollo se usan los del sistema.

Este módulo no crea directorios al importarse: ``preparar_directorios()`` lo
hace explícitamente desde ``factory.preparar()``, con un error claro si falla.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _dir_paquete() -> Path:
    """Carpeta del paquete ``sonora`` (donde vive este fichero)."""
    return Path(__file__).resolve().parent


def _dir_datos_usuario() -> Path:
    """Carpeta de datos por usuario, según la plataforma."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "Sonora"
        return Path.home() / "AppData" / "Local" / "Sonora"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Sonora"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "sonora"
    return Path.home() / ".local" / "share" / "sonora"


def _calcular_dir_base() -> Path:
    """Carpeta de datos (descargas + base de datos)."""
    if getattr(sys, "frozen", False):
        return _dir_datos_usuario()
    # Desarrollo: carpeta 'datos/' en la raíz del repositorio (la que contiene
    # el paquete). Mantiene la música y la BD fuera del árbol de código.
    return _dir_paquete().parent / "datos"


def _dir_datos_antiguo() -> Path:
    """Ubicación donde las versiones anteriores guardaban los datos.

    Empaquetado, junto al ``.exe``; en desarrollo, la raíz del repositorio
    (antes de que los datos se agruparan en ``datos/``).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _dir_paquete().parent


def _calcular_ruta_recursos() -> Path:
    """Carpeta donde están ``templates/`` y ``static/`` (dentro del paquete)."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base)
    return _dir_paquete()


DIR_BASE = _calcular_dir_base()
CARPETA_DESCARGAS = DIR_BASE / "descargas"
DB_PATH = DIR_BASE / "biblioteca.db"
RUTA_RECURSOS = _calcular_ruta_recursos()
# La rellena scripts/construir.py (ver scripts/sonora.spec).
DIR_HERRAMIENTAS = RUTA_RECURSOS / "bin"


def _volcar_wal(db_antigua: Path) -> None:
    """Vuelca a la BD el WAL pendiente antes de moverla de sitio.

    La versión antigua usaba ``journal_mode=WAL`` y no cerraba la conexión al
    salir, así que junto al ``.db`` suele quedar un ``-wal`` con transacciones
    aún no volcadas (cola, historial, configuración). Mover solo el ``.db``
    perdería esos datos en silencio.
    """
    import sqlite3

    try:
        conexion = sqlite3.connect(str(db_antigua))
        try:
            conexion.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        finally:
            conexion.close()
    except sqlite3.Error:
        pass


def _migrar_datos_antiguos() -> None:
    """Migra los datos de versiones anteriores a la ubicación actual.

    Las versiones anteriores escribían ``biblioteca.db`` y ``descargas/`` junto
    al ejecutable (empaquetado) o en la raíz del repositorio (desarrollo). Si
    existen allí y aún no hay datos en la ubicación nueva, se mueven. Cualquier
    fallo se ignora: la app arranca con datos vacíos antes que no arrancar.
    """
    import shutil

    antigua = _dir_datos_antiguo()
    if antigua == DIR_BASE:
        return
    try:
        db_antigua = antigua / "biblioteca.db"
        if db_antigua.is_file() and not DB_PATH.exists():
            _volcar_wal(db_antigua)
            shutil.move(str(db_antigua), str(DB_PATH))
            # Por si el checkpoint no pudo completarse, los ficheros auxiliares
            # viajan con la BD (SQLite los recoge al abrirla en el destino).
            for sufijo in ("-wal", "-shm"):
                aux = antigua / ("biblioteca.db" + sufijo)
                if aux.is_file():
                    shutil.move(str(aux), str(DB_PATH) + sufijo)
        descargas_antigua = antigua / "descargas"
        if descargas_antigua.is_dir() and not any(CARPETA_DESCARGAS.iterdir()):
            for hijo in descargas_antigua.iterdir():
                destino = CARPETA_DESCARGAS / hijo.name
                if not destino.exists():
                    shutil.move(str(hijo), str(destino))
    except OSError:
        pass


def preparar_directorios() -> None:
    """Crea las carpetas de datos y migra datos antiguos si procede.

    Lanza ``OSError`` con la ruta implicada si no se pueden crear: mejor un
    error claro en el arranque que fallos extraños después.
    """
    DIR_BASE.mkdir(parents=True, exist_ok=True)
    CARPETA_DESCARGAS.mkdir(parents=True, exist_ok=True)
    _migrar_datos_antiguos()


def resolver_dentro_descargas(rel: str) -> Path | None:
    """Resuelve una ruta relativa garantizando que queda dentro de descargas.

    Devuelve la ruta absoluta resuelta si es válida (no escapa de
    ``CARPETA_DESCARGAS``), o ``None`` si intenta salirse (path-traversal) o es
    inválida. Normaliza barras invertidas para tratar igual ``\\`` y ``/``.
    """
    rel = (rel or "").strip().replace("\\", "/").strip("/")
    base = CARPETA_DESCARGAS.resolve()
    try:
        candidato = (base / rel).resolve()
    except (OSError, ValueError):
        return None
    # Permitimos la propia base ('' -> base) y cualquier descendiente.
    if candidato == base:
        return candidato
    if base in candidato.parents:
        return candidato
    return None


def rel_descargas(ruta: Path) -> str:
    """Ruta relativa (con separadores '/') de un fichero bajo descargas."""
    try:
        rel = ruta.resolve().relative_to(CARPETA_DESCARGAS.resolve())
    except ValueError:
        return ""
    return rel.as_posix()
