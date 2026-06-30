"""Vistas HTML: la página principal de la app."""

from __future__ import annotations

from flask import Blueprint, render_template

bp = Blueprint("vistas", __name__)


@bp.get("/")
def index():
    """Página principal: renderiza la interfaz de «Mi Música»."""
    return render_template("index.html")
