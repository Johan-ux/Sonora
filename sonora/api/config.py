"""Rutas de configuración (carpeta, formato y calidad por defecto)."""

from __future__ import annotations

from flask import Blueprint, jsonify

from .. import db, ffmpeg
from ..ydl_opts import normalizar_bitrate, normalizar_formato, normalizar_resolucion
from .comun import cuerpo_json, ruta_relativa, texto

bp = Blueprint("config", __name__)


@bp.get("/api/config")
def obtener():
    """Devuelve la configuración persistida (carpeta, formato y calidad).

    Incluye ``ffmpeg_disponible`` para que el frontend avise si falta ffmpeg
    (sin él la conversión a MP3 o la fusión de vídeo fallarían con un error
    poco claro).
    """
    return jsonify({
        "carpeta_por_defecto": db.config_obtener("carpeta_por_defecto", ""),
        "bitrate_por_defecto": db.config_obtener("bitrate_por_defecto", "320") or "320",
        "formato_por_defecto": db.config_obtener("formato_por_defecto", "audio") or "audio",
        "resolucion_por_defecto": db.config_obtener("resolucion_por_defecto", "1080") or "1080",
        "ffmpeg_disponible": ffmpeg.localizacion() is not None,
    })


@bp.post("/api/config")
def guardar():
    """Guarda la configuración (campos opcionales: carpeta, bitrate, formato…)."""
    datos = cuerpo_json()
    if "carpeta_por_defecto" in datos:
        db.config_guardar("carpeta_por_defecto", ruta_relativa(datos, "carpeta_por_defecto"))
    if "bitrate_por_defecto" in datos:
        db.config_guardar(
            "bitrate_por_defecto",
            normalizar_bitrate(texto(datos, "bitrate_por_defecto")),
        )
    if "formato_por_defecto" in datos:
        db.config_guardar(
            "formato_por_defecto",
            normalizar_formato(texto(datos, "formato_por_defecto")),
        )
    if "resolucion_por_defecto" in datos:
        db.config_guardar(
            "resolucion_por_defecto",
            normalizar_resolucion(texto(datos, "resolucion_por_defecto")),
        )
    return jsonify({"ok": True})
