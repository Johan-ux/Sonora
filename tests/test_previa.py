"""Tests del reproductor propio de la vista previa.

Ni se consulta YouTube ni se lanza ffmpeg: ``yt_dlp.YoutubeDL`` y
``subprocess.Popen`` se sustituyen por dobles.
"""

from __future__ import annotations

import io

import pytest

from sonora.api import previa as api_previa
from sonora.servicios import previa

ID = "CkiqKg2bd8M"


@pytest.fixture(autouse=True)
def _sin_recuerdos():
    """Cada test parte sin URLs recordadas de otro."""
    previa._recordados.clear()
    yield
    previa._recordados.clear()


@pytest.fixture()
def ydl_falso(monkeypatch):
    """Sustituye yt_dlp.YoutubeDL; ``registro['info']`` es lo que devuelve."""
    registro: dict = {
        "llamadas": 0,
        "info": {
            "duration": 8131,
            "requested_formats": [
                {"url": "https://v.example/video", "http_headers": {"User-Agent": "Agente/1"}},
                {"url": "https://v.example/audio"},
            ],
        },
    }

    class YoutubeDLFalso:
        def __init__(self, opciones):
            registro["opciones"] = opciones

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            registro["llamadas"] += 1
            registro["url"] = url
            return registro["info"]

    monkeypatch.setattr(previa.yt_dlp, "YoutubeDL", YoutubeDLFalso)
    return registro


class TestIdValido:
    @pytest.mark.parametrize("video_id", [ID, "aqz-KE-bpKQ", "_-_-_-_-_-_"])
    def test_ids_de_youtube(self, video_id):
        assert previa.es_id_valido(video_id) is True

    @pytest.mark.parametrize(
        "video_id",
        ["", "corto", ID + "x", "../../etc/pwd", "CkiqKg2bd8 ", "CkiqKg2bd8;", None, 12345678901],
    )
    def test_lo_demas_no(self, video_id):
        assert previa.es_id_valido(video_id) is False


class TestResolver:
    def test_devuelve_entradas_agente_y_duracion(self, ydl_falso):
        flujo = previa.resolver(ID)
        assert flujo == {
            "entradas": ["https://v.example/video", "https://v.example/audio"],
            "agente": "Agente/1",
            "duracion": 8131.0,
        }
        assert ydl_falso["url"] == f"https://www.youtube.com/watch?v={ID}"

    def test_recuerda_las_urls_para_no_repetir_la_consulta(self, ydl_falso):
        previa.resolver(ID)
        previa.resolver(ID)
        assert ydl_falso["llamadas"] == 1

    def test_un_solo_formato_con_audio_y_video(self, ydl_falso):
        ydl_falso["info"] = {"duration": 10, "url": "https://v.example/todo"}
        assert previa.resolver(ID)["entradas"] == ["https://v.example/todo"]

    def test_id_no_valido(self, ydl_falso):
        with pytest.raises(ValueError):
            previa.resolver("demasiado-largo-para-ser-un-id")
        assert ydl_falso["llamadas"] == 0

    def test_un_directo_en_curso_no_se_reproduce_aqui(self, ydl_falso):
        ydl_falso["info"] = {"is_live": True, "url": "https://v.example/directo"}
        with pytest.raises(RuntimeError, match="directo"):
            previa.resolver(ID)

    def test_sin_datos_de_youtube(self, ydl_falso):
        ydl_falso["info"] = None
        with pytest.raises(RuntimeError):
            previa.resolver(ID)


class TestOrdenFfmpeg:
    FLUJO = {"entradas": ["https://v/video", "https://v/audio"], "agente": "Agente/1"}

    def test_une_video_y_audio_sin_recodificar(self):
        orden = previa.orden_ffmpeg("ffmpeg", self.FLUJO, 0)
        assert orden[0] == "ffmpeg"
        assert orden.count("-i") == 2
        assert orden[orden.index("-c") + 1] == "copy"
        mapa = orden.index("-map")
        assert orden[mapa:mapa + 4] == ["-map", "0:v:0", "-map", "1:a:0"]
        # MP4 fragmentado a la salida estándar: reproducible mientras se escribe.
        assert "frag_keyframe+empty_moov+default_base_moof" in orden
        assert orden[-1] == "pipe:1"

    def test_desde_el_principio_no_salta(self):
        assert "-ss" not in previa.orden_ffmpeg("ffmpeg", self.FLUJO, 0)

    def test_el_salto_va_delante_de_cada_entrada(self):
        orden = previa.orden_ffmpeg("ffmpeg", self.FLUJO, 3600)
        # -ss ANTES de -i: salta por el índice en vez de bajarse lo anterior.
        for posicion in (i for i, parte in enumerate(orden) if parte == "-i"):
            assert orden[posicion - 2:posicion] == ["-ss", "3600.000"]

    def test_una_sola_entrada_no_necesita_map(self):
        orden = previa.orden_ffmpeg("ffmpeg", {"entradas": ["https://v/todo"], "agente": ""}, 0)
        assert "-map" not in orden
        assert "-user_agent" not in orden


class TestApi:
    def test_info_devuelve_la_duracion(self, client, ydl_falso):
        respuesta = client.get(f"/api/previa/{ID}")
        assert respuesta.status_code == 200
        assert respuesta.get_json() == {"duracion": 8131.0}

    def test_info_con_id_no_valido(self, client, ydl_falso):
        assert client.get("/api/previa/corto").status_code == 400
        assert ydl_falso["llamadas"] == 0

    def test_info_cuando_youtube_falla(self, client, ydl_falso):
        ydl_falso["info"] = None
        respuesta = client.get(f"/api/previa/{ID}")
        assert respuesta.status_code == 502
        assert "error" in respuesta.get_json()

    def test_el_flujo_envia_lo_que_escribe_ffmpeg_y_lo_mata_al_acabar(self, client, monkeypatch):
        class ProcesoFalso:
            def __init__(self):
                self.stdout = io.BufferedReader(io.BytesIO(b"ftypmoov" * 4))
                self.muerto = False

            def kill(self):
                self.muerto = True

            def wait(self):
                return 0

        proceso = ProcesoFalso()
        pedido = {}

        def abrir(video_id, inicio=0.0):
            pedido.update(id=video_id, inicio=inicio)
            return proceso

        monkeypatch.setattr(api_previa.previa, "abrir_flujo", abrir)
        respuesta = client.get(f"/previa/{ID}.mp4?t=90.5")
        assert respuesta.status_code == 200
        assert respuesta.mimetype == "video/mp4"
        assert respuesta.data == b"ftypmoov" * 4
        assert pedido == {"id": ID, "inicio": 90.5}
        assert proceso.muerto is True

    def test_el_flujo_tolera_un_inicio_ilegible(self, client, monkeypatch):
        pedido = {}

        def abrir(video_id, inicio=0.0):
            pedido["inicio"] = inicio
            raise RuntimeError("Falta ffmpeg")

        monkeypatch.setattr(api_previa.previa, "abrir_flujo", abrir)
        respuesta = client.get(f"/previa/{ID}.mp4?t=mucho")
        assert pedido["inicio"] == 0.0
        assert respuesta.status_code == 502

    def test_abrir_en_youtube_construye_la_url_en_el_servidor(self, client, monkeypatch):
        abiertas = []
        monkeypatch.setattr(api_previa.webbrowser, "open", abiertas.append)
        assert client.post("/api/abrir-youtube", json={"id": ID}).status_code == 200
        assert abiertas == [f"https://www.youtube.com/watch?v={ID}"]

    @pytest.mark.parametrize("cuerpo", [{}, {"id": "https://malo.example"}, {"id": "calc.exe"}])
    def test_abrir_en_youtube_no_abre_otra_cosa(self, client, monkeypatch, cuerpo):
        abiertas = []
        monkeypatch.setattr(api_previa.webbrowser, "open", abiertas.append)
        assert client.post("/api/abrir-youtube", json=cuerpo).status_code == 400
        assert abiertas == []
