"""Ruta de eventos en tiempo real (Server-Sent Events)."""

from __future__ import annotations

import json
import queue

from flask import Blueprint, Response

from .. import sse
from ..servicios import descargas

bp = Blueprint("eventos", __name__)


@bp.get("/api/eventos")
def eventos():
    """Flujo de eventos en tiempo real (SSE) con heartbeat periódico."""
    cliente = sse.registrar_cliente()

    def generar():
        # Estado inicial: enviamos la cola actual al conectar.
        try:
            inicial = json.dumps(
                {"tipo": "cola_actualizada", "items": descargas.listar_cola_con_progreso()},
                ensure_ascii=False,
            )
            yield f"data: {inicial}\n\n"
            while True:
                try:
                    mensaje = cliente.get(timeout=30)
                    yield f"data: {mensaje}\n\n"
                except queue.Empty:
                    # Heartbeat: comentario SSE para mantener viva la conexión.
                    yield ":\n\n"
        except GeneratorExit:
            # El cliente se desconectó.
            pass
        finally:
            sse.eliminar_cliente(cliente)

    respuesta = Response(generar(), mimetype="text/event-stream")
    respuesta.headers["Cache-Control"] = "no-cache"
    respuesta.headers["X-Accel-Buffering"] = "no"
    respuesta.headers["Connection"] = "keep-alive"
    return respuesta
