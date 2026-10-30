"""Tests de la API HTTP con el test client de Flask.

La red nunca se toca: el servicio ``sonora.servicios.youtube`` se monkeypatchea
en los tests de búsqueda, y el worker de descargas queda desactivado por el
autouse fixture ``sin_worker`` (no se llama a /api/cola/descargar y
``arrancar_worker`` es un no-op). Los endpoints de cola emiten SSE
(``sonora.sse.emitir``), que sin clientes conectados es inofensivo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import sonora.servicios.descargas as descargas
import sonora.servicios.youtube as youtube
from sonora import db
from sonora.api.config import TEMAS
from sonora.paths import RUTA_RECURSOS


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

    def test_los_filtros_llegan_al_servicio(self, client, monkeypatch):
        llamadas = {}

        def falso_buscar(q, n, filtros=None):
            llamadas["filtros"] = filtros
            return []

        monkeypatch.setattr(youtube, "buscar", falso_buscar)
        filtros = {"orden": "recientes", "fecha": "mes", "caracteristicas": ["4k"]}
        respuesta = client.post("/api/buscar", json={"q": "beatles", "filtros": filtros})
        assert respuesta.status_code == 200
        assert llamadas["filtros"] == filtros


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

    def test_orden_de_busqueda_se_recuerda(self, client):
        assert client.get("/api/config").get_json()["busqueda_orden"] == "relevancia"
        client.post("/api/config", json={"busqueda_orden": "recientes"})
        assert client.get("/api/config").get_json()["busqueda_orden"] == "recientes"
        client.post("/api/config", json={"busqueda_orden": "al azar"})
        assert client.get("/api/config").get_json()["busqueda_orden"] == "relevancia"

    def test_tema_por_defecto_y_cambio(self, client):
        assert client.get("/api/config").get_json()["tema"] == "ocaso"
        client.post("/api/config", json={"tema": "buganvilla"})
        assert client.get("/api/config").get_json()["tema"] == "buganvilla"

    @pytest.mark.parametrize("tema", ["fucsia", "", None, 3, ["luna"]])
    def test_tema_invalido_cae_al_de_fabrica(self, client, tema):
        client.post("/api/config", json={"tema": "luna"})
        client.post("/api/config", json={"tema": tema})
        assert client.get("/api/config").get_json()["tema"] == "ocaso"

    @pytest.mark.parametrize("tema", TEMAS)
    def test_cada_tema_tiene_su_degradado_y_su_muestra(self, tema):
        # Un tema que el backend acepta pero la interfaz no define dejaría la
        # app con el acento de fábrica sin avisar.
        css = (RUTA_RECURSOS / "static" / "css" / "estilo.css").read_text(encoding="utf-8")
        html = (RUTA_RECURSOS / "templates" / "index.html").read_text(encoding="utf-8")
        for sufijo in ("-a", "-b", ""):
            assert f"--{tema}{sufijo}: #" in css
        assert f'.tema[data-tema="{tema}"]' in css
        assert f'name="tema" autocomplete="off" value="{tema}"' in html
        if tema != TEMAS[0]:
            assert f':root[data-tema="{tema}"]' in css

    def test_la_pagina_abre_ya_con_el_tema_guardado(self, client):
        # El tema va en el HTML: aplicarlo desde JS haría parpadear la ventana.
        assert b'<html lang="es" data-tema="ocaso">' in client.get("/").data
        client.post("/api/config", json={"tema": "cobre"})
        assert b'<html lang="es" data-tema="cobre">' in client.get("/").data

    def test_la_configuracion_dice_la_version(self, client):
        from sonora import __version__

        html = client.get("/").get_data(as_text=True)
        assert f"Sonora {__version__} ·" in html[html.index('id="vista-configuracion"'):]

    def test_el_selector_de_tema_vive_en_la_vista_de_configuracion(self):
        html = (RUTA_RECURSOS / "templates" / "index.html").read_text(encoding="utf-8")
        assert 'id="temas"' not in html[: html.index("</aside>")]
        assert html.index('id="vista-configuracion"') < html.index('id="temas"')

    def test_cada_destino_de_la_navegacion_tiene_su_vista(self):
        # cambiarVista() esconde todas las vistas menos «vista-<destino>»: un
        # destino sin la suya dejaría la zona principal vacía.
        html = (RUTA_RECURSOS / "templates" / "index.html").read_text(encoding="utf-8")
        destinos = re.findall(r'class="nav-item" data-vista="([a-z]+)"', html)
        assert "configuracion" in destinos
        for destino in destinos:
            assert f'id="vista-{destino}"' in html

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

    def test_crear_con_byte_nulo_devuelve_400(self, client):
        # Antes llegaba a mkdir, que lanza ValueError: un 500 sin capturar.
        respuesta = client.post("/api/carpetas/crear", json={"nombre": "a\x00b"})
        assert respuesta.status_code == 400

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


class TestAbrirCarpeta:
    """El explorador no se abre de verdad: ``carpetas_abiertas`` (conftest)."""

    def test_sin_archivo_abre_la_carpeta_de_descargas(self, client, entorno, carpetas_abiertas):
        assert client.post("/api/abrir-carpeta", json={}).status_code == 200
        assert carpetas_abiertas == [entorno]

    def test_con_archivo_abre_la_carpeta_que_lo_contiene(
        self, client, entorno, carpetas_abiertas
    ):
        (entorno / "rock").mkdir()
        (entorno / "rock" / "tema.mp3").write_bytes(b"ID3fake")
        respuesta = client.post("/api/abrir-carpeta", json={"archivo": "rock/tema.mp3"})
        assert respuesta.status_code == 200
        assert carpetas_abiertas == [(entorno / "rock").resolve()]

    def test_no_abre_nada_fuera_de_descargas(self, client, entorno, carpetas_abiertas):
        respuesta = client.post("/api/abrir-carpeta", json={"archivo": "../fuera.mp3"})
        assert respuesta.status_code == 403
        assert carpetas_abiertas == []


# --------------------------------------------------------------------------- #
# Altas con una tanda en marcha, reintentos y URLs de vídeo dentro de una lista
# --------------------------------------------------------------------------- #

class TestAnadirConTandaEnMarcha:
    """Cada alta repone la plantilla de workers (ver descargas.reponer_workers)."""

    @pytest.fixture()
    def reposiciones(self, monkeypatch):
        llamadas = []
        monkeypatch.setattr(descargas, "reponer_workers", lambda: llamadas.append(1))
        return llamadas

    def test_agregar_un_item(self, client, reposiciones):
        client.post("/api/cola/agregar", json={"url": "https://x/1"})
        assert reposiciones == [1]

    def test_un_duplicado_no_cuenta(self, client, reposiciones):
        client.post("/api/cola/agregar", json={"url": "https://x/1"})
        client.post("/api/cola/agregar", json={"url": "https://x/1"})
        assert reposiciones == [1]

    def test_agregar_una_playlist(self, client, reposiciones):
        client.post(
            "/api/cola/agregar_playlist",
            json={"items": [{"url": f"https://x/{i}"} for i in range(4)]},
        )
        assert reposiciones == [1]


class TestPlaylistDeUnaVez:
    def test_no_lee_la_configuracion_por_cada_cancion(self, client, monkeypatch):
        lecturas = []
        real = db.config_obtener

        def contar(clave, por_defecto=""):
            lecturas.append(clave)
            return real(clave, por_defecto)

        monkeypatch.setattr(db, "config_obtener", contar)
        respuesta = client.post(
            "/api/cola/agregar_playlist",
            json={"items": [{"url": f"https://x/{i}"} for i in range(60)]},
        )
        assert respuesta.get_json()["total"] == 60
        # Bitrate, formato y resolución: una vez por petición, no por canción.
        assert len(lecturas) <= 3

    def test_los_valores_de_la_peticion_llegan_a_cada_item(self, client):
        client.post(
            "/api/cola/agregar_playlist",
            json={
                "items": [{"url": "https://x/1"}, {"url": "https://x/2", "formato": "audio"}],
                "formato": "video",
                "resolucion": "720",
            },
        )
        cola = client.get("/api/cola").get_json()["items"]
        assert [(i["formato"], i["resolucion"]) for i in cola] == [
            ("video", "720"),
            ("audio", "720"),  # el ítem manda sobre el valor común
        ]


class TestReintentarLoQueYaEstaEnLaCola:
    def test_explica_por_que_no_se_reintenta(self, client):
        client.post("/api/cola/agregar", json={"url": "https://x/1"})
        viejo = client.get("/api/cola").get_json()["items"][0]["id"]
        db.cola_actualizar_estado(viejo, "error", "boom")
        client.post("/api/cola/agregar", json={"url": "https://x/1"})

        respuesta = client.post("/api/cola/reintentar", json={"id": viejo})

        assert respuesta.status_code == 409
        assert "ya está" in respuesta.get_json()["error"]
        estados = sorted(i["estado"] for i in client.get("/api/cola").get_json()["items"])
        assert estados == ["en_cola", "error"]


class TestBuscarVideoDentroDeUnaLista:
    URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=WL&index=2"
    VIDEO = {"id": "dQw4w9WgXcQ", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
             "titulo": "El vídeo", "tipo": "video"}

    @pytest.fixture(autouse=True)
    def _video(self, monkeypatch):
        monkeypatch.setattr(youtube, "info_video", lambda url: dict(self.VIDEO))

    def test_si_la_lista_no_se_puede_abrir_se_muestra_el_video(self, client, monkeypatch):
        def privada(url):
            raise RuntimeError("YouTube no devolvió datos")

        monkeypatch.setattr(youtube, "expandir_playlist", privada)
        datos = client.post("/api/buscar", json={"q": self.URL}).get_json()
        assert datos["es_playlist"] is False
        assert datos["resultados"] == [self.VIDEO]

    def test_si_la_lista_viene_vacia_tambien(self, client, monkeypatch):
        monkeypatch.setattr(youtube, "expandir_playlist", lambda url: ("Ver más tarde", [], 0))
        datos = client.post("/api/buscar", json={"q": self.URL}).get_json()
        assert datos["resultados"] == [self.VIDEO]

    def test_si_la_lista_se_abre_gana_la_lista(self, client, monkeypatch):
        temas = [{"id": "a", "url": "https://x/a", "tipo": "video"}]
        monkeypatch.setattr(youtube, "expandir_playlist", lambda url: ("Mi lista", temas, 1))
        datos = client.post("/api/buscar", json={"q": self.URL}).get_json()
        assert datos["es_playlist"] is True
        assert datos["resultados"] == temas

    def test_una_lista_sin_video_al_que_caer_sigue_fallando(self, client, monkeypatch):
        def privada(url):
            raise RuntimeError("YouTube no devolvió datos")

        monkeypatch.setattr(youtube, "expandir_playlist", privada)
        respuesta = client.post(
            "/api/buscar", json={"q": "https://www.youtube.com/playlist?list=PLprivada"}
        )
        assert respuesta.status_code == 502


class TestBuscarPestanaDeListasDeUnCanal:
    def test_son_colecciones_que_abrir_no_canciones_en_lotes(self, client, monkeypatch):
        listas = [
            {"id": "", "url": "https://www.youtube.com/playlist?list=PL1", "tipo": "lista"},
            {"id": "", "url": "https://www.youtube.com/playlist?list=PL2", "tipo": "lista"},
        ]
        monkeypatch.setattr(youtube, "expandir_canal", lambda url: ("Canal", listas, 2))
        datos = client.post(
            "/api/buscar", json={"q": "https://www.youtube.com/@canal/playlists"}
        ).get_json()
        assert datos["es_playlist"] is False
        assert datos["resultados"] == listas

    def test_los_videos_de_un_canal_siguen_yendo_por_lotes(self, client, monkeypatch):
        videos = [{"id": "a", "url": "https://x/a", "tipo": "video"}]
        monkeypatch.setattr(youtube, "expandir_canal", lambda url: ("Canal", videos, 1))
        datos = client.post(
            "/api/buscar", json={"q": "https://www.youtube.com/@canal"}
        ).get_json()
        assert datos["es_playlist"] is True and datos["es_canal"] is True


class TestBuscarCanalConListasMezcladas:
    def test_por_lotes_solo_van_los_videos(self, client, monkeypatch):
        mezcla = [
            {"id": "a", "url": "https://x/a", "tipo": "video"},
            {"id": "", "url": "https://www.youtube.com/playlist?list=PL1", "tipo": "lista"},
        ]
        monkeypatch.setattr(youtube, "expandir_canal", lambda url: ("Canal", mezcla, 2))
        datos = client.post(
            "/api/buscar", json={"q": "https://www.youtube.com/@canal/featured"}
        ).get_json()
        # «Añadir todo» no debe encolar la lista como si fuera una canción.
        assert datos["es_playlist"] is True
        assert [r["tipo"] for r in datos["resultados"]] == ["video"]
        assert datos["obtenidas"] == 1


class TestBibliotecaEliminarEnUso:
    """El reproductor suelta la pista justo antes de pedir que se borre; el
    servidor puede tardar unas décimas en cerrar el fichero que servía."""

    @pytest.fixture()
    def pista(self, entorno, monkeypatch):
        from sonora.api import biblioteca as api_biblioteca

        monkeypatch.setattr(api_biblioteca.time, "sleep", lambda segundos: None)
        ruta = entorno / "tema.mp3"
        ruta.write_bytes(b"musica")
        return ruta

    def _unlink_ocupado(self, monkeypatch, veces):
        intentos = []
        real = Path.unlink

        def unlink(ruta, *args, **kwargs):
            intentos.append(ruta.name)
            if len(intentos) <= veces:
                raise PermissionError(13, "El archivo está siendo utilizado por otro proceso")
            return real(ruta, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", unlink)
        return intentos

    def test_insiste_hasta_que_windows_lo_suelta(self, client, pista, monkeypatch):
        intentos = self._unlink_ocupado(monkeypatch, veces=2)
        respuesta = client.post("/api/biblioteca/eliminar", json={"archivo": "tema.mp3"})
        assert respuesta.status_code == 200
        assert len(intentos) == 3
        assert not pista.exists()

    def test_si_no_lo_suelta_lo_dice(self, client, pista, monkeypatch):
        intentos = self._unlink_ocupado(monkeypatch, veces=99)
        respuesta = client.post("/api/biblioteca/eliminar", json={"archivo": "tema.mp3"})
        assert respuesta.status_code == 500
        assert "No se pudo eliminar" in respuesta.get_json()["error"]
        assert len(intentos) == 6  # insiste un momento, no para siempre
        assert pista.exists()
