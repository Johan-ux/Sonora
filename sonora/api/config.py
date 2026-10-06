"""Rutas de configuración (carpeta, formato, calidad y reproductor)."""

from __future__ import annotations

import json
import math

from flask import Blueprint, jsonify

from .. import db, ffmpeg
from ..servicios.descargas import MAX_SIMULTANEAS, descargas_simultaneas, normalizar_simultaneas
from ..servicios.youtube import ORDENES
from ..ydl_opts import normalizar_bitrate, normalizar_formato, normalizar_resolucion
from .comun import cuerpo_json, ruta_relativa, texto

bp = Blueprint("config", __name__)

# Modos del reproductor de vídeo: ventana flotante o teatro (toda la zona de
# contenido). La pantalla completa no se guarda: siempre se entra a mano.
MODOS_VIDEO = ("flotante", "teatro")

# Temas de color: el degradado de acento sobre la paleta de negros. Cada uno
# tiene su bloque ``[data-tema]`` en estilo.css y su muestra en index.html (un
# test lo comprueba); el primero es el de fábrica.
TEMAS = (
    "ocaso",
    "cobre",
    "duna",
    "agave",
    "turquesa",
    "oasis",
    "crepusculo",
    "buganvilla",
    "luna",
)


def _numero(valor: object) -> float | None:
    """Devuelve ``valor`` como número finito, o ``None`` si no lo es."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
        return None
    try:
        numero = float(valor)
    except ValueError:
        return None
    return numero if math.isfinite(numero) else None


def normalizar_volumen(valor: object) -> str:
    """Devuelve el volumen como texto entre 0 y 1 (1 si no es un número)."""
    numero = _numero(valor)
    if numero is None:
        return "1"
    return str(min(1.0, max(0.0, numero)))


def normalizar_modo_video(valor: object) -> str:
    """Devuelve ``valor`` como modo de vídeo válido, o 'flotante'."""
    return valor if valor in MODOS_VIDEO else "flotante"


def normalizar_orden_busqueda(valor: object) -> str:
    """Devuelve ``valor`` como orden de búsqueda válido, o 'relevancia'."""
    return valor if valor in ORDENES else ORDENES[0]


def normalizar_tema(valor: object) -> str:
    """Devuelve ``valor`` como tema de color válido, o el de fábrica."""
    return valor if valor in TEMAS else TEMAS[0]


def normalizar_geometria_video(valor: object) -> str:
    """Valida la posición y el tamaño de la ventana de vídeo, como JSON.

    Devuelve '' si no es un objeto ``{x, y, lado}`` de números: una geometría
    vacía significa «sin colocar» y la interfaz vuelve a la esquina por
    defecto. ``lado`` es el lado largo de la imagen; ancho y alto no se guardan
    porque los dicta la proporción de cada vídeo.
    """
    if not isinstance(valor, dict):
        return ""
    geometria = {}
    for clave in ("x", "y", "lado"):
        numero = _numero(valor.get(clave))
        if numero is None:
            return ""
        geometria[clave] = round(numero)
    if geometria["lado"] <= 0:
        return ""
    return json.dumps(geometria)


def _geometria_video_guardada() -> dict | None:
    """Geometría persistida de la ventana de vídeo, o ``None`` si no hay."""
    crudo = db.config_obtener("video_geometria", "")
    if not crudo:
        return None
    try:
        geometria = json.loads(crudo)
    except ValueError:
        return None
    return geometria if isinstance(geometria, dict) else None


@bp.get("/api/config")
def obtener():
    """Devuelve la configuración persistida (carpeta, formato, calidad…).

    Incluye ``ffmpeg_disponible`` para que el frontend avise si falta ffmpeg
    (sin él la conversión a MP3 o la fusión de vídeo fallarían con un error
    poco claro).

    Las preferencias del reproductor (volumen y ventana de vídeo) viven aquí y
    no en el ``localStorage`` de la interfaz: la ventana de la app usa un perfil
    privado y un puerto distinto en cada arranque, así que lo guardado en el
    navegador no sobrevive al cierre.
    """
    return jsonify({
        "carpeta_por_defecto": db.config_obtener("carpeta_por_defecto", ""),
        "bitrate_por_defecto": db.config_obtener("bitrate_por_defecto", "320") or "320",
        "formato_por_defecto": db.config_obtener("formato_por_defecto", "audio") or "audio",
        "resolucion_por_defecto": db.config_obtener("resolucion_por_defecto", "1080") or "1080",
        "ffmpeg_disponible": ffmpeg.localizacion() is not None,
        "descargas_simultaneas": descargas_simultaneas(),
        "max_simultaneas": MAX_SIMULTANEAS,
        "volumen": float(normalizar_volumen(db.config_obtener("volumen", "1"))),
        "video_modo": normalizar_modo_video(db.config_obtener("video_modo", "flotante")),
        "video_geometria": _geometria_video_guardada(),
        "tema": normalizar_tema(db.config_obtener("tema", "")),
        "busqueda_orden": normalizar_orden_busqueda(db.config_obtener("busqueda_orden", "")),
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
    if "descargas_simultaneas" in datos:
        db.config_guardar(
            "descargas_simultaneas",
            str(normalizar_simultaneas(texto(datos, "descargas_simultaneas"))),
        )
    if "volumen" in datos:
        db.config_guardar("volumen", normalizar_volumen(datos["volumen"]))
    if "video_modo" in datos:
        db.config_guardar("video_modo", normalizar_modo_video(datos["video_modo"]))
    if "video_geometria" in datos:
        # null (o cualquier cosa que no sea una geometría) la restablece.
        db.config_guardar(
            "video_geometria",
            normalizar_geometria_video(datos["video_geometria"]),
        )
    if "tema" in datos:
        db.config_guardar("tema", normalizar_tema(datos["tema"]))
    if "busqueda_orden" in datos:
        # El orden se recuerda; el resto de filtros de búsqueda, no: son de
        # cada búsqueda, y encontrarlos puestos al abrir la app despistaría.
        db.config_guardar(
            "busqueda_orden",
            normalizar_orden_busqueda(datos["busqueda_orden"]),
        )
    return jsonify({"ok": True})
