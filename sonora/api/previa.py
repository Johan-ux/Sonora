"""Rutas del reproductor propio de la vista previa (respaldo del de YouTube)."""

from __future__ import annotations

import webbrowser

from flask import Blueprint, Response, jsonify, request

from ..servicios import previa
from ..utils import colapsar_error
from .comun import cuerpo_json, error_json, texto

bp = Blueprint("previa", __name__)

_BLOQUE = 64 * 1024


@bp.get("/api/previa/<video_id>")
def info(video_id: str):
    """Prepara la reproducción propia de un vídeo y devuelve su duración.

    La interfaz lo pide antes de crear el ``<video>``: el flujo no dice cuánto
    dura (se escribe sobre la marcha), y sin la duración no hay barra de
    posición que pintar.
    """
    if not previa.es_id_valido(video_id):
        return error_json("Identificador de vídeo no válido.")
    try:
        flujo = previa.resolver(video_id)
    except Exception as error:  # noqa: BLE001
        return error_json(f"No se pudo preparar el vídeo: {colapsar_error(error)}", 502)
    return jsonify({"duracion": flujo["duracion"]})


@bp.get("/previa/<video_id>.mp4")
def flujo(video_id: str):
    """Sirve el vídeo como MP4 fragmentado, desde el segundo ``t`` si se indica."""
    if not previa.es_id_valido(video_id):
        return error_json("Identificador de vídeo no válido.")
    try:
        inicio = max(0.0, float(request.args.get("t") or 0))
    except ValueError:
        inicio = 0.0
    try:
        proceso = previa.abrir_flujo(video_id, inicio)
    except Exception as error:  # noqa: BLE001
        return error_json(f"No se pudo reproducir: {colapsar_error(error)}", 502)

    def generar():
        try:
            while True:
                # read1: lo que haya ya, sin esperar a llenar el bloque.
                bloque = proceso.stdout.read1(_BLOQUE)
                if not bloque:
                    break
                yield bloque
        finally:
            # Se llega aquí al terminar y también cuando la ventana deja de
            # leer (se cerró la vista previa o se saltó a otro punto): sin
            # esto ffmpeg seguiría bajando el vídeo para nadie.
            proceso.kill()
            proceso.wait()

    return Response(generar(), mimetype="video/mp4", headers={"Cache-Control": "no-store"})


@bp.post("/api/abrir-youtube")
def abrir_youtube():
    """Abre un vídeo en el navegador del sistema.

    Solo acepta un id de vídeo y la URL la construye el servidor: nada de lo
    que llegue en la petición se le pasa tal cual al sistema.
    """
    video_id = texto(cuerpo_json(), "id")
    if not previa.es_id_valido(video_id):
        return error_json("Identificador de vídeo no válido.")
    try:
        webbrowser.open(f"https://www.youtube.com/watch?v={video_id}")
    except Exception as error:  # noqa: BLE001
        return error_json(f"No se pudo abrir el navegador: {colapsar_error(error)}", 500)
    return jsonify({"ok": True})
