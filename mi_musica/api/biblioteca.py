"""Rutas de la biblioteca local: listado, servido de audio y abrir carpeta."""

from __future__ import annotations

import os
import subprocess
import sys

from flask import Blueprint, jsonify, request, send_file

from ..paths import CARPETA_DESCARGAS, resolver_dentro_descargas
from ..servicios import biblioteca as servicio
from ..utils import colapsar_error
from .comun import cuerpo_json, error_json

bp = Blueprint("biblioteca", __name__)


@bp.get("/api/biblioteca")
def listar():
    """Escanea la biblioteca local de MP3 y devuelve tracks + subcarpetas."""
    q = (request.args.get("q") or "").strip()
    carpeta_rel = (request.args.get("carpeta") or "").strip()
    return jsonify(servicio.escanear(q=q, carpeta_rel=carpeta_rel))


def _enviar_mp3(rel: str, como_adjunto: bool):
    """Sirve un MP3 bajo descargas con validación estricta de path-traversal."""
    destino = resolver_dentro_descargas(rel)
    if destino is None or not destino.is_file():
        return error_json("Fichero no encontrado.", 404)
    if destino.suffix.lower() != ".mp3":
        return error_json("Tipo de fichero no permitido.", 403)
    try:
        return send_file(
            str(destino),
            mimetype="audio/mpeg",
            as_attachment=como_adjunto,
            download_name=destino.name,
            conditional=True,
        )
    except Exception:  # noqa: BLE001
        return error_json("No se pudo servir el fichero.", 500)


@bp.get("/audio/<path:rel>")
def servir_audio(rel: str):
    """Sirve el MP3 en línea (inline) para el reproductor."""
    return _enviar_mp3(rel, como_adjunto=False)


@bp.get("/descargas/<path:rel>")
def servir_descarga(rel: str):
    """Sirve el MP3 como adjunto (descarga al disco del usuario)."""
    return _enviar_mp3(rel, como_adjunto=True)


@bp.post("/api/abrir-carpeta")
def abrir_carpeta():
    """Abre en el explorador del sistema la carpeta que contiene un archivo de
    la biblioteca (o la raíz de descargas si no se indica archivo)."""
    datos = cuerpo_json()
    rel = (datos.get("archivo") or "").strip()
    destino = resolver_dentro_descargas(rel) if rel else CARPETA_DESCARGAS
    if destino is None:
        return error_json("Ruta no permitida.", 403)
    carpeta = destino.parent if destino.is_file() else destino
    if not carpeta.exists():
        return error_json("Carpeta no encontrada.", 404)
    try:
        if os.name == "nt":
            if destino.is_file():
                # En Windows abre el Explorador y selecciona el archivo.
                subprocess.Popen(["explorer", "/select,", os.path.normpath(str(destino))])
            else:
                os.startfile(str(carpeta))  # noqa: S606 - ruta validada bajo descargas
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(carpeta)])
        else:
            subprocess.Popen(["xdg-open", str(carpeta)])
        return jsonify({"ok": True})
    except Exception as error:  # noqa: BLE001
        return error_json(f"No se pudo abrir la carpeta: {colapsar_error(error)}", 500)
