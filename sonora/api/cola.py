"""Rutas de la cola de descargas y del historial."""

from __future__ import annotations

import uuid

from flask import Blueprint, jsonify

from .. import db
from ..servicios import descargas
from ..utils import ahora_iso
from ..ydl_opts import normalizar_bitrate, normalizar_formato, normalizar_resolucion
from .comun import cuerpo_json, error_json, ruta_relativa, texto

bp = Blueprint("cola", __name__)

# Tope de canciones por lote. Generoso para que el usuario pueda "ampliar" el
# lote tanto como quiera (incluso meter toda la playlist en uno solo); el límite
# evita valores absurdos. La descarga sigue siendo secuencial, una a una.
MAX_TAMANO_LOTE = 1000


def _globales(datos: dict) -> dict:
    """Valores por defecto del cuerpo de la petición para el conjunto de ítems.

    Cada uno cae, si no viene en la petición, al valor persistido en config.
    Un ítem individual puede sobreescribir cualquiera de estos (override por
    resultado); estos son solo el punto de partida común del lote/petición.

    La configuración se lee aquí, una vez por petición, y no al normalizar cada
    ítem: con una playlist de mil canciones serían tres mil consultas.
    """
    return {
        "carpeta": ruta_relativa(datos, "carpeta"),
        "bitrate": texto(datos, "bitrate") or descargas.bitrate_por_defecto(),
        "formato": texto(datos, "formato") or descargas.formato_por_defecto(),
        "resolucion": texto(datos, "resolucion") or descargas.resolucion_por_defecto(),
    }


def _item_desde(entrada: dict, globales: dict) -> dict:
    """Normaliza una entrada JSON del cliente en un ítem de cola.

    ``globales`` aporta los valores por defecto de la petición; la propia
    entrada puede sobreescribir carpeta, bitrate, formato y resolución (así el
    ajuste global y el override por resultado conviven sin ambigüedad: el ítem
    guarda su valor concreto en el momento de añadirse).
    """
    carpeta = ruta_relativa(entrada, "carpeta") or globales["carpeta"]
    bitrate = texto(entrada, "bitrate") or globales["bitrate"]
    formato = texto(entrada, "formato") or globales["formato"]
    resolucion = texto(entrada, "resolucion") or globales["resolucion"]
    return {
        "id": uuid.uuid4().hex[:10],
        "url": texto(entrada, "url"),
        "titulo": texto(entrada, "titulo"),
        "thumbnail": texto(entrada, "thumbnail"),
        "duracion": texto(entrada, "duracion"),
        "canal": texto(entrada, "canal"),
        "carpeta": carpeta,
        "bitrate": normalizar_bitrate(bitrate),
        "formato": normalizar_formato(formato),
        "resolucion": normalizar_resolucion(resolucion),
        "creado": ahora_iso(),
    }


@bp.get("/api/cola")
def cola():
    """Devuelve la cola actual con el progreso vivo del ítem activo."""
    return jsonify({"items": descargas.listar_cola_con_progreso()})


@bp.post("/api/cola/agregar")
def agregar():
    """Añade un único ítem a la cola de descargas.

    Si la misma URL ya está pendiente o descargándose, no se duplica: se
    responde ``{"ok": true, "duplicado": true}`` para que la UI lo indique.
    """
    datos = cuerpo_json()
    url = texto(datos, "url")
    if not url:
        return error_json("Falta la URL.")
    item = _item_desde(datos, _globales(datos))
    # Comprobación e inserción atómicas (bajo el mismo lock): dos peticiones
    # concurrentes con la misma URL no pueden duplicarla.
    if not db.cola_agregar_si_no_activa(item):
        return jsonify({"ok": True, "duplicado": True})
    descargas.reponer_workers()
    descargas.emitir_cola_actualizada()
    return jsonify({"id": item["id"], "ok": True, "duplicado": False})


@bp.post("/api/cola/agregar_playlist")
def agregar_playlist():
    """Añade canciones de una playlist a la cola, organizadas en LOTES.

    Dos modos según los datos recibidos:

    * ``nombre_lote`` presente → todas las canciones entran como UN único lote
      con ese nombre exacto (sirve para añadir "un lote concreto" desde el
      buscador, p. ej. solo el Lote 2/4).
    * en otro caso → se reparten en lotes de ``tamano_lote`` canciones (por
      defecto 100, ampliable hasta ``MAX_TAMANO_LOTE``), nombrados ``i/N``.

    Las URLs que ya estén pendientes o descargándose se omiten (no se
    duplican); la respuesta incluye cuántas se omitieron.
    """
    datos = cuerpo_json()
    entradas = datos.get("items")
    if not isinstance(entradas, list) or not entradas:
        return error_json("No se han proporcionado canciones.")
    titulo = texto(datos, "titulo") or "Playlist"
    globales = _globales(datos)
    nombre_lote = texto(datos, "nombre_lote")

    validas: list[dict] = []
    omitidas = 0
    vistas: set[str] = set()
    for e in entradas:
        if not isinstance(e, dict):
            continue
        url = texto(e, "url")
        if not url:
            continue
        if url in vistas:
            omitidas += 1
            continue
        vistas.add(url)
        validas.append(e)
    if not validas:
        return jsonify({"ok": True, "lotes": 0, "total": 0, "omitidas": omitidas})

    # Reparto en lotes: uno solo con nombre explícito (añadir un lote concreto
    # desde el buscador) o varios de 'tam' canciones, nombrados «i/N».
    total = len(validas)
    if nombre_lote:
        tramos = [(validas, nombre_lote)]
    else:
        try:
            tam = int(datos.get("tamano_lote") or 100)
        except (TypeError, ValueError):
            tam = 100
        tam = max(1, min(tam, MAX_TAMANO_LOTE))
        n_lotes = (total + tam - 1) // tam
        tramos = []
        for indice_lote in range(n_lotes):
            ini = indice_lote * tam
            fin = min(ini + tam, total)
            nombre = f"{titulo} · Lote {indice_lote + 1}/{n_lotes} (canciones {ini + 1}–{fin})"
            tramos.append((validas[ini:fin], nombre))

    items: list[dict] = []
    for entradas_lote, lote_nombre in tramos:
        lote_id = uuid.uuid4().hex[:12]
        for entrada in entradas_lote:
            item = _item_desde(entrada, globales)
            item["lote"] = lote_id
            item["lote_nombre"] = lote_nombre
            items.append(item)

    # Todo de una vez y atómico contra la cola activa: peticiones concurrentes
    # (dos lotes a la vez, «Añadir todo» + un ＋ suelto…) no duplican.
    insertados = set(db.cola_agregar_varios_si_no_activas(items))
    omitidas += len(items) - len(insertados)
    # 'lotes' cuenta solo los que recibieron canciones de verdad: si todo
    # estaba ya en la cola, la respuesta es {lotes: 0, total: 0, omitidas: N}.
    lotes_con_items = len({item["lote"] for item in items if item["id"] in insertados})
    if insertados:
        descargas.reponer_workers()
    descargas.emitir_cola_actualizada()
    return jsonify({
        "ok": True,
        "lotes": lotes_con_items,
        "total": len(insertados),
        "omitidas": omitidas,
    })


@bp.post("/api/cola/eliminar")
def eliminar():
    """Elimina un ítem de la cola (solo si está en estado 'en_cola')."""
    datos = cuerpo_json()
    item_id = texto(datos, "id")
    if not item_id:
        return error_json("Falta el id del ítem.")
    ok = db.cola_eliminar(item_id)
    descargas.emitir_cola_actualizada()
    if not ok:
        return error_json("El ítem ya no está pendiente (¿descargando o terminado?).", 409)
    return jsonify({"ok": True})


@bp.post("/api/cola/eliminar_lote")
def eliminar_lote():
    """Elimina de la cola todos los ítems pendientes ('en_cola') de un lote."""
    datos = cuerpo_json()
    lote = texto(datos, "lote")
    if not lote:
        return error_json("Falta el lote.")
    eliminados = db.cola_eliminar_lote(lote)
    descargas.emitir_cola_actualizada()
    return jsonify({"ok": True, "eliminados": eliminados})


@bp.post("/api/cola/cancelar")
def cancelar():
    """Cancela el ítem que se está descargando ahora mismo.

    La cancelación es cooperativa: el worker la aplica en el siguiente tick de
    progreso y el ítem queda en estado 'error' con el mensaje «Cancelada por el
    usuario» (reintentable). Para ítems 'en_cola' usa /api/cola/eliminar.
    """
    datos = cuerpo_json()
    item_id = texto(datos, "id")
    if not item_id:
        return error_json("Falta el id del ítem.")
    if descargas.cancelar_item(item_id):
        return jsonify({"ok": True, "cancelando": True})
    return error_json("Ese ítem no se está descargando.", 409)


@bp.post("/api/cola/reintentar")
def reintentar():
    """Devuelve a 'en_cola' un ítem en error (o todos, con {"todos": true}).

    Arranca el worker automáticamente para que el reintento empiece ya.
    """
    datos = cuerpo_json()
    if datos.get("todos"):
        n = db.cola_reintentar_errores()
        if n:
            descargas.arrancar_worker()
        descargas.emitir_cola_actualizada()
        return jsonify({"ok": True, "reintentados": n})
    item_id = texto(datos, "id")
    if not item_id:
        return error_json("Falta el id del ítem.")
    ok = db.cola_reintentar(item_id)
    if ok:
        descargas.arrancar_worker()
    descargas.emitir_cola_actualizada()
    if not ok:
        item = db.cola_obtener(item_id)
        if item and item.get("estado") == "error":
            # Sigue en error: no se reactivó porque su URL ya está en otro ítem.
            return error_json("Esa canción ya está otra vez en la cola.", 409)
        return error_json("El ítem no está en estado de error.", 409)
    return jsonify({"ok": True})


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


@bp.post("/api/historial/eliminar")
def historial_eliminar():
    """Borra una entrada del historial (solo el registro, no el archivo)."""
    datos = cuerpo_json()
    item_id = texto(datos, "id")
    if not item_id:
        return error_json("Falta el id de la entrada.")
    if not db.historial_eliminar(item_id):
        return error_json("No se encontró esa entrada del historial.", 404)
    return jsonify({"ok": True})


@bp.post("/api/historial/limpiar")
def historial_limpiar():
    """Vacía todo el historial (solo el registro, no los archivos)."""
    eliminados = db.historial_limpiar()
    return jsonify({"ok": True, "eliminados": eliminados})
