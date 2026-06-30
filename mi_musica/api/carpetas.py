"""Rutas del explorador de carpetas bajo descargas."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..paths import CARPETA_DESCARGAS, rel_descargas, resolver_dentro_descargas
from ..utils import colapsar_error
from .comun import cuerpo_json, error_json

bp = Blueprint("carpetas", __name__)


@bp.get("/api/carpetas")
def listar():
    """Explorador de carpetas bajo descargas (con protección de path-traversal)."""
    ruta_rel = (request.args.get("ruta") or "").strip().replace("\\", "/").strip("/")
    destino = resolver_dentro_descargas(ruta_rel)
    if destino is None or not destino.exists() or not destino.is_dir():
        # Si la ruta es inválida, volvemos a la raíz de descargas.
        destino = CARPETA_DESCARGAS.resolve()
        ruta_rel = ""

    items: list[dict] = []
    try:
        for hijo in sorted(destino.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            es_carpeta = hijo.is_dir()
            try:
                tamano = 0 if es_carpeta else hijo.stat().st_size
            except OSError:
                tamano = 0
            items.append({
                "nombre": hijo.name,
                "es_carpeta": es_carpeta,
                "tamano": tamano,
                "ruta": rel_descargas(hijo),
            })
    except OSError:
        pass

    return jsonify({
        "ruta": ruta_rel,
        "items": items,
        "puede_subir": bool(ruta_rel),
    })


@bp.post("/api/carpetas/crear")
def crear():
    """Crea una subcarpeta bajo descargas, validando el nombre."""
    datos = cuerpo_json()
    ruta_padre = (datos.get("ruta_padre") or "").strip().replace("\\", "/").strip("/")
    nombre = (datos.get("nombre") or "").strip()

    if not nombre:
        return error_json("El nombre de la carpeta no puede estar vacío.")
    # Validación estricta: sin separadores ni '..'.
    if "/" in nombre or "\\" in nombre or ".." in nombre or nombre in (".", ""):
        return error_json("Nombre de carpeta no válido.")

    padre = resolver_dentro_descargas(ruta_padre)
    if padre is None:
        return error_json("Ruta padre no válida.")

    rel_nueva = f"{ruta_padre}/{nombre}" if ruta_padre else nombre
    nueva = resolver_dentro_descargas(rel_nueva)
    if nueva is None:
        return error_json("Ruta de carpeta no válida.")
    try:
        nueva.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return error_json(f"No se pudo crear la carpeta: {colapsar_error(error)}", 500)

    return jsonify({"ok": True, "ruta": rel_descargas(nueva)})
