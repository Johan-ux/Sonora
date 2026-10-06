#!/usr/bin/env python3
"""Capa de persistencia SQLite para la app "Sonora".

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
    id          TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    titulo      TEXT DEFAULT '',
    thumbnail   TEXT DEFAULT '',
    duracion    TEXT DEFAULT '',
    canal       TEXT DEFAULT '',
    estado      TEXT DEFAULT 'en_cola',  -- en_cola | descargando | completado | error
    error       TEXT DEFAULT '',
    carpeta     TEXT DEFAULT '',         -- ruta relativa bajo descargas/ ('' = raíz)
    bitrate     TEXT DEFAULT '320',      -- calidad de audio (kbps) si formato='audio'
    creado      TEXT DEFAULT '',         -- ISO-8601
    posicion    INTEGER DEFAULT 0,       -- orden incremental
    lote        TEXT DEFAULT '',         -- id del lote (agrupa una playlist); '' = suelto
    lote_nombre TEXT DEFAULT '',         -- nombre visible del lote
    formato     TEXT DEFAULT 'audio',    -- audio (MP3) | video (MP4)
    resolucion  TEXT DEFAULT '1080'      -- alto máx. de vídeo si formato='video'
);
CREATE TABLE IF NOT EXISTS historial (
    id         TEXT PRIMARY KEY,
    url        TEXT,
    titulo     TEXT,
    canal      TEXT,
    archivo    TEXT,   -- ruta relativa del mp3/mp4 resultante bajo descargas/ (puede ser '')
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
    return {clave: fila[clave] for clave in fila.keys()}  # noqa: SIM118


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
        _migrar(conexion)
        conexion.commit()
        _conexion = conexion


def _migrar(conexion: sqlite3.Connection) -> None:
    """Migra esquemas antiguos: añade columnas nuevas a 'cola' si faltan.

    Permite que una base de datos creada por una versión anterior (sin las
    columnas de lotes) siga funcionando sin perder datos.
    """
    columnas = {fila["name"] for fila in conexion.execute("PRAGMA table_info(cola)")}
    if "lote" not in columnas:
        conexion.execute("ALTER TABLE cola ADD COLUMN lote TEXT DEFAULT ''")
    if "lote_nombre" not in columnas:
        conexion.execute("ALTER TABLE cola ADD COLUMN lote_nombre TEXT DEFAULT ''")
    if "formato" not in columnas:
        conexion.execute("ALTER TABLE cola ADD COLUMN formato TEXT DEFAULT 'audio'")
    if "resolucion" not in columnas:
        conexion.execute("ALTER TABLE cola ADD COLUMN resolucion TEXT DEFAULT '1080'")


def _insertar_item(conexion: sqlite3.Connection, item: dict) -> None:
    """Inserta un ítem en la cola. El llamador debe tener tomado ``_lock``."""
    fila = conexion.execute(
        "SELECT COALESCE(MAX(posicion), 0) + 1 AS siguiente FROM cola"
    ).fetchone()
    siguiente_posicion = fila["siguiente"] if fila else 1

    conexion.execute(
        """
        INSERT INTO cola (
            id, url, titulo, thumbnail, duracion, canal,
            estado, error, carpeta, bitrate, creado, posicion,
            lote, lote_nombre, formato, resolucion
        ) VALUES (
            :id, :url, :titulo, :thumbnail, :duracion, :canal,
            'en_cola', '', :carpeta, :bitrate, :creado, :posicion,
            :lote, :lote_nombre, :formato, :resolucion
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
            "lote": item.get("lote", "") or "",
            "lote_nombre": item.get("lote_nombre", "") or "",
            "formato": item.get("formato", "audio") or "audio",
            "resolucion": item.get("resolucion", "1080") or "1080",
        },
    )


def cola_agregar(item: dict) -> None:
    """Inserta un ítem nuevo en la cola con estado 'en_cola'.

    ``item`` debe traer las claves: id, url, titulo, thumbnail, duracion,
    canal, carpeta, bitrate, creado. Opcionalmente lote y lote_nombre (para
    agrupar una playlist). La posición se calcula como max+1 para mantener un
    orden incremental estable.
    """
    with _lock:
        conexion = _obtener_conexion()
        _insertar_item(conexion, item)
        conexion.commit()


def cola_agregar_si_no_activa(item: dict) -> bool:
    """Inserta el ítem SOLO si su URL no está ya pendiente o descargándose.

    La comprobación y la inserción ocurren bajo el mismo lock, de modo que dos
    peticiones concurrentes (p. ej. «Añadir todo» y un lote a la vez) no pueden
    colarse entre el check y el insert y duplicar la canción. Devuelve True si
    insertó, False si la URL ya estaba activa.
    """
    with _lock:
        conexion = _obtener_conexion()
        fila = conexion.execute(
            "SELECT 1 FROM cola WHERE url = ? AND estado IN ('en_cola', 'descargando') "
            "LIMIT 1",
            (item["url"],),
        ).fetchone()
        if fila is not None:
            return False
        _insertar_item(conexion, item)
        conexion.commit()
        return True


def cola_agregar_varios_si_no_activas(items: list[dict]) -> list[str]:
    """Inserta de una vez los ítems cuya URL no esté ya pendiente o bajando.

    Es ``cola_agregar_si_no_activa`` para una playlist entera: una sola
    transacción en lugar de un ``commit`` (una escritura a disco) por canción.
    Devuelve los ids insertados; el resto se omitió por estar ya en la cola o
    por repetirse dentro de la propia lista.
    """
    insertados: list[str] = []
    with _lock:
        conexion = _obtener_conexion()
        activas = {
            fila["url"] for fila in conexion.execute(
                "SELECT url FROM cola WHERE estado IN ('en_cola', 'descargando')"
            )
        }
        for item in items:
            if item["url"] in activas:
                continue
            try:
                _insertar_item(conexion, item)
            except sqlite3.Error:
                continue  # un ítem inválido no aborta el resto
            activas.add(item["url"])
            insertados.append(item["id"])
        conexion.commit()
    return insertados


def cola_obtener(item_id: str) -> dict | None:
    """Devuelve el ítem de la cola con ese id, o None si no existe."""
    with _lock:
        conexion = _obtener_conexion()
        fila = conexion.execute("SELECT * FROM cola WHERE id = ?", (item_id,)).fetchone()
    return _fila_a_dict(fila)


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


def cola_eliminar_lote(lote: str) -> int:
    """Borra todos los ítems 'en_cola' de un lote. Devuelve cuántos borró.

    No toca los que ya estén descargando/completados/error (solo los pendientes).
    """
    if not lote:
        return 0
    with _lock:
        conexion = _obtener_conexion()
        cursor = conexion.execute(
            "DELETE FROM cola WHERE lote = ? AND estado = 'en_cola'",
            (lote,),
        )
        conexion.commit()
        return cursor.rowcount


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


def cola_reclamar(item_id: str) -> bool:
    """Marca un ítem como 'descargando' SOLO si sigue 'en_cola' (atómico).

    Evita la carrera entre el worker y los endpoints HTTP: si el usuario
    eliminó el ítem justo cuando el worker iba a procesarlo, el UPDATE no
    afecta a ninguna fila y el worker lo salta.
    """
    with _lock:
        conexion = _obtener_conexion()
        cursor = conexion.execute(
            "UPDATE cola SET estado = 'descargando', error = '' "
            "WHERE id = ? AND estado = 'en_cola'",
            (item_id,),
        )
        conexion.commit()
        return cursor.rowcount > 0


# Reactiva un ítem en error SOLO si su URL no está ya pendiente o bajando en
# otra fila. Sin esa condición, reintentar una canción que el usuario ya volvió
# a añadir dejaría dos ítems activos con la misma URL, y dos workers
# escribiendo el mismo fichero a la vez.
_SQL_REINTENTAR = (
    "UPDATE cola SET estado = 'en_cola', error = '' "
    "WHERE id = ? AND estado = 'error' AND NOT EXISTS ("
    "    SELECT 1 FROM cola AS otra"
    "    WHERE otra.url = cola.url AND otra.id <> cola.id"
    "      AND otra.estado IN ('en_cola', 'descargando')"
    ")"
)


def cola_reintentar(item_id: str) -> bool:
    """Devuelve un ítem 'error' a 'en_cola' para reintentarlo.

    Devuelve False si no estaba en error o si su URL ya está activa en otro
    ítem (se quedaría duplicada).
    """
    with _lock:
        conexion = _obtener_conexion()
        cursor = conexion.execute(_SQL_REINTENTAR, (item_id,))
        conexion.commit()
        return cursor.rowcount > 0


def cola_reintentar_errores() -> int:
    """Devuelve a 'en_cola' los ítems 'error'. Devuelve cuántos.

    Va de uno en uno, en orden: si dos ítems en error comparten URL, el primero
    se reactiva y el segundo, que ya la encuentra activa, se queda como está.
    """
    with _lock:
        conexion = _obtener_conexion()
        ids = [
            fila["id"] for fila in conexion.execute(
                "SELECT id FROM cola WHERE estado = 'error' ORDER BY posicion ASC"
            )
        ]
        reactivados = 0
        for item_id in ids:
            reactivados += conexion.execute(_SQL_REINTENTAR, (item_id,)).rowcount
        conexion.commit()
        return reactivados


def cola_urls_activas() -> set[str]:
    """URLs de los ítems pendientes o en curso ('en_cola' / 'descargando').

    Sirve para no encolar la misma canción dos veces (p. ej. doble clic en
    «Añadir» o añadir la misma playlist dos veces seguidas).
    """
    with _lock:
        conexion = _obtener_conexion()
        filas = conexion.execute(
            "SELECT url FROM cola WHERE estado IN ('en_cola', 'descargando')"
        ).fetchall()
    return {fila["url"] for fila in filas if fila["url"]}


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


def historial_eliminar(item_id: str) -> bool:
    """Borra una entrada concreta del historial. Devuelve True si borró algo.

    No toca el archivo en disco: el historial es solo un registro.
    """
    with _lock:
        conexion = _obtener_conexion()
        cursor = conexion.execute(
            "DELETE FROM historial WHERE id = ?",
            (item_id,),
        )
        conexion.commit()
        return cursor.rowcount > 0


def historial_limpiar() -> int:
    """Vacía todo el historial. Devuelve cuántas entradas borró.

    No toca los archivos en disco: el historial es solo un registro.
    """
    with _lock:
        conexion = _obtener_conexion()
        cursor = conexion.execute("DELETE FROM historial")
        conexion.commit()
        return cursor.rowcount


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
