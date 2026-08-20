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


def texto(datos: dict, clave: str, por_defecto: str = "") -> str:
    """Extrae ``datos[clave]`` como cadena recortada, tolerante a tipos.

    Un cliente (o un curl manual) puede mandar números, null, listas… donde
    esperamos texto; sin esto, un ``.strip()`` sobre un int provoca un 500 HTML
    sin capturar. None y los tipos no escalares devuelven ``por_defecto``.
    """
    valor = datos.get(clave, por_defecto)
    if valor is None:
        return por_defecto
    if isinstance(valor, (str, int, float)):
        return str(valor).strip()
    return por_defecto


def ruta_relativa(datos: dict, clave: str) -> str:
    """Extrae una ruta relativa normalizada (separadores '/', sin extremos)."""
    return texto(datos, clave).replace("\\", "/").strip("/")
