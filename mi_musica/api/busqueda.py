"""Rutas de búsqueda e información de YouTube."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..servicios import youtube
from ..utils import colapsar_error
from .comun import cuerpo_json, error_json

bp = Blueprint("busqueda", __name__)


@bp.post("/api/buscar")
def buscar():
    """Busca en YouTube por texto, o expande una URL de vídeo/playlist."""
    datos = cuerpo_json()
    q = (datos.get("q") or "").strip()
    n = datos.get("n", 12)
    if not q:
        return error_json("Falta el término de búsqueda.")
    try:
        if youtube.es_url(q):
            if youtube.es_url_playlist(q):
                titulo, items = youtube.expandir_playlist(q)
                return jsonify({
                    "resultados": items,
                    "es_playlist": True,
                    "titulo_playlist": titulo,
                })
            resultado = youtube.info_video(q)
            return jsonify({
                "resultados": [resultado],
                "es_playlist": False,
                "titulo_playlist": "",
            })
        resultados = youtube.buscar_ytsearch(q, n)
        return jsonify({
            "resultados": resultados,
            "es_playlist": False,
            "titulo_playlist": "",
        })
    except Exception as error:  # noqa: BLE001
        return error_json(f"Error en la búsqueda: {colapsar_error(error)}", 502)


@bp.post("/api/info")
def info():
    """Devuelve la información de un único vídeo a partir de su URL."""
    datos = cuerpo_json()
    url = (datos.get("url") or "").strip()
    if not url:
        return error_json("Falta la URL.")
    try:
        return jsonify(youtube.info_video(url))
    except Exception as error:  # noqa: BLE001
        return error_json(f"No se pudo obtener la información: {colapsar_error(error)}", 502)


@bp.post("/api/playlist")
def playlist():
    """Expande una playlist y devuelve su título y la lista de ítems."""
    datos = cuerpo_json()
    url = (datos.get("url") or "").strip()
    if not url:
        return error_json("Falta la URL de la playlist.")
    try:
        titulo, items = youtube.expandir_playlist(url)
        return jsonify({"titulo": titulo, "items": items})
    except Exception as error:  # noqa: BLE001
        return error_json(f"No se pudo expandir la playlist: {colapsar_error(error)}", 502)
