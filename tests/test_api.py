"""Tests de la API HTTP con el test client de Flask.

La red nunca se toca: el servicio ``sonora.servicios.youtube`` se monkeypatchea
en los tests de búsqueda, y el worker de descargas queda desactivado por el
autouse fixture ``sin_worker`` (no se llama a /api/cola/descargar y
``arrancar_worker`` es un no-op). Los endpoints de cola emiten SSE
(``sonora.sse.emitir``), que sin clientes conectados es inofensivo.
"""

from __future__ import annotations

import pytest

import sonora.servicios.descargas as descargas
import sonora.servicios.youtube as youtube
from sonora import db


@pytest.fixture(autouse=True)
def sin_worker(monkeypatch):
    """El worker de descargas NUNCA debe arrancar durante los tests."""
    monkeypatch.setattr(descargas, "arrancar_worker", lambda: None)


# --------------------------------------------------------------------------- #
# /api/buscar
# --------------------------------------------------------------------------- #

class TestBuscar:
    def test_sin_q_devuelve_400(self, client):
        respuesta = client.post("/api/buscar", json={})
        assert respuesta.status_code == 400
        assert "error" in respuesta.get_json()

    def test_busqueda_texto_devuelve_resultados_del_mock(self, client, monkeypatch):
        resultados = [
            {
                "id": "abc",
                "url": "https://www.youtube.com/watch?v=abc",
                "titulo": "Canción",
                "canal": "Canal",
                "duracion": "3:00",
                "thumbnail": "https://i.ytimg.com/vi/abc/mqdefault.jpg",
            }
        ]
        llamadas = {}

        def falso_buscar(q, n):
            llamadas["q"], llamadas["n"] = q, n
            return resultados

        monkeypatch.setattr(youtube, "buscar_ytsearch", falso_buscar)
        respuesta = client.post("/api/buscar", json={"q": "beatles", "n": 5})
        assert respuesta.status_code == 200
        datos = respuesta.get_json()
        assert datos["resultados"] == resultados
        assert datos["es_playlist"] is False
        assert llamadas == {"q": "beatles", "n": 5}


# --------------------------------------------------------------------------- #
# /api/cola/*
# --------------------------------------------------------------------------- #

class TestColaAgregar:
    URL = "https://www.youtube.com/watch?v=abc"

    def test_sin_url_devuelve_400(self, client):
        respuesta = client.post("/api/cola/agregar", json={})
        assert respuesta.status_code == 400

    def test_agregar_ok_y_aparece_en_la_cola(self, client):
        respuesta = client.post(
            "/api/cola/agregar",
            json={"url": self.URL, "titulo": "Canción", "bitrate": "192"},
        )
        assert respuesta.status_code == 200
        datos = respuesta.get_json()
        assert datos["ok"] is True
        assert datos["duplicado"] is False
        assert datos["id"]

        cola = client.get("/api/cola").get_json()["items"]
        assert len(cola) == 1
        assert cola[0]["url"] == self.URL
        assert cola[0]["estado"] == "en_cola"
        assert cola[0]["bitrate"] == "192"
        # Sin pedir formato, el ítem es de audio por defecto.
        assert cola[0]["formato"] == "audio"

    def test_agregar_video_guarda_formato_y_resolucion(self, client):
        respuesta = client.post(
            "/api/cola/agregar",
            json={"url": self.URL, "formato": "video", "resolucion": "720"},
        )
        assert respuesta.status_code == 200
        cola = client.get("/api/cola").get_json()["items"]
        assert cola[0]["formato"] == "video"
        assert cola[0]["resolucion"] == "720"

    def test_agregar_video_resolucion_invalida_cae_a_1080(self, client):
        client.post(
            "/api/cola/agregar",
            json={"url": self.URL, "formato": "video", "resolucion": "9999"},
        )
        cola = client.get("/api/cola").get_json()["items"]
        assert cola[0]["resolucion"] == "1080"

    def test_url_duplicada_no_se_duplica(self, client):
        client.post("/api/cola/agregar", json={"url": self.URL})
        respuesta = client.post("/api/cola/agregar", json={"url": self.URL})
        assert respuesta.status_code == 200
        assert respuesta.get_json() == {"ok": True, "duplicado": True}
        cola = client.get("/api/cola").get_json()["items"]
        assert len(cola) == 1

    def test_url_entera_no_provoca_500(self, client):
        # Un cliente raro (o un curl manual) puede mandar un int donde se
        # espera texto; el helper texto() lo tolera convirtiéndolo a cadena.
        respuesta = client.post("/api/cola/agregar", json={"url": 12345})
        assert respuesta.status_code == 200
        cola = client.get("/api/cola").get_json()["items"]
        assert cola[0]["url"] == "12345"

    def test_bitrate_invalido_se_normaliza(self, client):
        client.post("/api/cola/agregar", json={"url": self.URL, "bitrate": "999"})
        cola = client.get("/api/cola").get_json()["items"]
        assert cola[0]["bitrate"] == "320"


class TestColaEliminarReintentar:
    def test_eliminar_inexistente_devuelve_409(self, client):
        respuesta = client.post("/api/cola/eliminar", json={"id": "no-existe"})
        assert respuesta.status_code == 409

    def test_eliminar_sin_id_devuelve_400(self, client):
        assert client.post("/api/cola/eliminar", json={}).status_code == 400

    def test_reintentar_item_que_no_esta_en_error_devuelve_409(self, client):
        client.post("/api/cola/agregar", json={"url": "https://x/1"})
        item_id = client.get("/api/cola").get_json()["items"][0]["id"]
        respuesta = client.post("/api/cola/reintentar", json={"id": item_id})
        assert respuesta.status_code == 409

    def test_reintentar_item_en_error(self, client):
        # El autouse fixture sin_worker garantiza que arrancar_worker es no-op.
        client.post("/api/cola/agregar", json={"url": "https://x/1"})
        item_id = client.get("/api/cola").get_json()["items"][0]["id"]
        db.cola_actualizar_estado(item_id, "error", "boom")
        respuesta = client.post("/api/cola/reintentar", json={"id": item_id})
        assert respuesta.status_code == 200
        assert respuesta.get_json()["ok"] is True
        assert client.get("/api/cola").get_json()["items"][0]["estado"] == "en_cola"


class TestAgregarPlaylist:
    @staticmethod
    def _items(n, prefijo="v"):
        return [
            {"url": f"https://www.youtube.com/watch?v={prefijo}{i}", "titulo": f"Tema {i}"}
            for i in range(n)
        ]

    def test_sin_items_devuelve_400(self, client):
        assert client.post("/api/cola/agregar_playlist", json={}).status_code == 400
        assert (
            client.post("/api/cola/agregar_playlist", json={"items": []}).status_code == 400
        )

    def test_reparto_en_lotes(self, client):
        respuesta = client.post(
            "/api/cola/agregar_playlist",
            json={"titulo": "Mi Lista", "items": self._items(5), "tamano_lote": 2},
        )
        assert respuesta.status_code == 200
        datos = respuesta.get_json()
        assert datos == {"ok": True, "lotes": 3, "total": 5, "omitidas": 0}

        cola = client.get("/api/cola").get_json()["items"]
        assert len(cola) == 5
        nombres = [i["lote_nombre"] for i in cola]
        assert "Lote 1/3" in nombres[0]
        assert "Lote 3/3" in nombres[4]
        # Los ítems de un mismo lote comparten id de lote; lotes distintos, no.
        assert cola[0]["lote"] == cola[1]["lote"]
        assert cola[0]["lote"] != cola[2]["lote"]

    def test_nombre_lote_explicito(self, client):
        respuesta = client.post(
            "/api/cola/agregar_playlist",
            json={"items": self._items(2), "nombre_lote": "Lote 2/4"},
        )
        datos = respuesta.get_json()
        assert datos == {"ok": True, "lotes": 1, "total": 2, "omitidas": 0}
        cola = client.get("/api/cola").get_json()["items"]
        assert {i["lote_nombre"] for i in cola} == {"Lote 2/4"}
        assert len({i["lote"] for i in cola}) == 1

    def test_omitidas_duplicados(self, client):
        # Una URL ya activa en la cola + una repetida dentro de la propia lista.
        client.post("/api/cola/agregar", json={"url": "https://www.youtube.com/watch?v=v0"})
        items = self._items(3)
        items.append(dict(items[1]))  # duplicada dentro del envío
        respuesta = client.post("/api/cola/agregar_playlist", json={"items": items})
        datos = respuesta.get_json()
        assert datos["ok"] is True
        assert datos["omitidas"] == 2  # la ya activa (v0) + la repetida (v1)
        assert datos["total"] == 2     # solo v1 y v2 entran
        cola = client.get("/api/cola").get_json()["items"]
        assert len(cola) == 3  # v0 (suelta) + v1 + v2

    def test_todas_omitidas(self, client):
        client.post("/api/cola/agregar", json={"url": "https://www.youtube.com/watch?v=v0"})
        respuesta = client.post(
            "/api/cola/agregar_playlist", json={"items": self._items(1)}
        )
        assert respuesta.get_json() == {"ok": True, "lotes": 0, "total": 0, "omitidas": 1}


# --------------------------------------------------------------------------- #
# /api/config
# --------------------------------------------------------------------------- #

class TestConfig:
    def test_get_valores_por_defecto(self, client):
        datos = client.get("/api/config").get_json()
        assert datos["carpeta_por_defecto"] == ""
        assert datos["bitrate_por_defecto"] == "320"
        assert isinstance(datos["ffmpeg_disponible"], bool)

    def test_post_y_get(self, client):
        respuesta = client.post(
            "/api/config",
            json={"carpeta_por_defecto": "rock", "bitrate_por_defecto": "192"},
        )
        assert respuesta.status_code == 200
        datos = client.get("/api/config").get_json()
        assert datos["carpeta_por_defecto"] == "rock"
        assert datos["bitrate_por_defecto"] == "192"

    def test_bitrate_invalido_se_guarda_como_320(self, client):
        client.post("/api/config", json={"bitrate_por_defecto": "192"})
        client.post("/api/config", json={"bitrate_por_defecto": "999"})
        datos = client.get("/api/config").get_json()
        assert datos["bitrate_por_defecto"] == "320"

    def test_reproductor_valores_por_defecto(self, client):
        datos = client.get("/api/config").get_json()
        assert datos["volumen"] == 1.0
        assert datos["video_modo"] == "flotante"
        assert datos["video_geometria"] is None

    def test_reproductor_se_recuerda(self, client):
        client.post(
            "/api/config",
            json={
                "volumen": 0.35,
                "video_modo": "teatro",
                "video_geometria": {"x": 40.4, "y": 12, "lado": 640.6},
            },
        )
        datos = client.get("/api/config").get_json()
        assert datos["volumen"] == 0.35
        assert datos["video_modo"] == "teatro"
        # Se guarda en píxeles enteros.
        assert datos["video_geometria"] == {"x": 40, "y": 12, "lado": 641}

    @pytest.mark.parametrize(
        ("enviado", "guardado"),
        [(7, 1.0), (-3, 0.0), ("0.5", 0.5), ("alto", 1.0), (None, 1.0), (True, 1.0)],
    )
    def test_volumen_se_acota_entre_0_y_1(self, client, enviado, guardado):
        client.post("/api/config", json={"volumen": enviado})
        assert client.get("/api/config").get_json()["volumen"] == guardado

    def test_modo_de_video_invalido_cae_a_flotante(self, client):
        client.post("/api/config", json={"video_modo": "teatro"})
        client.post("/api/config", json={"video_modo": "cine"})
        assert client.get("/api/config").get_json()["video_modo"] == "flotante"

    @pytest.mark.parametrize(
        "geometria",
        [
            None,
            "aquí",
            [1, 2, 3],
            {"x": 1, "y": 2},
            {"x": "a", "y": 2, "lado": 300},
            {"x": 1, "y": 2, "lado": 0},
            {"x": 1, "y": True, "lado": 300},
        ],
    )
    def test_geometria_invalida_restablece_la_ventana(self, client, geometria):
        client.post("/api/config", json={"video_geometria": {"x": 1, "y": 2, "lado": 300}})
        client.post("/api/config", json={"video_geometria": geometria})
        assert client.get("/api/config").get_json()["video_geometria"] is None


# --------------------------------------------------------------------------- #
# /api/carpetas
# --------------------------------------------------------------------------- #

class TestCarpetas:
    def test_crear_ok(self, client, entorno):
        respuesta = client.post("/api/carpetas/crear", json={"nombre": "sub"})
        assert respuesta.status_code == 200
        assert respuesta.get_json() == {"ok": True, "ruta": "sub"}
        assert (entorno / "sub").is_dir()

    def test_crear_traversal_devuelve_400(self, client, entorno):
        respuesta = client.post("/api/carpetas/crear", json={"nombre": "../mal"})
        assert respuesta.status_code == 400
        assert not (entorno.parent / "mal").exists()

    def test_crear_nombre_con_puntos_interiores_ok(self, client, entorno):
        # "Rock..Pop" es un nombre legítimo: solo se rechaza '..' como nombre
        # completo (validación nueva).
        respuesta = client.post("/api/carpetas/crear", json={"nombre": "Rock..Pop"})
        assert respuesta.status_code == 200
        assert (entorno / "Rock..Pop").is_dir()

    def test_crear_sin_nombre_devuelve_400(self, client):
        assert client.post("/api/carpetas/crear", json={}).status_code == 400

    def test_listar_raiz(self, client, entorno):
        (entorno / "una").mkdir()
        datos = client.get("/api/carpetas").get_json()
        assert datos["ruta"] == ""
        assert datos["puede_subir"] is False
        assert [i["nombre"] for i in datos["items"]] == ["una"]


# --------------------------------------------------------------------------- #
# /audio/<rel>
# --------------------------------------------------------------------------- #

class TestAudio:
    def test_fichero_inexistente_devuelve_404(self, client):
        assert client.get("/audio/no-existe.mp3").status_code == 404

    def test_traversal_devuelve_404(self, client):
        # Tanto si el cliente HTTP normaliza el '../' (la ruta deja de casar
        # con /audio/...) como si llega al handler (resolver_dentro_descargas
        # devuelve None), el resultado debe ser 404: nunca sirve el fichero.
        assert client.get("/audio/../../x.mp3").status_code == 404

    def test_extension_no_mp3_devuelve_403(self, client, entorno):
        (entorno / "nota.txt").write_text("hola", encoding="utf-8")
        assert client.get("/audio/nota.txt").status_code == 403

    def test_sirve_mp3_existente(self, client, entorno):
        (entorno / "cancion.mp3").write_bytes(b"ID3fake")
        respuesta = client.get("/audio/cancion.mp3")
        assert respuesta.status_code == 200
        assert respuesta.mimetype == "audio/mpeg"
        respuesta.close()

    def test_sirve_mp4_con_mimetype_video(self, client, entorno):
        (entorno / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftyp")
        respuesta = client.get("/media/clip.mp4")
        assert respuesta.status_code == 200
        assert respuesta.mimetype == "video/mp4"
        respuesta.close()


# --------------------------------------------------------------------------- #
# /api/historial/*
# --------------------------------------------------------------------------- #

class TestHistorial:
    def _sembrar(self, n):
        for i in range(n):
            db.historial_agregar({
                "id": f"h{i}",
                "url": f"https://youtu.be/{i}",
                "titulo": f"Pista {i}",
                "canal": "Canal",
                "archivo": f"Pista {i}.mp3",
                "carpeta": "",
                "completado": f"2026-07-0{i + 1}T10:00:00+00:00",
            })

    def test_eliminar_una_entrada(self, client, entorno):
        self._sembrar(3)
        r = client.post("/api/historial/eliminar", json={"id": "h1"})
        assert r.status_code == 200
        ids = [h["id"] for h in client.get("/api/historial").get_json()["items"]]
        assert "h1" not in ids
        assert len(ids) == 2

    def test_eliminar_sin_id_devuelve_400(self, client, entorno):
        assert client.post("/api/historial/eliminar", json={}).status_code == 400

    def test_eliminar_inexistente_devuelve_404(self, client, entorno):
        assert client.post("/api/historial/eliminar", json={"id": "zzz"}).status_code == 404

    def test_limpiar_vacia_todo(self, client, entorno):
        self._sembrar(4)
        r = client.post("/api/historial/limpiar")
        assert r.status_code == 200
        assert r.get_json()["eliminados"] == 4
        assert client.get("/api/historial").get_json()["items"] == []


# --------------------------------------------------------------------------- #
# /api/biblioteca/eliminar
# --------------------------------------------------------------------------- #

class TestBibliotecaEliminar:
    def test_borra_el_archivo_del_disco(self, client, entorno):
        f = entorno / "cancion.mp3"
        f.write_bytes(b"ID3fake")
        r = client.post("/api/biblioteca/eliminar", json={"archivo": "cancion.mp3"})
        assert r.status_code == 200
        assert not f.exists()

    def test_borra_mp4(self, client, entorno):
        f = entorno / "clip.mp4"
        f.write_bytes(b"\x00\x00\x00\x18ftyp")
        respuesta = client.post("/api/biblioteca/eliminar", json={"archivo": "clip.mp4"})
        assert respuesta.status_code == 200
        assert not f.exists()

    def test_sin_archivo_devuelve_400(self, client, entorno):
        assert client.post("/api/biblioteca/eliminar", json={}).status_code == 400

    def test_inexistente_devuelve_404(self, client, entorno):
        respuesta = client.post("/api/biblioteca/eliminar", json={"archivo": "no.mp3"})
        assert respuesta.status_code == 404

    def test_traversal_no_borra_fuera(self, client, entorno, tmp_path):
        externo = tmp_path / "secreto.mp3"
        externo.write_bytes(b"ID3fake")
        # '../secreto.mp3' escapa de descargas → rechazado, el fichero sigue.
        r = client.post("/api/biblioteca/eliminar", json={"archivo": "../secreto.mp3"})
        assert r.status_code == 404
        assert externo.exists()

    def test_extension_no_permitida_devuelve_403(self, client, entorno):
        (entorno / "nota.txt").write_text("x", encoding="utf-8")
        respuesta = client.post("/api/biblioteca/eliminar", json={"archivo": "nota.txt"})
        assert respuesta.status_code == 403
