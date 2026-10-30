"""Rutas de la biblioteca local: listado, servido de audio y abrir carpeta."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

from ..paths import CARPETA_DESCARGAS, resolver_dentro_descargas
from ..servicios import biblioteca as servicio
from ..utils import colapsar_error
from .comun import cuerpo_json, error_json, texto

bp = Blueprint("biblioteca", __name__)


@bp.get("/api/biblioteca")
def listar():
    """Escanea la biblioteca local de MP3 y devuelve tracks + subcarpetas."""
    q = (request.args.get("q") or "").strip()
    carpeta_rel = (request.args.get("carpeta") or "").strip()
    return jsonify(servicio.escanear(q=q, carpeta_rel=carpeta_rel))


def _borrar_con_paciencia(destino: Path, intentos: int = 6, espera: float = 0.15) -> None:
    """Borra el fichero, insistiendo un momento si Windows dice que está en uso.

    El reproductor suelta la pista justo antes de pedir que se borre, pero el
    servidor puede tardar unas décimas en cerrar el fichero que le estaba
    sirviendo, y mientras tanto Windows no deja eliminarlo.
    """
    for intento in range(1, intentos + 1):
        try:
            destino.unlink()
            return
        except PermissionError:
            if intento == intentos:
                raise
            time.sleep(espera)


@bp.post("/api/biblioteca/eliminar")
def eliminar_pista():
    """Borra del disco un archivo de la biblioteca (mp3/mp4).

    Acción destructiva: elimina el fichero de forma permanente. Con validación
    estricta de path-traversal (solo dentro de descargas) y de tipo.
    """
    datos = cuerpo_json()
    rel = texto(datos, "archivo")
    if not rel:
        return error_json("Falta el archivo.")
    destino = resolver_dentro_descargas(rel)
    if destino is None or not destino.is_file():
        return error_json("Archivo no encontrado.", 404)
    if destino.suffix.lower() not in (".mp3", ".mp4"):
        return error_json("Tipo de archivo no permitido.", 403)
    try:
        _borrar_con_paciencia(destino)
    except OSError as error:
        return error_json(f"No se pudo eliminar: {colapsar_error(error)}", 500)
    servicio.olvidar_cache(destino)
    return jsonify({"ok": True})


# Tipos servibles por el reproductor y su mimetype.
_MIME_MEDIA = {".mp3": "audio/mpeg", ".mp4": "video/mp4"}


def _servir_media(rel: str):
    """Sirve un MP3/MP4 en línea (inline) con validación de path-traversal.

    Solo ficheros .mp3/.mp4 dentro de la carpeta de descargas; ``conditional``
    habilita las peticiones por rango (imprescindible para el 'seek' de vídeo).
    """
    destino = resolver_dentro_descargas(rel)
    if destino is None or not destino.is_file():
        return error_json("Fichero no encontrado.", 404)
    mimetype = _MIME_MEDIA.get(destino.suffix.lower())
    if mimetype is None:
        return error_json("Tipo de fichero no permitido.", 403)
    try:
        return send_file(
            str(destino),
            mimetype=mimetype,
            as_attachment=False,
            download_name=destino.name,
            conditional=True,
        )
    except Exception:  # noqa: BLE001
        return error_json("No se pudo servir el fichero.", 500)


@bp.get("/audio/<path:rel>")
def servir_audio(rel: str):
    """Sirve un MP3/MP4 en línea (inline) para el reproductor.

    (La ruta conserva el nombre ``/audio/`` por compatibilidad; sirve ambos.)
    """
    return _servir_media(rel)


@bp.get("/media/<path:rel>")
def servir_media(rel: str):
    """Alias semántico de ``/audio`` para el reproductor (audio o vídeo)."""
    return _servir_media(rel)


def abrir_en_explorador(destino: Path, carpeta: Path) -> None:
    """Abre ``carpeta`` en el explorador del sistema.

    Aparte del endpoint para que los tests la sustituyan (ver
    ``tests/conftest.py``): si no, cada petición válida abriría una ventana.
    """
    if os.name == "nt":
        if destino.is_file():
            # En Windows abre el Explorador y selecciona el archivo.
            subprocess.Popen(["explorer", "/select,", os.path.normpath(str(destino))])
        else:
            os.startfile(str(carpeta))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(carpeta)])
    else:
        subprocess.Popen(["xdg-open", str(carpeta)])


@bp.post("/api/abrir-carpeta")
def abrir_carpeta():
    """Abre en el explorador del sistema la carpeta que contiene un archivo de
    la biblioteca (o la raíz de descargas si no se indica archivo)."""
    datos = cuerpo_json()
    rel = texto(datos, "archivo")
    destino = resolver_dentro_descargas(rel) if rel else CARPETA_DESCARGAS
    if destino is None:
        return error_json("Ruta no permitida.", 403)
    carpeta = destino.parent if destino.is_file() else destino
    if not carpeta.exists():
        return error_json("Carpeta no encontrada.", 404)
    try:
        abrir_en_explorador(destino, carpeta)
        return jsonify({"ok": True})
    except Exception as error:  # noqa: BLE001
        return error_json(f"No se pudo abrir la carpeta: {colapsar_error(error)}", 500)
