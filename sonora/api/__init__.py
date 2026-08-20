"""Blueprints HTTP de «Sonora».

Cada módulo define un ``Blueprint`` con rutas de path absoluto (``/api/...``).
``registrar_blueprints`` los engancha todos a la aplicación.
"""

from __future__ import annotations

from flask import Flask

from . import biblioteca, busqueda, carpetas, config, cola, eventos, vistas

_MODULOS = (vistas, busqueda, cola, eventos, biblioteca, carpetas, config)


def registrar_blueprints(app: Flask) -> None:
    """Registra todos los blueprints de la API en la aplicación."""
    for modulo in _MODULOS:
        app.register_blueprint(modulo.bp)
