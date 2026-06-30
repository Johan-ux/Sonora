"""Rutas de datos y recursos, y validación de rutas (anti path-traversal).

Funciona tanto en desarrollo como empaquetado con PyInstaller:

* ``DIR_BASE``        Carpeta de datos del usuario (descargas + base de datos).
                      En desarrollo es la raíz del repositorio (la que contiene
                      el paquete ``mi_musica``); empaquetado, la del ejecutable.
* ``RUTA_RECURSOS``   Carpeta con ``templates/`` y ``static/``. En desarrollo es
                      el propio paquete; empaquetado, ``sys._MEIPASS``.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _dir_paquete() -> Path:
    """Carpeta del paquete ``mi_musica`` (donde vive este fichero)."""
    return Path(__file__).resolve().parent


def _calcular_dir_base() -> Path:
    """Carpeta de datos (descargas + base de datos)."""
    if getattr(sys, "frozen", False):
        # Empaquetado: los datos viven junto al .exe.
        return Path(sys.executable).resolve().parent
    # Desarrollo: la raíz del repositorio (carpeta que contiene el paquete).
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

# Aseguramos que la carpeta de descargas exista desde el arranque.
CARPETA_DESCARGAS.mkdir(parents=True, exist_ok=True)


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
