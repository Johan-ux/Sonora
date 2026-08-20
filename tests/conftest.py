"""Fixtures compartidas de la suite de tests de Sonora.

Enfoque elegido (documentado, tal y como pide la misión):

* NO usamos ``sonora.factory.crear_app()``: tiene un flag global
  ``_INICIALIZADO`` y llamaría a ``paths.preparar_directorios()`` /
  ``db.inicializar(DB_PATH)`` contra las rutas REALES del repo (``paths.py``
  calcula ``DIR_BASE``/``CARPETA_DESCARGAS``/``DB_PATH`` al importarse).
  En su lugar:

  1. ``sonora.db`` se inicializa directamente contra una BD temporal por test
     (``db.inicializar(tmp_path / "test.db")`` es idempotente y re-abre la
     conexión, así que cada test parte de una BD limpia).
  2. ``CARPETA_DESCARGAS`` se monkeypatchea hacia ``tmp_path / "descargas"``.
     Como varios módulos hacen ``from ..paths import CARPETA_DESCARGAS``
     (copian la referencia en SU espacio de nombres), hay que parchear tanto
     ``sonora.paths`` como cada módulo que la importó:
     ``sonora.servicios.biblioteca``, ``sonora.servicios.descargas``,
     ``sonora.api.carpetas`` y ``sonora.api.biblioteca``.
     Las funciones ``resolver_dentro_descargas`` / ``rel_descargas`` leen la
     global de ``sonora.paths`` en tiempo de llamada, así que con parchear el
     módulo ``sonora.paths`` esas funciones ya quedan redirigidas.
  3. La app Flask de test se construye a mano registrando los blueprints con
     ``sonora.api.registrar_blueprints`` (sin tocar el factory ni su flag).

* El worker de descargas NUNCA se arranca en los tests: no se llama a
  ``/api/cola/descargar`` y en ``tests/test_api.py`` hay un autouse fixture
  que deja ``sonora.servicios.descargas.arrancar_worker`` en no-op.

* Los endpoints de cola emiten SSE (``sonora.sse.emitir``); sin clientes
  conectados es un no-op seguro, no hace falta mockear nada.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from flask import Flask

# Garantiza que el paquete `sonora` sea importable aunque pytest se lance
# desde otro directorio (p. ej. en CI).
RAIZ_REPO = Path(__file__).resolve().parent.parent
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

from sonora import db  # noqa: E402


@pytest.fixture()
def entorno(tmp_path, monkeypatch):
    """BD temporal inicializada + CARPETA_DESCARGAS parcheada a tmp_path.

    Devuelve la ruta de la carpeta de descargas temporal.
    """
    descargas_dir = tmp_path / "descargas"
    descargas_dir.mkdir()

    # Import tardío para que el fixture sea el único punto donde se parchea.
    import sonora.api.biblioteca
    import sonora.api.carpetas
    import sonora.paths
    import sonora.servicios.biblioteca
    import sonora.servicios.descargas

    for modulo in (
        sonora.paths,                  # la global "de verdad" (usada por las funciones)
        sonora.servicios.biblioteca,   # from ..paths import CARPETA_DESCARGAS
        sonora.servicios.descargas,    # idem
        sonora.api.carpetas,           # idem
        sonora.api.biblioteca,         # idem
    ):
        monkeypatch.setattr(modulo, "CARPETA_DESCARGAS", descargas_dir)

    # BD temporal por test. inicializar() es idempotente: cierra la conexión
    # anterior y abre una nueva contra la ruta indicada.
    db.inicializar(tmp_path / "test.db")

    yield descargas_dir

    # Teardown: cerramos la conexión para no dejar el fichero .db bloqueado
    # (relevante en Windows, donde un fichero abierto no se puede borrar).
    with db._lock:
        if db._conexion is not None:
            try:
                db._conexion.close()
            except Exception:  # noqa: BLE001 - el teardown nunca debe fallar
                pass
            db._conexion = None


@pytest.fixture()
def app(entorno):
    """App Flask de test con todos los blueprints registrados.

    Se crea a mano (sin ``sonora.factory.crear_app``) para no disparar el flag
    global ``_INICIALIZADO`` ni tocar las rutas reales del repositorio.
    """
    from sonora.api import registrar_blueprints
    from sonora.factory import _bloquear_peticiones_externas
    from sonora.paths import RUTA_RECURSOS

    aplicacion = Flask(
        "sonora-test",
        template_folder=str(RUTA_RECURSOS / "templates"),
        static_folder=str(RUTA_RECURSOS / "static"),
    )
    aplicacion.config["TESTING"] = True
    # El mismo guard que instala crear_app(): sin él, los tests correrían
    # contra una app distinta de la real y no verían un fallo de origen.
    aplicacion.before_request(_bloquear_peticiones_externas)
    registrar_blueprints(aplicacion)
    return aplicacion


@pytest.fixture()
def client(app):
    """Test client HTTP de Flask."""
    return app.test_client()
