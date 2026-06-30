#!/usr/bin/env python3
"""Interfaz web para el descargador de música personal.

Aplicación Flask que proporciona una interfaz web moderna para descargar
música desde YouTube usando yt-dlp. Incluye progreso en tiempo real
mediante Server-Sent Events (SSE).

Uso:
    python app.py
    # Abre http://localhost:5000 en el navegador.
"""

from __future__ import annotations

import json
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

# Almacén de tareas en memoria (suficiente para uso personal).
tareas: dict[str, TareaDescarga] = {}


# --------------------------------------------------------------------------- #
# Modelo de tarea
# --------------------------------------------------------------------------- #

@dataclass
class ItemDescarga:
    """Estado de una URL individual dentro de una tarea."""
    url: str
    estado: str = "pendiente"  # pendiente | descargando | completado | error
    titulo: str = ""
    progreso: float = 0.0
    error: str = ""


@dataclass
class TareaDescarga:
    """Agrupa varias URLs en una sola tarea de descarga."""
    id: str
    items: list[ItemDescarga] = field(default_factory=list)
    estado: str = "pendiente"  # pendiente | en_progreso | completada
    cola_eventos: queue.Queue = field(default_factory=queue.Queue)


# --------------------------------------------------------------------------- #
# Lógica de descarga (en hilo separado)
# --------------------------------------------------------------------------- #

def _enviar_evento(tarea: TareaDescarga, tipo: str, datos: dict) -> None:
    """Encola un evento SSE para el cliente."""
    tarea.cola_eventos.put({"tipo": tipo, **datos})


def _hook_progreso(d: dict, tarea: TareaDescarga, item: ItemDescarga) -> None:
    """Hook de progreso de yt-dlp: actualiza el item y envía evento SSE."""
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        descargado = d.get("downloaded_bytes", 0)
        porcentaje = (descargado / total * 100) if total else 0
        item.progreso = round(porcentaje, 1)
        item.titulo = d.get("info_dict", {}).get("title", item.titulo)
        _enviar_evento(tarea, "progreso", {
            "url": item.url,
            "titulo": item.titulo,
            "progreso": item.progreso,
        })
    elif d["status"] == "finished":
        item.titulo = d.get("info_dict", {}).get("title", item.titulo)
        _enviar_evento(tarea, "progreso", {
            "url": item.url,
            "titulo": item.titulo,
            "progreso": 100.0,
            "mensaje": "Convirtiendo a MP3…",
        })


def _ejecutar_descarga(tarea: TareaDescarga, bitrate: str) -> None:
    """Descarga todas las URLs de la tarea (ejecutar en hilo)."""
    tarea.estado = "en_progreso"
    _enviar_evento(tarea, "inicio", {"total": len(tarea.items)})

    ffmpeg_loc = localizar_ffmpeg()

    for i, item in enumerate(tarea.items):
        item.estado = "descargando"
        _enviar_evento(tarea, "descargando", {
            "url": item.url,
            "indice": i + 1,
            "total": len(tarea.items),
        })

        opciones: dict = {
            "format": "bestaudio/best",
            "outtmpl": str(CARPETA_DESCARGAS / "%(title)s.%(ext)s"),
            "writethumbnail": True,
            "ignoreerrors": False,
            "noplaylist": True,
            "progress_hooks": [
                lambda d, t=tarea, it=item: _hook_progreso(d, t, it)
            ],
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": bitrate,
                },
                {"key": "FFmpegMetadata", "add_metadata": True},
                {"key": "EmbedThumbnail", "already_have_thumbnail": False},
            ],
        }

        if ffmpeg_loc is not None:
            opciones["ffmpeg_location"] = str(ffmpeg_loc)

        try:
            with yt_dlp.YoutubeDL(opciones) as ydl:
                ydl.download([item.url])
            item.estado = "completado"
            item.progreso = 100.0
            _enviar_evento(tarea, "completado", {
                "url": item.url,
                "titulo": item.titulo,
            })
        except (DownloadError, Exception) as error:  # noqa: BLE001
            item.estado = "error"
            item.error = str(error)
            _enviar_evento(tarea, "error", {
                "url": item.url,
                "error": " ".join(str(error).split()),
            })

    tarea.estado = "completada"
    completados = sum(1 for it in tarea.items if it.estado == "completado")
    _enviar_evento(tarea, "fin", {
        "completados": completados,
        "total": len(tarea.items),
    })
    # Señal de cierre del stream SSE.
    tarea.cola_eventos.put(None)


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def _parsear_urls(texto: str) -> list[str]:
    """Extrae URLs únicas de un texto (separadas por comas, espacios o saltos de línea)."""
    urls: list[str] = []
    vistas: set[str] = set()
    for linea in texto.splitlines():
        if linea.lstrip().startswith("#"):
            continue
        for fragmento in re.split(r"[,\s]+", linea):
            url = fragmento.strip()
            if url and url.startswith("http") and url not in vistas:
                vistas.add(url)
                urls.append(url)
    return urls


# --------------------------------------------------------------------------- #
# Rutas
# --------------------------------------------------------------------------- #

@app.route("/")
def index():
    """Página principal."""
    return render_template("index.html")


@app.route("/api/descargar", methods=["POST"])
def api_descargar():
    """Inicia una tarea de descarga con las URLs proporcionadas."""
    datos = request.get_json(silent=True) or {}
    texto_urls = datos.get("urls", "")
    bitrate = datos.get("bitrate", BITRATE_POR_DEFECTO)

    urls = _parsear_urls(texto_urls)
    if not urls:
        return jsonify({"error": "No se encontraron URLs válidas."}), 400

    tarea_id = uuid.uuid4().hex[:12]
    tarea = TareaDescarga(
        id=tarea_id,
        items=[ItemDescarga(url=url) for url in urls],
    )
    tareas[tarea_id] = tarea

    hilo = threading.Thread(
        target=_ejecutar_descarga,
        args=(tarea, bitrate),
        daemon=True,
    )
    hilo.start()

    return jsonify({"tarea_id": tarea_id, "urls": urls})


@app.route("/api/progreso/<tarea_id>")
def api_progreso(tarea_id: str):
    """Stream SSE con el progreso de una tarea."""
    tarea = tareas.get(tarea_id)
    if tarea is None:
        return jsonify({"error": "Tarea no encontrada."}), 404

    def generar():
        while True:
            try:
                evento = tarea.cola_eventos.get(timeout=60)
            except queue.Empty:
                # Keep-alive para evitar timeout del navegador.
                yield ":\n\n"
                continue
            if evento is None:
                break
            yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"

    return Response(generar(), mimetype="text/event-stream")


@app.route("/api/archivos")
def api_archivos():
    """Lista los MP3 descargados."""
    archivos = []
    if CARPETA_DESCARGAS.exists():
        for f in sorted(CARPETA_DESCARGAS.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True):
            archivos.append({
                "nombre": f.name,
                "tamaño": f.stat().st_size,
            })
    return jsonify(archivos)


@app.route("/descargas/<path:nombre>")
def servir_archivo(nombre: str):
    """Sirve un archivo MP3 descargado."""
    return send_from_directory(CARPETA_DESCARGAS, nombre, as_attachment=True)


# --------------------------------------------------------------------------- #
# Punto de entrada
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    print("Descargador de Musica Personal")
    print("Abre http://localhost:5000 en tu navegador")
    print()
    app.run(debug=False, host="127.0.0.1", port=5000)
