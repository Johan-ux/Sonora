"""Rutas de la cola de descargas y del historial."""

from __future__ import annotations

import uuid

from flask import Blueprint, jsonify

from .. import db
from ..servicios import descargas
from ..utils import ahora_iso
from .comun import cuerpo_json, error_json

bp = Blueprint("cola", __name__)


@bp.get("/api/cola")
def cola():
    """Devuelve la cola actual con el progreso vivo del ítem activo."""
    return jsonify({"items": descargas.listar_cola_con_progreso()})


@bp.post("/api/cola/agregar")
def agregar():
    """Añade un único ítem a la cola de descargas."""
    datos = cuerpo_json()
    url = (datos.get("url") or "").strip()
    if not url:
        return error_json("Falta la URL.")
    item_id = uuid.uuid4().hex[:10]
    item = {
        "id": item_id,
        "url": url,
        "titulo": datos.get("titulo") or "",
        "thumbnail": datos.get("thumbnail") or "",
        "duracion": datos.get("duracion") or "",
        "canal": datos.get("canal") or "",
        "carpeta": (datos.get("carpeta") or "").strip().replace("\\", "/").strip("/"),
        "bitrate": str(datos.get("bitrate") or descargas.bitrate_por_defecto()),
        "creado": ahora_iso(),
    }
    db.cola_agregar(item)
    descargas.emitir_cola_actualizada()
    return jsonify({"id": item_id, "ok": True})


@bp.post("/api/cola/agregar_varios")
def agregar_varios():
    """Añade varios ítems a la cola (p. ej. una playlist completa)."""
    datos = cuerpo_json()
    entradas = datos.get("items")
    if not isinstance(entradas, list) or not entradas:
        return error_json("No se han proporcionado ítems.")
    carpeta_global = (datos.get("carpeta") or "").strip().replace("\\", "/").strip("/")
    bitrate_global = datos.get("bitrate")
    ids: list[str] = []
    for entrada in entradas:
        if not isinstance(entrada, dict):
            continue
        url = (entrada.get("url") or "").strip()
        if not url:
            continue
        item_id = uuid.uuid4().hex[:10]
        carpeta_item = (entrada.get("carpeta") or carpeta_global or "")
        item = {
            "id": item_id,
            "url": url,
            "titulo": entrada.get("titulo") or "",
            "thumbnail": entrada.get("thumbnail") or "",
            "duracion": entrada.get("duracion") or "",
            "canal": entrada.get("canal") or "",
            "carpeta": carpeta_item.strip().replace("\\", "/").strip("/"),
            "bitrate": str(entrada.get("bitrate") or bitrate_global or descargas.bitrate_por_defecto()),
            "creado": ahora_iso(),
        }
        try:
            db.cola_agregar(item)
            ids.append(item_id)
        except Exception:  # noqa: BLE001 - un ítem inválido no aborta el lote
            continue
    descargas.emitir_cola_actualizada()
    return jsonify({"ids": ids, "ok": True})


@bp.post("/api/cola/eliminar")
def eliminar():
    """Elimina un ítem de la cola (solo si está en estado 'en_cola')."""
    datos = cuerpo_json()
    item_id = (datos.get("id") or "").strip()
    if not item_id:
        return error_json("Falta el id del ítem.")
    ok = db.cola_eliminar(item_id)
    descargas.emitir_cola_actualizada()
    return jsonify({"ok": bool(ok)})


@bp.post("/api/cola/descargar")
def descargar():
    """Arranca el worker de descargas si no está ya en marcha."""
    descargas.arrancar_worker()
    return jsonify({"ok": True})


@bp.post("/api/cola/limpiar")
def limpiar():
    """Elimina de la cola los ítems completados o con error."""
    db.cola_limpiar_terminados()
    descargas.emitir_cola_actualizada()
    return jsonify({"ok": True})


@bp.get("/api/historial")
def historial():
    """Devuelve el historial de descargas completadas."""
    return jsonify({"items": db.historial_listar()})
