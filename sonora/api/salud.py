"""Rutas del chequeo de entorno (versión de yt-dlp, ffmpeg y runtime de JS)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from .. import salud

bp = Blueprint("salud", __name__)


@bp.get("/api/salud")
def obtener():
    """Estado del entorno para el aviso de la interfaz.

    Consulta PyPI (con caché y tiempo de espera corto) salvo que se pida
    ``?red=0``, que devuelve solo lo averiguable sin conexión.
    """
    consultar_red = request.args.get("red", "1") != "0"
    return jsonify(salud.estado(consultar_red=consultar_red))


@bp.post("/api/salud/actualizar")
def actualizar():
    """Actualiza yt-dlp con pip y devuelve el resultado.

    Responde 409 si no se pudo actualizar (app empaquetada, pip falló, sin
    red…): no es un fallo del servidor, es que la operación no procede o no
    salió bien, y el frontend lo muestra tal cual.
    """
    resultado = salud.actualizar_yt_dlp()
    if resultado.get("ok"):
        return jsonify(resultado)
    # 'error' además de 'mensaje': es la clave que el frontend usa para
    # construir el texto de las respuestas fallidas.
    resultado["error"] = resultado.get("mensaje", "No se pudo actualizar.")
    return jsonify(resultado), 409
