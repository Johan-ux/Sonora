"""Application factory de «Mi Música».

``crear_app()`` construye y devuelve la aplicación Flask ya inicializada; el
lanzamiento real de la ventana de escritorio (pywebview + puerto libre) lo hace
``desktop.py``. ``preparar()`` inicializa la base de datos y es idempotente.
"""

from __future__ import annotations

import threading

from flask import Flask

from . import db
from .api import registrar_blueprints
from .paths import CARPETA_DESCARGAS, DB_PATH, RUTA_RECURSOS

_INICIALIZADO = False
_LOCK_INIT = threading.Lock()


def preparar() -> None:
    """Inicializa la base de datos y limpia descargas interrumpidas.

    Es idempotente y seguro de llamar varias veces. ``crear_app`` lo invoca antes
    de devolver la aplicación, de modo que la BD esté lista antes de servir.
    """
    global _INICIALIZADO
    with _LOCK_INIT:
        if _INICIALIZADO:
            return
        db.inicializar(DB_PATH)
        # Descargas que quedaron 'descargando' por un cierre inesperado vuelven a
        # 'en_cola' para reintentarse.
        try:
            db.cola_reiniciar_descargando()
        except Exception:  # noqa: BLE001
            pass
        CARPETA_DESCARGAS.mkdir(parents=True, exist_ok=True)
        _INICIALIZADO = True


def crear_app() -> Flask:
    """Crea la aplicación Flask, inicializa la BD y registra los blueprints."""
    preparar()
    app = Flask(
        "mi_musica",
        template_folder=str(RUTA_RECURSOS / "templates"),
        static_folder=str(RUTA_RECURSOS / "static"),
    )
    registrar_blueprints(app)
    return app


if __name__ == "__main__":
    # Servidor de desarrollo simple (sin abrir ventana). El lanzamiento real de
    # la app de escritorio lo hace desktop.py.
    import os

    aplicacion = crear_app()
    puerto = int(os.environ.get("PUERTO", "5000"))
    print(f"Servidor de desarrollo en http://127.0.0.1:{puerto}")
    aplicacion.run(host="127.0.0.1", port=puerto, debug=False, use_reloader=False, threaded=True)
