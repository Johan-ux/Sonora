"""Rutas del chequeo de entorno (versión de yt-dlp, ffmpeg y runtime de JS)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from .. import db, salud
from ..servicios import descargas

bp = Blueprint("salud", __name__)

# Clave de configuración donde se guarda la última consulta a PyPI
# («momento|versión»), para no repetirla en cada arranque.
CLAVE_PYPI = "salud_pypi"

# Rutas que ponen a trabajar a yt-dlp. Después de actualizarlo con la app
# abierta quedan cerradas hasta reiniciar (ver ``salud.reinicio_pendiente``).
RUTAS_CON_YT_DLP = (
    "/api/buscar",
    "/api/cola/descargar",
    "/api/cola/reintentar",
    "/api/previa/",
    "/previa/",
)


@bp.before_app_request
def _cerrar_el_paso_tras_actualizar():
    """Responde 409 a lo que necesita yt-dlp mientras falte reiniciar."""
    if salud.reinicio_pendiente() and request.path.startswith(RUTAS_CON_YT_DLP):
        return jsonify({"error": salud.MENSAJE_REINICIO}), 409
    return None


def _recuperar_consulta_guardada() -> None:
    """Carga la consulta a PyPI de una sesión anterior, si aún no hay ninguna."""
    if salud.cache_pypi() is not None:
        return
    momento, _, version = db.config_obtener(CLAVE_PYPI, "").partition("|")
    try:
        salud.recordar_pypi(float(momento), version)
    except ValueError:
        pass  # nunca se guardó, o el valor no se entiende: se consultará


@bp.get("/api/salud")
def obtener():
    """Estado del entorno para el aviso de la interfaz.

    Consulta PyPI (con caché y tiempo de espera corto) salvo que se pida
    ``?red=0``, que devuelve solo lo averiguable sin conexión.
    """
    consultar_red = request.args.get("red", "1") != "0"
    if consultar_red:
        _recuperar_consulta_guardada()
    antes = salud.cache_pypi()
    resultado = salud.estado(consultar_red=consultar_red)
    despues = salud.cache_pypi()
    if despues is not None and despues != antes:
        db.config_guardar(CLAVE_PYPI, f"{despues[0]}|{despues[1]}")
    return jsonify(resultado)


@bp.post("/api/salud/actualizar")
def actualizar():
    """Actualiza yt-dlp con pip y devuelve el resultado.

    Responde 409 si no se pudo actualizar (app empaquetada, pip falló, sin
    red, descargas en marcha…): no es un fallo del servidor, es que la
    operación no procede o no salió bien, y el frontend lo muestra tal cual.
    """
    if descargas.hay_tanda_en_marcha():
        # pip reemplaza los ficheros de yt-dlp bajo los pies de quien los usa.
        resultado = {
            "ok": False,
            "mensaje": (
                "Hay descargas en marcha: espera a que terminen o cancélalas "
                "antes de actualizar."
            ),
            "version": salud.version_instalada(),
        }
    else:
        resultado = salud.actualizar_yt_dlp()
    if resultado.get("ok"):
        return jsonify(resultado)
    # 'error' además de 'mensaje': es la clave que el frontend usa para
    # construir el texto de las respuestas fallidas.
    resultado["error"] = resultado.get("mensaje", "No se pudo actualizar.")
    return jsonify(resultado), 409
