"""Tests del servicio de búsqueda (``sonora.servicios.youtube``).

La red nunca se toca: ``yt_dlp.YoutubeDL`` se sustituye por un doble que
recuerda qué se le pidió y devuelve entradas preparadas. Lo que sí se fija con
valores reales es el parámetro ``sp``: sus cadenas son las que YouTube aceptó
al comprobarlas contra el servicio, de modo que un cambio en la codificación
que las altere hace fallar estos tests.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from sonora.servicios import youtube


def _video(vid: str, timestamp: int | None = None, **extra) -> dict:
    return {
        "ie_key": "Youtube",
        "id": vid,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "title": f"Vídeo {vid}",
        "channel": "Canal",
        "duration": 200,
        "timestamp": timestamp,
        **extra,
    }


CANAL = {
    "ie_key": "YoutubeTab",
    "id": "UCabc",
    "url": "https://www.youtube.com/channel/UCabc",
    "title": "Artista",
    "channel": "Artista",
    "uploader_id": "@artista",
    "thumbnails": [{"url": "//yt3.ggpht.com/avatar=s88"}, {"url": "//yt3.ggpht.com/avatar=s176"}],
}

LISTA = {
    "ie_key": "YoutubeTab",
    "url": "https://www.youtube.com/playlist?list=PLabc",
    "title": "Álbum completo",
    "channel": "Quien la subió",
    "thumbnails": [{"url": "https://i.ytimg.com/vi/abc/hqdefault.jpg"}],
}


@pytest.fixture()
def ydl_falso(monkeypatch):
    """Sustituye yt_dlp.YoutubeDL; devuelve el registro de lo que se le pidió."""
    registro: dict = {"entradas": []}

    class YoutubeDLFalso:
        def __init__(self, opciones):
            registro["opciones"] = opciones

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            registro["url"] = url
            return {"entries": registro["entradas"]}

    monkeypatch.setattr(youtube.yt_dlp, "YoutubeDL", YoutubeDLFalso)
    return registro


class TestNormalizarFiltros:
    def test_sin_filtros_son_los_de_por_defecto(self):
        assert youtube.normalizar_filtros(None) == youtube.FILTROS_POR_DEFECTO
        assert youtube.normalizar_filtros("recientes") == youtube.FILTROS_POR_DEFECTO

    def test_lo_desconocido_cae_al_valor_por_defecto(self):
        filtros = youtube.normalizar_filtros({
            "orden": "aleatorio",
            "fecha": 7,
            "duracion": ["corta"],
            "tipo": None,
            "caracteristicas": "4k",
        })
        assert filtros == youtube.FILTROS_POR_DEFECTO

    def test_caracteristicas_sin_repetir_ni_inventadas(self):
        filtros = youtube.normalizar_filtros({"caracteristicas": ["hdr", "4k", "turbo", "4k"]})
        assert filtros["caracteristicas"] == ["4k", "hdr"]


class TestParametroSp:
    @pytest.mark.parametrize(
        ("filtros", "esperado"),
        [
            # Solo el tipo (lo que queda al elegir «Más recientes», que se
            # ordena aquí y no viaja en el parámetro).
            ({"orden": "recientes"}, "EgIQAQ=="),
            ({"tipo": "canal"}, "EgIQAg=="),
            ({"tipo": "lista"}, "EgIQAw=="),
            ({"orden": "popularidad"}, "CAMSAhAB"),
            ({"fecha": "hoy"}, "EgQIAhAB"),
            ({"duracion": "corta"}, "EgQQARgB"),
            ({"caracteristicas": ["4k"]}, "EgQQAXAB"),
            ({"caracteristicas": ["directo"]}, "EgQQAUAB"),
            # HDR es el campo 25: su etiqueta ya no cabe en un octeto.
            ({"caracteristicas": ["hdr"]}, "EgUQAcgBAQ=="),
            ({"fecha": "mes", "duracion": "corta"}, "EgYIBBABGAE="),
        ],
    )
    def test_cadenas_comprobadas_contra_youtube(self, filtros, esperado):
        assert youtube.parametro_sp(youtube.normalizar_filtros(filtros)) == esperado


class TestEstadoDirecto:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ({"live_status": "is_live"}, "en_vivo"),
            ({"is_live": True}, "en_vivo"),
            ({"live_status": "is_upcoming"}, "programado"),
            ({"live_status": "was_live"}, "terminado"),
            ({"live_status": "post_live"}, "terminado"),
            ({"live_status": "not_live"}, ""),
            ({}, ""),
        ],
    )
    def test_estado_de_emision(self, ydl_falso, entrada, esperado):
        ydl_falso["entradas"] = [_video("a", **entrada)]
        (resultado,) = youtube.buscar("x", 5)
        assert resultado["directo"] == esperado


class TestBuscar:
    def test_sin_filtros_usa_la_busqueda_de_siempre(self, ydl_falso):
        ydl_falso["entradas"] = [_video("a"), _video("b")]
        resultados = youtube.buscar("beatles", 5)
        assert ydl_falso["url"] == "ytsearch5:beatles"
        assert [r["id"] for r in resultados] == ["a", "b"]
        assert resultados[0]["tipo"] == "video"

    def test_sin_filtros_tambien_descarta_el_canal_colado(self, ydl_falso):
        ydl_falso["entradas"] = [_video("a"), CANAL, _video("b")]
        assert [r["id"] for r in youtube.buscar("beatles", 5)] == ["a", "b"]

    def test_con_filtros_usa_la_url_de_resultados_con_sp(self, ydl_falso):
        youtube.buscar("bad bunny", 12, {"fecha": "hoy"})
        partes = urlsplit(ydl_falso["url"])
        consulta = parse_qs(partes.query)
        assert partes.path == "/results"
        assert consulta == {"search_query": ["bad bunny"], "sp": ["EgQIAhAB"]}

    def test_pide_fecha_aproximada(self, ydl_falso):
        # Sin ella los resultados no traen fecha y no habría qué ordenar.
        youtube.buscar("x", 5, {"orden": "recientes"})
        assert ydl_falso["opciones"]["extractor_args"] == {
            "youtubetab": {"approximate_date": [""]}
        }

    def test_recientes_pide_de_mas_y_ordena_por_fecha(self, ydl_falso):
        ydl_falso["entradas"] = [
            _video("viejo", 100),
            _video("sin_fecha"),
            _video("nuevo", 300),
            _video("medio", 200),
        ]
        resultados = youtube.buscar("x", 3, {"orden": "recientes"})
        assert ydl_falso["opciones"]["playlistend"] == youtube.RESULTADOS_PARA_ORDENAR
        # Lo que no trae fecha va al final, y se recorta DESPUÉS de ordenar.
        assert [r["id"] for r in resultados] == ["nuevo", "medio", "viejo"]

    def test_popularidad_respeta_el_orden_de_youtube(self, ydl_falso):
        ydl_falso["entradas"] = [_video("a", 100), _video("b", 300)]
        resultados = youtube.buscar("x", 5, {"orden": "popularidad"})
        assert [r["id"] for r in resultados] == ["a", "b"]

    def test_descarta_lo_que_no_es_del_tipo_pedido(self, ydl_falso):
        # YouTube cuela el canal del artista entre los vídeos.
        ydl_falso["entradas"] = [CANAL, _video("a"), LISTA, _video("b")]
        resultados = youtube.buscar("x", 5, {"duracion": "corta"})
        assert [r["id"] for r in resultados] == ["a", "b"]

    def test_listas(self, ydl_falso):
        ydl_falso["entradas"] = [CANAL, LISTA]
        (lista,) = youtube.buscar("x", 5, {"tipo": "lista"})
        assert lista == {
            "id": "",
            "url": "https://www.youtube.com/playlist?list=PLabc",
            "titulo": "Álbum completo",
            "canal": "Quien la subió",
            "duracion": "",
            "thumbnail": "https://i.ytimg.com/vi/abc/hqdefault.jpg",
            "tipo": "lista",
            "timestamp": None,
        }

    def test_canales(self, ydl_falso):
        ydl_falso["entradas"] = [CANAL, _video("a")]
        (canal,) = youtube.buscar("x", 5, {"tipo": "canal"})
        assert canal["tipo"] == "canal"
        assert canal["titulo"] == "Artista"
        assert canal["canal"] == "@artista"
        # El avatar llega sin esquema; se usa el más grande.
        assert canal["thumbnail"] == "https://yt3.ggpht.com/avatar=s176"


class TestUrlDelResultado:
    def test_prefiere_la_pagina_del_video_a_la_del_stream(self):
        # Extracción completa con un único formato: 'url' es la dirección
        # firmada del fichero, que caduca a las horas.
        entrada = _video(
            "dQw4w9WgXcQ",
            url="https://rr3---sn-abc.googlevideo.com/videoplayback?expire=1790000000&sig=x",
            webpage_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        resultado = youtube._entrada_a_resultado(entrada)
        assert resultado["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_sin_pagina_usa_la_url_de_la_entrada(self):
        assert youtube._entrada_a_resultado(_video("abc"))["url"].endswith("watch?v=abc")


class TestClasificarUrls:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/playlist?list=PLabc",
            "https://music.youtube.com/playlist?list=OLAK5uy",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabc&index=3",
            "https://youtu.be/dQw4w9WgXcQ?list=PLabc",
        ],
    )
    def test_es_una_lista(self, url):
        assert youtube.es_url_playlist(url) is True
        assert youtube.es_url_canal(url) is False

    @pytest.mark.parametrize(
        "url",
        [
            # La pestaña de listas de un canal es una página de canal.
            "https://www.youtube.com/@canal/playlists",
            "https://www.youtube.com/channel/UCabc/playlists",
            "https://www.youtube.com/@canal",
        ],
    )
    def test_es_un_canal(self, url):
        assert youtube.es_url_playlist(url) is False
        assert youtube.es_url_canal(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            # Un parámetro que solo *acaba* en «list» no es el de la lista.
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&playlist=1",
            "dQw4w9WgXcQ",
            "",
        ],
    )
    def test_no_es_ni_lista_ni_canal(self, url):
        assert youtube.es_url_playlist(url) is False
        assert youtube.es_url_canal(url) is False

    @pytest.mark.parametrize(
        ("url", "esperado"),
        [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=WL", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ?list=PLabc", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/playlist?list=PLabc", ""),
            ("", ""),
        ],
    )
    def test_id_del_video_que_trae_la_url(self, url, esperado):
        assert youtube.id_video(url) == esperado


class TestExpandirPestanaDeListas:
    def test_las_listas_de_un_canal_no_salen_como_canciones(self, ydl_falso):
        ydl_falso["entradas"] = [LISTA, _video("abc")]
        _, items, _ = youtube.expandir_canal("https://www.youtube.com/@canal/playlists")
        assert ydl_falso["url"] == "https://www.youtube.com/@canal/playlists"
        assert [i["tipo"] for i in items] == ["lista", "video"]
        # La lista conserva su URL para poder abrirla; no lleva id de vídeo.
        assert items[0]["url"] == LISTA["url"] and items[0]["id"] == ""
