#!/usr/bin/env python3
"""Capa de persistencia SQLite para la app "Mi Música".

Gestiona tres tablas: la cola de descargas, el historial de descargas
completadas y la configuración (clave/valor).

Diseño:
    * Una única conexión a nivel de módulo, compartida entre hilos
      (``check_same_thread=False``) y protegida por un ``threading.Lock``
      global. El uso es personal y de baja concurrencia, así que un único
      lock global es suficiente y robusto.
    * ``row_factory = sqlite3.Row`` para acceder a las columnas por nombre.
    * ``PRAGMA journal_mode=WAL`` para mejor concurrencia lectura/escritura.
    * Todas las funciones que devuelven filas las convierten a ``dict``
      (JSON-serializable); nunca se filtran objetos ``sqlite3.Row`` hacia
      la capa web.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

# --- Estado del módulo -----------------------------------------------------

# Conexión única compartida por todos los hilos. Se inicializa en
# ``inicializar()``; mientras tanto es None.
_conexion: sqlite3.Connection | None = None

# Lock global que serializa TODOS los accesos a la conexión. SQLite con una
# sola conexión compartida no es seguro para escrituras concurrentes sin
# sincronización, así que envolvemos cada operación con este lock.
_lock = threading.Lock()


# --- Esquema ---------------------------------------------------------------

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS cola (
    id        TEXT PRIMARY KEY,
    url       TEXT NOT NULL,
    titulo    TEXT DEFAULT '',
    thumbnail TEXT DEFAULT '',
    duracion  TEXT DEFAULT '',
    canal     TEXT DEFAULT '',
    estado    TEXT DEFAULT 'en_cola',   -- en_cola | descargando | completado | error
    error     TEXT DEFAULT '',
    carpeta   TEXT DEFAULT '',          -- ruta relativa bajo descargas/ ('' = raíz)
    bitrate   TEXT DEFAULT '320',
    creado    TEXT DEFAULT '',          -- ISO-8601
    posicion  INTEGER DEFAULT 0         -- orden incremental
);
CREATE TABLE IF NOT EXISTS historial (
    id         TEXT PRIMARY KEY,
    url        TEXT,
    titulo     TEXT,
    canal      TEXT,
    archivo    TEXT,   -- ruta relativa del mp3 resultante bajo descargas/ (puede ser '')
    carpeta    TEXT,
    completado TEXT     -- ISO-8601
);
CREATE TABLE IF NOT EXISTS config (
    clave TEXT PRIMARY KEY,
    valor TEXT
);
"""


# --- Utilidades internas ---------------------------------------------------


def _obtener_conexion() -> sqlite3.Connection:
    """Devuelve la conexión activa o lanza un error claro si no se inicializó."""
    if _conexion is None:
        raise RuntimeError(
            "db.py no está inicializado: llama a db.inicializar(db_path) primero."
        )
    return _conexion


def _fila_a_dict(fila: sqlite3.Row | None) -> dict | None:
    """Convierte una ``sqlite3.Row`` en un ``dict`` JSON-serializable."""
    if fila is None:
        return None
    return {clave: fila[clave] for clave in fila.keys()}


# --- API pública -----------------------------------------------------------


def inicializar(db_path: str | Path) -> None:
    """Abre la conexión SQLite, crea las tablas y aplica el modo WAL.

    Es idempotente: si se llama de nuevo, cierra la conexión previa y la
    vuelve a abrir contra la ruta indicada.
    """
    global _conexion
    with _lock:
        # Cerrar una posible conexión anterior (re-inicialización limpia).
        if _conexion is not None:
            try:
                _conexion.close()
            except sqlite3.Error:
                pass
            _conexion = None

        conexion = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
        )
        conexion.row_factory = sqlite3.Row
        # WAL mejora la concurrencia lectura/escritura; foreign_keys por higiene.
        conexion.execute("PRAGMA journal_mode=WAL;")
        conexion.execute("PRAGMA foreign_keys=ON;")
        conexion.executescript(_ESQUEMA)
        conexion.commit()
        _conexion = conexion


def cola_agregar(item: dict) -> None:
    """Inserta un ítem nuevo en la cola con estado 'en_cola'.

    ``item`` debe traer las claves: id, url, titulo, thumbnail, duracion,
    canal, carpeta, bitrate, creado. La posición se calcula como max+1 para
    mantener un orden incremental estable.
    """
    with _lock:
        conexion = _obtener_conexion()
        fila = conexion.execute(
            "SELECT COALESCE(MAX(posicion), 0) + 1 AS siguiente FROM cola"
        ).fetchone()
        siguiente_posicion = fila["siguiente"] if fila else 1

        conexion.execute(
            """
            INSERT INTO cola (
                id, url, titulo, thumbnail, duracion, canal,
                estado, error, carpeta, bitrate, creado, posicion
            ) VALUES (
                :id, :url, :titulo, :thumbnail, :duracion, :canal,
                'en_cola', '', :carpeta, :bitrate, :creado, :posicion
            )
            """,
            {
                "id": item["id"],
                "url": item["url"],
                "titulo": item.get("titulo", "") or "",
                "thumbnail": item.get("thumbnail", "") or "",
                "duracion": item.get("duracion", "") or "",
                "canal": item.get("canal", "") or "",
                "carpeta": item.get("carpeta", "") or "",
                "bitrate": item.get("bitrate", "320") or "320",
                "creado": item.get("creado", "") or "",
                "posicion": siguiente_posicion,
            },
        )
        conexion.commit()


def cola_eliminar(item_id: str) -> bool:
    """Borra un ítem de la cola solo si su estado es 'en_cola'.

    Devuelve True si efectivamente borró una fila, False en caso contrario
    (no existe o ya está descargando/completado/error).
    """
    with _lock:
        conexion = _obtener_conexion()
        cursor = conexion.execute(
            "DELETE FROM cola WHERE id = ? AND estado = 'en_cola'",
            (item_id,),
        )
        conexion.commit()
        return cursor.rowcount > 0


def cola_listar() -> list[dict]:
    """Devuelve todas las filas de la cola ordenadas por posición ascendente.

    Cada dict incluye TODAS las columnas más la clave 'progreso' (float,
    0.0 por defecto). app.py sobrescribe 'progreso' con el progreso vivo del
    ítem que se esté descargando en ese momento.
    """
    with _lock:
        conexion = _obtener_conexion()
        filas = conexion.execute(
            "SELECT * FROM cola ORDER BY posicion ASC"
        ).fetchall()

    resultado: list[dict] = []
    for fila in filas:
        registro = _fila_a_dict(fila) or {}
        registro["progreso"] = 0.0
        resultado.append(registro)
    return resultado


def cola_actualizar_estado(item_id: str, estado: str, error: str = "") -> None:
    """Actualiza el estado (y opcionalmente el mensaje de error) de un ítem."""
    with _lock:
        conexion = _obtener_conexion()
        conexion.execute(
            "UPDATE cola SET estado = ?, error = ? WHERE id = ?",
            (estado, error or "", item_id),
        )
        conexion.commit()


def cola_siguiente_en_cola() -> dict | None:
    """Devuelve el ítem 'en_cola' de menor posición, o None si no hay ninguno."""
    with _lock:
        conexion = _obtener_conexion()
        fila = conexion.execute(
            "SELECT * FROM cola WHERE estado = 'en_cola' "
            "ORDER BY posicion ASC LIMIT 1"
        ).fetchone()
    return _fila_a_dict(fila)


def cola_limpiar_terminados() -> None:
    """Borra de la cola las filas en estado 'completado' o 'error'."""
    with _lock:
        conexion = _obtener_conexion()
        conexion.execute(
            "DELETE FROM cola WHERE estado IN ('completado', 'error')"
        )
        conexion.commit()


def cola_reiniciar_descargando() -> None:
    """Al arrancar, devuelve a 'en_cola' los ítems que quedaron 'descargando'.

    Esto recupera descargas que se interrumpieron al cerrar la app y limpia
    cualquier mensaje de error parcial de esos ítems.
    """
    with _lock:
        conexion = _obtener_conexion()
        conexion.execute(
            "UPDATE cola SET estado = 'en_cola', error = '' "
            "WHERE estado = 'descargando'"
        )
        conexion.commit()


def historial_agregar(item: dict) -> None:
    """Inserta (o reemplaza por id) una entrada en el historial.

    ``item`` debe traer: id, url, titulo, canal, archivo, carpeta, completado.
    """
    with _lock:
        conexion = _obtener_conexion()
        conexion.execute(
            """
            INSERT OR REPLACE INTO historial (
                id, url, titulo, canal, archivo, carpeta, completado
            ) VALUES (
                :id, :url, :titulo, :canal, :archivo, :carpeta, :completado
            )
            """,
            {
                "id": item["id"],
                "url": item.get("url", "") or "",
                "titulo": item.get("titulo", "") or "",
                "canal": item.get("canal", "") or "",
                "archivo": item.get("archivo", "") or "",
                "carpeta": item.get("carpeta", "") or "",
                "completado": item.get("completado", "") or "",
            },
        )
        conexion.commit()


def historial_listar(limite: int = 100) -> list[dict]:
    """Devuelve las entradas del historial, las más recientes primero.

    Ordena por la fecha de completado descendente y limita la cantidad.
    """
    # Saneamos el límite para evitar valores inválidos.
    try:
        limite = int(limite)
    except (TypeError, ValueError):
        limite = 100
    if limite <= 0:
        limite = 100

    with _lock:
        conexion = _obtener_conexion()
        filas = conexion.execute(
            "SELECT * FROM historial ORDER BY completado DESC LIMIT ?",
            (limite,),
        ).fetchall()

    return [_fila_a_dict(fila) for fila in filas if fila is not None]  # type: ignore[misc]


def config_obtener(clave: str, por_defecto: str = "") -> str:
    """Devuelve el valor de configuración para ``clave`` o ``por_defecto``."""
    with _lock:
        conexion = _obtener_conexion()
        fila = conexion.execute(
            "SELECT valor FROM config WHERE clave = ?",
            (clave,),
        ).fetchone()
    if fila is None or fila["valor"] is None:
        return por_defecto
    return fila["valor"]


def config_guardar(clave: str, valor: str) -> None:
    """Guarda (upsert) un valor de configuración bajo ``clave``."""
    with _lock:
        conexion = _obtener_conexion()
        conexion.execute(
            """
            INSERT INTO config (clave, valor) VALUES (?, ?)
            ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
            """,
            (clave, valor),
        )
        conexion.commit()
