"""Rutas de configuración (carpeta y bitrate por defecto)."""

from __future__ import annotations

from flask import Blueprint, jsonify

from .. import db, ffmpeg
from .comun import cuerpo_json

bp = Blueprint("config", __name__)


@bp.get("/api/config")
def obtener():
    """Devuelve la configuración persistida (carpeta y bitrate por defecto).

    Incluye ``ffmpeg_disponible`` para que el frontend avise si falta ffmpeg
    (sin él la conversión a MP3 fallaría con un error poco claro).
    """
    return jsonify({
        "carpeta_por_defecto": db.config_obtener("carpeta_por_defecto", ""),
        "bitrate_por_defecto": db.config_obtener("bitrate_por_defecto", "320") or "320",
        "ffmpeg_disponible": ffmpeg.localizacion() is not None,
    })


@bp.post("/api/config")
def guardar():
    """Guarda la configuración (campos opcionales: carpeta y/o bitrate)."""
    datos = cuerpo_json()
    if "carpeta_por_defecto" in datos:
        carpeta = (datos.get("carpeta_por_defecto") or "").strip().replace("\\", "/").strip("/")
        db.config_guardar("carpeta_por_defecto", carpeta)
    if "bitrate_por_defecto" in datos:
        bitrate = str(datos.get("bitrate_por_defecto") or "320")
        if bitrate not in ("128", "192", "256", "320"):
            bitrate = "320"
        db.config_guardar("bitrate_por_defecto", bitrate)
    return jsonify({"ok": True})
