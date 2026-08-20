"""Difusión de eventos en tiempo real (Server-Sent Events).

Mantiene el conjunto de clientes conectados (una cola por cliente) y difunde a
todos ellos. Es seguro para hilos: el worker de descargas y los handlers HTTP
pueden emitir desde distintos hilos.
"""

from __future__ import annotations

import json
import queue
import threading

# Una cola por cliente SSE conectado; protegido por su propio lock.
_CLIENTES: set[queue.Queue[str]] = set()
_LOCK = threading.Lock()


def registrar_cliente() -> queue.Queue[str]:
    """Crea y registra una cola para un nuevo cliente SSE."""
    cliente: queue.Queue[str] = queue.Queue(maxsize=200)
    with _LOCK:
        _CLIENTES.add(cliente)
    return cliente


def eliminar_cliente(cliente: queue.Queue[str]) -> None:
    """Da de baja un cliente SSE (al desconectarse)."""
    with _LOCK:
        _CLIENTES.discard(cliente)


def emitir(evento: dict) -> None:
    """Difunde un evento (dict serializable) a todos los clientes SSE.

    Nunca lanza: si un cliente tiene la cola llena, se descarta ese evento para
    no bloquear al emisor (p. ej. el worker de descargas).
    """
    try:
        mensaje = json.dumps(evento, ensure_ascii=False)
    except (TypeError, ValueError):
        return
    with _LOCK:
        clientes = list(_CLIENTES)
    for cliente in clientes:
        try:
            cliente.put_nowait(mensaje)
        except queue.Full:
            pass
