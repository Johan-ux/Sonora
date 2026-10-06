"""Rutas de búsqueda e información de YouTube."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..servicios import youtube
from ..utils import colapsar_error
from .comun import cuerpo_json, error_json, texto

bp = Blueprint("busqueda", __name__)


@bp.post("/api/buscar")
def buscar():
    """Busca en YouTube por texto, o expande una URL de vídeo/playlist/canal.

    Los ``filtros`` (orden, fecha, duración, tipo y características) solo se
    aplican a la búsqueda por texto: una URL ya dice exactamente qué se quiere.
    """
    datos = cuerpo_json()
    q = texto(datos, "q")
    n = datos.get("n", 12)
    if not q:
        return error_json("Falta el término de búsqueda.")
    try:
        if youtube.es_url(q):
            if youtube.es_url_playlist(q):
                # «Ver más tarde», «Me gusta» o una lista privada no se pueden
                # abrir sin cuenta, pero una URL watch?v=X&list=Y trae además el
                # vídeo que se estaba viendo: si la lista falla, se enseña ese.
                con_video = bool(youtube.id_video(q))
                try:
                    titulo, items, total = youtube.expandir_playlist(q)
                except Exception:
                    if not con_video:
                        raise
                    items = []
                if items or not con_video:
                    return jsonify({
                        "resultados": items,
                        "es_playlist": True,
                        "es_canal": False,
                        "es_mix": youtube.es_mix(q),
                        "titulo_playlist": titulo,
                        "total_playlist": total,      # total real según YouTube
                        "obtenidas": len(items),      # cuántas se pudieron extraer
                        "tope": len(items) >= youtube.MAX_PLAYLIST,  # se cortó en el tope
                    })
            elif youtube.es_url_canal(q):
                # Un canal se muestra como una "playlist" (por lotes, con ＋ por
                # vídeo) para que el usuario ELIJA; nunca se descarga entero solo.
                titulo, items, total = youtube.expandir_canal(q)
                videos = [item for item in items if item["tipo"] == "video"]
                if items and not videos:
                    # La pestaña de listas del canal: son colecciones que abrir,
                    # no canciones que repartir en lotes.
                    return jsonify({
                        "resultados": items,
                        "es_playlist": False,
                        "titulo_playlist": "",
                    })
                # Por lotes solo van los vídeos: «Añadir todo» no debe encolar
                # una lista que se hubiera colado entre ellos.
                items = videos
                return jsonify({
                    "resultados": items,
                    "es_playlist": True,
                    "es_canal": True,
                    "es_mix": False,
                    "titulo_playlist": titulo,
                    "total_playlist": total,
                    "obtenidas": len(items),
                    "tope": len(items) >= youtube.MAX_PLAYLIST,  # se cortó en el tope
                })
            resultado = youtube.info_video(q)
            return jsonify({
                "resultados": [resultado],
                "es_playlist": False,
                "titulo_playlist": "",
            })
        resultados = youtube.buscar(q, n, datos.get("filtros"))
        return jsonify({
            "resultados": resultados,
            "es_playlist": False,
            "titulo_playlist": "",
        })
    except Exception as error:  # noqa: BLE001
        return error_json(f"Error en la búsqueda: {colapsar_error(error)}", 502)
