#!/usr/bin/env python3
"""Interfaz web para el descargador de música personal.

Aplicación Flask con layout 70/30: navegador YouTube embebido a la izquierda,
panel de control con cola de descarga a la derecha, y explorador de carpetas
opcional. Progreso en tiempo real mediante Server-Sent Events (SSE).

Uso:
    python app.py
    # Abre http://localhost:5000 en el navegador.
"""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

try:
    import yt_dlp
    from yt_dlp.utils import DownloadError
except ImportError:
    import sys
    sys.exit(
        "Falta la dependencia 'yt-dlp'.\n"
        "Instálala con: pip install -r requirements.txt"
    )

from descargar_musica import localizar_ffmpeg

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #

app = Flask(__name__)

CARPETA_DESCARGAS = Path("descargas")
CARPETA_DESCARGAS.mkdir(parents=True, exist_ok=True)

BITRATE_POR_DEFECTO = "320"

# Almacén en memoria.
tareas: dict[str, TareaDescarga] = {}
cola_global: list[ItemCola] = []
historial_completados: list[dict] = []


# --------------------------------------------------------------------------- #
# Modelos
# --------------------------------------------------------------------------- #

@dataclass
class ItemCola:
    """Un elemento en la cola de descarga."""
    id: str
    url: str
    titulo: str = ""
    thumbnail: str = ""
    duracion: str = ""
    canal: str = ""
    estado: str = "en_cola"  # en_cola | descargando | completado | error
    progreso: float = 0.0
    error: str = ""
    carpeta_destino: str = ""


@dataclass
class TareaDescarga:
    """Tarea de descarga activa."""
    id: str
    items: list[ItemCola] = field(default_factory=list)
    estado: str = "pendiente"
    cola_eventos: queue.Queue = field(default_factory=queue.Queue)


# --------------------------------------------------------------------------- #
# Cola de eventos global para SSE
# --------------------------------------------------------------------------- #

clientes_sse: list[queue.Queue] = []
lock_clientes = threading.Lock()


def emitir_evento(tipo: str, datos: dict) -> None:
    """Envía un evento a todos los clientes SSE conectados."""
    evento = {"tipo": tipo, **datos}
    with lock_clientes:
        for q in clientes_sse:
            try:
                q.put_nowait(evento)
            except queue.Full:
                pass


# --------------------------------------------------------------------------- #
# Extracción de info de video
# --------------------------------------------------------------------------- #

def extraer_info_video(url: str) -> dict | None:
    """Extrae metadatos de un video de YouTube sin descargarlo."""
    ffmpeg_loc = localizar_ffmpeg()
    opciones = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "noplaylist": True,
    }
    if ffmpeg_loc:
        opciones["ffmpeg_location"] = str(ffmpeg_loc)

    try:
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                return None
            duracion_seg = info.get("duration", 0) or 0
            minutos = int(duracion_seg) // 60
            segundos = int(duracion_seg) % 60
            return {
                "url": url,
                "titulo": info.get("title", "Sin título"),
                "thumbnail": info.get("thumbnail", ""),
                "duracion": f"{minutos}:{segundos:02d}",
                "canal": info.get("uploader", info.get("channel", "")),
                "id": info.get("id", ""),
            }
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Descarga en hilo
# --------------------------------------------------------------------------- #

descarga_activa = threading.Event()
lock_cola = threading.Lock()


def _hook_progreso(d: dict, item: ItemCola) -> None:
    """Hook de progreso de yt-dlp."""
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        descargado = d.get("downloaded_bytes", 0)
        porcentaje = (descargado / total * 100) if total else 0
        item.progreso = round(porcentaje, 1)
        item.titulo = d.get("info_dict", {}).get("title", item.titulo) or item.titulo
        emitir_evento("progreso", {
            "id": item.id,
            "progreso": item.progreso,
            "titulo": item.titulo,
        })
    elif d["status"] == "finished":
        item.titulo = d.get("info_dict", {}).get("title", item.titulo) or item.titulo
        emitir_evento("progreso", {
            "id": item.id,
            "progreso": 100.0,
            "mensaje": "Convirtiendo a MP3…",
        })


def procesar_cola() -> None:
    """Procesa la cola de descarga secuencialmente."""
    ffmpeg_loc = localizar_ffmpeg()

    while True:
        item_actual = None
        with lock_cola:
            for item in cola_global:
                if item.estado == "en_cola":
                    item_actual = item
                    item.estado = "descargando"
                    break

        if item_actual is None:
            descarga_activa.clear()
            return

        emitir_evento("descargando", {
            "id": item_actual.id,
            "titulo": item_actual.titulo,
        })

        carpeta = Path(item_actual.carpeta_destino) if item_actual.carpeta_destino else CARPETA_DESCARGAS
        carpeta.mkdir(parents=True, exist_ok=True)

        opciones: dict = {
            "format": "bestaudio/best",
            "outtmpl": str(carpeta / "%(title)s.%(ext)s"),
            "writethumbnail": True,
            "ignoreerrors": False,
            "noplaylist": True,
            "progress_hooks": [
                lambda d, it=item_actual: _hook_progreso(d, it)
            ],
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": BITRATE_POR_DEFECTO,
                },
                {"key": "FFmpegMetadata", "add_metadata": True},
                {"key": "EmbedThumbnail", "already_have_thumbnail": False},
            ],
        }

        if ffmpeg_loc:
            opciones["ffmpeg_location"] = str(ffmpeg_loc)

        try:
            with yt_dlp.YoutubeDL(opciones) as ydl:
                ydl.download([item_actual.url])
            item_actual.estado = "completado"
            item_actual.progreso = 100.0
            historial_completados.insert(0, {
                "id": item_actual.id,
                "titulo": item_actual.titulo,
                "url": item_actual.url,
                "carpeta": str(carpeta),
            })
            emitir_evento("completado", {
                "id": item_actual.id,
                "titulo": item_actual.titulo,
            })
        except (DownloadError, Exception) as error:
            item_actual.estado = "error"
            item_actual.error = str(error)
            emitir_evento("error", {
                "id": item_actual.id,
                "error": " ".join(str(error).split()),
            })


def iniciar_procesamiento_cola() -> None:
    """Inicia el procesamiento de la cola si no está activo."""
    if not descarga_activa.is_set():
        descarga_activa.set()
        hilo = threading.Thread(target=procesar_cola, daemon=True)
        hilo.start()


# --------------------------------------------------------------------------- #
# Rutas
# --------------------------------------------------------------------------- #

@app.route("/")
def index():
    """Página principal."""
    return render_template("index.html")


@app.route("/api/info", methods=["POST"])
def api_info():
    """Extrae información de un video de YouTube."""
    datos = request.get_json(silent=True) or {}
    url = datos.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL vacía"}), 400

    info = extraer_info_video(url)
    if info is None:
        return jsonify({"error": "No se pudo obtener información del video"}), 400

    return jsonify(info)


@app.route("/api/cola/agregar", methods=["POST"])
def api_cola_agregar():
    """Agrega un item a la cola de descarga."""
    datos = request.get_json(silent=True) or {}
    url = datos.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL vacía"}), 400

    item_id = uuid.uuid4().hex[:10]
    item = ItemCola(
        id=item_id,
        url=url,
        titulo=datos.get("titulo", ""),
        thumbnail=datos.get("thumbnail", ""),
        duracion=datos.get("duracion", ""),
        canal=datos.get("canal", ""),
        carpeta_destino=datos.get("carpeta", ""),
    )

    with lock_cola:
        cola_global.append(item)

    emitir_evento("cola_actualizada", _estado_cola())
    return jsonify({"id": item_id, "mensaje": "Agregado a la cola"})


@app.route("/api/cola/eliminar", methods=["POST"])
def api_cola_eliminar():
    """Elimina un item de la cola (solo si está en_cola)."""
    datos = request.get_json(silent=True) or {}
    item_id = datos.get("id", "")

    with lock_cola:
        cola_global[:] = [
            it for it in cola_global
            if not (it.id == item_id and it.estado == "en_cola")
        ]

    emitir_evento("cola_actualizada", _estado_cola())
    return jsonify({"ok": True})


@app.route("/api/cola")
def api_cola():
    """Devuelve el estado actual de la cola."""
    return jsonify(_estado_cola())


@app.route("/api/cola/descargar", methods=["POST"])
def api_cola_descargar():
    """Inicia la descarga de la cola."""
    iniciar_procesamiento_cola()
    return jsonify({"ok": True, "mensaje": "Descarga iniciada"})


@app.route("/api/eventos")
def api_eventos():
    """Stream SSE global de eventos."""
    q: queue.Queue = queue.Queue(maxsize=200)
    with lock_clientes:
        clientes_sse.append(q)

    def generar():
        try:
            while True:
                try:
                    evento = q.get(timeout=30)
                    yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
                except queue.Empty:
                    yield ":\n\n"
        finally:
            with lock_clientes:
                if q in clientes_sse:
                    clientes_sse.remove(q)

    return Response(generar(), mimetype="text/event-stream")


@app.route("/api/carpetas")
def api_carpetas():
    """Lista el contenido de una carpeta dentro de descargas."""
    ruta_rel = request.args.get("ruta", "")
    carpeta = (CARPETA_DESCARGAS / ruta_rel).resolve()

    # Seguridad: no salir de CARPETA_DESCARGAS.
    if not str(carpeta).startswith(str(CARPETA_DESCARGAS.resolve())):
        return jsonify({"error": "Ruta no permitida"}), 403

    if not carpeta.exists():
        return jsonify({"error": "Carpeta no encontrada"}), 404

    items = []
    for entry in sorted(carpeta.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if entry.name.startswith("."):
            continue
        items.append({
            "nombre": entry.name,
            "es_carpeta": entry.is_dir(),
            "tamaño": entry.stat().st_size if entry.is_file() else 0,
            "ruta": str(entry.relative_to(CARPETA_DESCARGAS.resolve())).replace("\\", "/"),
        })

    # Ruta relativa actual.
    try:
        ruta_actual = str(carpeta.relative_to(CARPETA_DESCARGAS.resolve())).replace("\\", "/")
    except ValueError:
        ruta_actual = ""
    if ruta_actual == ".":
        ruta_actual = ""

    return jsonify({
        "ruta": ruta_actual,
        "items": items,
        "puede_subir": ruta_actual != "",
    })


@app.route("/api/carpetas/crear", methods=["POST"])
def api_carpetas_crear():
    """Crea una nueva carpeta dentro de descargas."""
    datos = request.get_json(silent=True) or {}
    ruta_padre = datos.get("ruta_padre", "")
    nombre = datos.get("nombre", "").strip()

    if not nombre or "/" in nombre or "\\" in nombre:
        return jsonify({"error": "Nombre de carpeta no válido"}), 400

    carpeta = (CARPETA_DESCARGAS / ruta_padre / nombre).resolve()
    if not str(carpeta).startswith(str(CARPETA_DESCARGAS.resolve())):
        return jsonify({"error": "Ruta no permitida"}), 403

    carpeta.mkdir(parents=True, exist_ok=True)
    return jsonify({"ok": True, "ruta": str(carpeta.relative_to(CARPETA_DESCARGAS.resolve())).replace("\\", "/")})


@app.route("/api/historial")
def api_historial():
    """Devuelve el historial de descargas completadas."""
    return jsonify(historial_completados[:50])


@app.route("/descargas/<path:nombre>")
def servir_archivo(nombre: str):
    """Sirve un archivo descargado."""
    return send_from_directory(CARPETA_DESCARGAS, nombre, as_attachment=True)


# --------------------------------------------------------------------------- #
# Utilidades internas
# --------------------------------------------------------------------------- #

def _estado_cola() -> dict:
    """Devuelve el estado serializable de la cola."""
    return {
        "items": [
            {
                "id": it.id,
                "url": it.url,
                "titulo": it.titulo,
                "thumbnail": it.thumbnail,
                "duracion": it.duracion,
                "canal": it.canal,
                "estado": it.estado,
                "progreso": it.progreso,
                "error": it.error,
                "carpeta": it.carpeta_destino,
            }
            for it in cola_global
        ]
    }


# --------------------------------------------------------------------------- #
# Punto de entrada
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    print("Descargador de Musica Personal")
    print("Abre http://localhost:5000 en tu navegador")
    print()
    app.run(debug=False, host="127.0.0.1", port=5000)
