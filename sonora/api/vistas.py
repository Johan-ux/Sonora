"""Vistas HTML: la página principal de la app."""

from __future__ import annotations

from flask import Blueprint, render_template

from .. import __version__, db, salud
from .config import normalizar_tema

bp = Blueprint("vistas", __name__)


@bp.get("/")
def index():
    """Página principal: renderiza la interfaz de «Sonora».

    El tema de color va ya puesto en el HTML (``<html data-tema>``): si lo
    aplicase el JavaScript al cargar la configuración, la ventana abriría con
    el de fábrica y saltaría al elegido.
    """
    tema = normalizar_tema(db.config_obtener("tema", ""))
    return render_template(
        "index.html", tema=tema, version=__version__, instalar=salud.ordenes_instalar()
    )
