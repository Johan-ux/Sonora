"""Tests de ``sonora.db`` contra una base de datos temporal (fixture entorno)."""

from __future__ import annotations

import sqlite3

from sonora import db


def _item(item_id: str = "abc123", url: str = "https://www.youtube.com/watch?v=abc", **extra) -> dict:
    base = {
        "id": item_id,
        "url": url,
        "titulo": "Canción de prueba",
        "thumbnail": "",
        "duracion": "3:33",
        "canal": "Canal",
        "carpeta": "",
        "bitrate": "320",
        "creado": "2026-01-01T00:00:00+00:00",
    }
    base.update(extra)
    return base


class TestCola:
    def test_agregar_y_listar(self, entorno):
        assert db.cola_listar() == []
        db.cola_agregar(_item("id1", "https://x/1"))
        db.cola_agregar(_item("id2", "https://x/2"))
        items = db.cola_listar()
        assert [i["id"] for i in items] == ["id1", "id2"]
        assert items[0]["estado"] == "en_cola"
        assert items[0]["progreso"] == 0.0
        # posición incremental estable
        assert items[0]["posicion"] < items[1]["posicion"]

    def test_eliminar_en_cola(self, entorno):
        db.cola_agregar(_item("id1"))
        assert db.cola_eliminar("id1") is True
        assert db.cola_listar() == []

    def test_eliminar_inexistente(self, entorno):
        assert db.cola_eliminar("no-existe") is False

    def test_eliminar_no_borra_descargando(self, entorno):
        db.cola_agregar(_item("id1"))
        assert db.cola_reclamar("id1") is True  # pasa a 'descargando'
        assert db.cola_eliminar("id1") is False
        assert [i["id"] for i in db.cola_listar()] == ["id1"]

    def test_reclamar_solo_en_cola(self, entorno):
        db.cola_agregar(_item("id1"))
        assert db.cola_reclamar("id1") is True
        # Segunda llamada: ya no está 'en_cola', no debe reclamarse otra vez.
        assert db.cola_reclamar("id1") is False
        assert db.cola_listar()[0]["estado"] == "descargando"

    def test_reclamar_inexistente(self, entorno):
        assert db.cola_reclamar("no-existe") is False

    def test_reintentar(self, entorno):
        db.cola_agregar(_item("id1"))
        db.cola_actualizar_estado("id1", "error", "boom")
        assert db.cola_reintentar("id1") is True
        item = db.cola_listar()[0]
        assert item["estado"] == "en_cola"
        assert item["error"] == ""
        # Ya no está en error: reintentarlo de nuevo devuelve False.
        assert db.cola_reintentar("id1") is False

    def test_reintentar_no_error(self, entorno):
        db.cola_agregar(_item("id1"))  # estado 'en_cola'
        assert db.cola_reintentar("id1") is False

    def test_reintentar_errores(self, entorno):
        db.cola_agregar(_item("id1", "https://x/1"))
        db.cola_agregar(_item("id2", "https://x/2"))
        db.cola_agregar(_item("id3", "https://x/3"))
        db.cola_actualizar_estado("id1", "error", "boom 1")
        db.cola_actualizar_estado("id2", "error", "boom 2")
        assert db.cola_reintentar_errores() == 2
        estados = {i["id"]: i["estado"] for i in db.cola_listar()}
        assert estados == {"id1": "en_cola", "id2": "en_cola", "id3": "en_cola"}

    def test_urls_activas(self, entorno):
        db.cola_agregar(_item("id1", "https://x/1"))
        db.cola_agregar(_item("id2", "https://x/2"))
        db.cola_agregar(_item("id3", "https://x/3"))
        db.cola_reclamar("id1")                              # descargando: activa
        db.cola_actualizar_estado("id2", "completado")       # completado: NO activa
        assert db.cola_urls_activas() == {"https://x/1", "https://x/3"}


class TestHistorial:
    def test_agregar_y_listar(self, entorno):
        db.historial_agregar({
            "id": "h1",
            "url": "https://x/1",
            "titulo": "Uno",
            "canal": "Canal",
            "archivo": "Uno [h1].mp3",
            "carpeta": "",
            "completado": "2026-01-01T10:00:00+00:00",
        })
        db.historial_agregar({
            "id": "h2",
            "url": "https://x/2",
            "titulo": "Dos",
            "canal": "Canal",
            "archivo": "Dos [h2].mp3",
            "carpeta": "rock",
            "completado": "2026-01-02T10:00:00+00:00",
        })
        items = db.historial_listar()
        # Más recientes primero (orden por 'completado' descendente).
        assert [i["id"] for i in items] == ["h2", "h1"]
        assert items[0]["archivo"] == "Dos [h2].mp3"

    def test_reemplaza_por_id(self, entorno):
        db.historial_agregar({"id": "h1", "titulo": "Original", "completado": "2026-01-01"})
        db.historial_agregar({"id": "h1", "titulo": "Actualizado", "completado": "2026-01-02"})
        items = db.historial_listar()
        assert len(items) == 1
        assert items[0]["titulo"] == "Actualizado"

    def test_limite(self, entorno):
        for i in range(5):
            db.historial_agregar({"id": f"h{i}", "completado": f"2026-01-0{i + 1}"})
        assert len(db.historial_listar(limite=3)) == 3
        # Límite inválido: cae al valor por defecto sin lanzar.
        assert len(db.historial_listar(limite="abc")) == 5


class TestConfig:
    def test_guardar_y_obtener(self, entorno):
        assert db.config_obtener("no-existe", "defecto") == "defecto"
        db.config_guardar("bitrate_por_defecto", "192")
        assert db.config_obtener("bitrate_por_defecto") == "192"
        # Upsert: el segundo guardado sobrescribe.
        db.config_guardar("bitrate_por_defecto", "128")
        assert db.config_obtener("bitrate_por_defecto") == "128"


class TestMigracion:
    def test_migrar_bd_sin_columnas_lote(self, entorno, tmp_path):
        """Una BD de una versión antigua (sin lote/lote_nombre) se migra sola."""
        ruta = tmp_path / "vieja.db"
        conexion = sqlite3.connect(str(ruta))
        conexion.execute(
            """
            CREATE TABLE cola (
                id        TEXT PRIMARY KEY,
                url       TEXT NOT NULL,
                titulo    TEXT DEFAULT '',
                thumbnail TEXT DEFAULT '',
                duracion  TEXT DEFAULT '',
                canal     TEXT DEFAULT '',
                estado    TEXT DEFAULT 'en_cola',
                error     TEXT DEFAULT '',
                carpeta   TEXT DEFAULT '',
                bitrate   TEXT DEFAULT '320',
                creado    TEXT DEFAULT '',
                posicion  INTEGER DEFAULT 0
            )
            """
        )
        conexion.execute(
            "INSERT INTO cola (id, url, posicion) VALUES ('viejo1', 'https://x/v', 1)"
        )
        conexion.commit()
        conexion.close()

        # inicializar() ejecuta _migrar(): debe añadir las columnas que faltan
        # sin perder los datos existentes.
        db.inicializar(ruta)
        items = db.cola_listar()
        assert len(items) == 1
        assert items[0]["id"] == "viejo1"
        assert items[0]["lote"] == ""
        assert items[0]["lote_nombre"] == ""

        # Y la BD migrada admite ítems nuevos con lote.
        db.cola_agregar(_item("nuevo1", "https://x/n", lote="l1", lote_nombre="Lote 1/1"))
        nuevos = {i["id"]: i for i in db.cola_listar()}
        assert nuevos["nuevo1"]["lote"] == "l1"
        assert nuevos["nuevo1"]["lote_nombre"] == "Lote 1/1"
