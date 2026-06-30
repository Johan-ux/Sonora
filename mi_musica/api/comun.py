"""Helpers comunes a los blueprints (respuestas y lectura del cuerpo JSON)."""

from __future__ import annotations

from flask import jsonify, request


def error_json(mensaje: str, status: int = 400):
    """Respuesta JSON de error estándar con el código de estado indicado."""
    return jsonify({"error": mensaje}), status


def cuerpo_json() -> dict:
    """Lee el cuerpo JSON de la petición de forma tolerante (nunca lanza)."""
    datos = request.get_json(silent=True)
    return datos if isinstance(datos, dict) else {}
