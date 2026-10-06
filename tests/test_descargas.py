"""Tests del worker de descargas: reintentos automáticos y cancelación.

Nunca se descarga nada de verdad: se sustituye ``yt_dlp.YoutubeDL`` por un
doble que falla o funciona según convenga, y se acorta la espera entre
reintentos para que la suite no tarde.
"""

from __future__ import annotations

import pytest
from yt_dlp.utils import DownloadError

from sonora import db
from sonora.servicios import descargas


@pytest.fixture(autouse=True)
def _sin_esperas(monkeypatch):
    """Reintentos inmediatos: la espera real haría la suite lentísima."""
    monkeypatch.setattr(descargas, "ESPERA_REINTENTO", 0.0)


class _YoutubeDLFalso:
    """Doble de yt_dlp.YoutubeDL con guion de fallos programable.

    ``fallos`` son las excepciones a lanzar en las primeras llamadas; agotadas,
    devuelve ``info``. Cuenta los intentos para poder afirmarlos.
    """

    intentos = 0
    fallos: list = []
    info: dict = {}

    def __init__(self, opciones):
        self.opciones = opciones

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=True):
        type(self).intentos += 1
        if type(self).fallos:
            raise type(self).fallos.pop(0)
        return dict(type(self).info)

    @classmethod
    def programar(cls, fallos, info=None):
        cls.intentos = 0
        cls.fallos = list(fallos)
        cls.info = info if info is not None else {"title": "Prueba", "id": "abc123"}


@pytest.fixture()
def ydl_falso(monkeypatch):
    monkeypatch.setattr(descargas.yt_dlp, "YoutubeDL", _YoutubeDLFalso)
    return _YoutubeDLFalso


def _item(item_id="i1"):
    return {
        "id": item_id,
        "url": "https://www.youtube.com/watch?v=abc123",
        "titulo": "Prueba",
        "carpeta": "",
        "bitrate": "320",
        "formato": "audio",
        "resolucion": "1080",
    }


class TestClasificarErrores:
    @pytest.mark.parametrize(
        "mensaje",
        [
            "ERROR: Private video. Sign in if you've been granted access",
            "Video unavailable",
            "This video has been removed by the uploader",
            "Join this channel to get access to members-only content",
            "Sign in to confirm your age",
            "The uploader has not made this video available in your country",
            "No video formats found",
        ],
    )
    def test_permanentes(self, mensaje):
        assert descargas._es_error_permanente(mensaje) is True

    @pytest.mark.parametrize(
        "mensaje",
        [
            "unable to download video data: HTTP Error 403: Forbidden",
            "HTTP Error 500: Internal Server Error",
            "[Errno 11001] getaddrinfo failed",
            "The read operation timed out",
            "Connection reset by peer",
            "",
        ],
    )
    def test_transitorios(self, mensaje):
        # Ante la duda, reintentar: un fallo de red no debe quedar en error.
        assert descargas._es_error_permanente(mensaje) is False


class TestDirectos:
    """Un directo en curso se rechaza: yt-dlp lo grabaría hasta que acabase."""

    @pytest.mark.parametrize(
        "info",
        [
            {"is_live": True},
            {"live_status": "is_live"},
            {"live_status": "is_upcoming"},
        ],
    )
    def test_en_emision_o_por_empezar_se_rechaza(self, info):
        with pytest.raises(DownloadError) as error:
            descargas._rechazar_directos(info)
        # Debe ser un fallo definitivo: reintentarlo no cambiaría nada.
        assert descargas._es_error_permanente(str(error.value)) is True

    @pytest.mark.parametrize(
        "info",
        [
            {},
            {"is_live": False, "live_status": "not_live"},
            # Un directo ya terminado es un vídeo como cualquier otro.
            {"is_live": False, "live_status": "was_live"},
        ],
    )
    def test_lo_demas_pasa(self, info):
        assert descargas._rechazar_directos(info) is None

    def test_las_descargas_llevan_el_filtro(self, entorno):
        opciones = descargas._construir_opciones_descarga(
            "", "audio", "320", "1080", lambda d: None, lambda d: None
        )
        assert opciones["match_filter"] is descargas._rechazar_directos

    def test_el_que_aun_no_ha_empezado_no_se_reintenta(self):
        mensaje = "ERROR: [youtube] abc: This live event will begin in 3 hours."
        assert descargas._es_error_permanente(mensaje) is True


class TestReintentos:
    def test_un_fallo_pasajero_se_reintenta_y_acaba_bien(self, entorno, ydl_falso):
        db.cola_agregar(_item())
        db.cola_reclamar("i1")
        ydl_falso.programar([DownloadError("HTTP Error 500: Internal Server Error")])

        descargas._procesar_item(_item())

        assert ydl_falso.intentos == 2  # falló una vez, la segunda entró
        assert db.cola_listar()[0]["estado"] == "completado"

    def test_agota_los_intentos_y_marca_error(self, entorno, ydl_falso):
        db.cola_agregar(_item())
        db.cola_reclamar("i1")
        ydl_falso.programar([DownloadError("timed out")] * 5)

        descargas._procesar_item(_item())

        assert ydl_falso.intentos == descargas.MAX_INTENTOS
        assert db.cola_listar()[0]["estado"] == "error"

    def test_un_error_permanente_no_se_reintenta(self, entorno, ydl_falso):
        db.cola_agregar(_item())
        db.cola_reclamar("i1")
        ydl_falso.programar([DownloadError("ERROR: Private video")] * 5)

        descargas._procesar_item(_item())

        # Reintentar un vídeo privado solo haría esperar al resto de la cola.
        assert ydl_falso.intentos == 1
        assert db.cola_listar()[0]["estado"] == "error"

    def test_la_cancelacion_corta_los_reintentos(self, entorno, ydl_falso, monkeypatch):
        db.cola_agregar(_item())
        db.cola_reclamar("i1")
        ydl_falso.programar([DownloadError("timed out")] * 5)
        # El usuario cancela mientras el worker está entre intentos.
        monkeypatch.setattr(descargas, "_cancelacion_pedida", lambda item_id: True)

        descargas._procesar_item(_item())

        assert ydl_falso.intentos == 1
        fila = db.cola_listar()[0]
        assert fila["estado"] == "error"
        assert fila["error"] == descargas.MENSAJE_CANCELADA


class TestEsperaCancelable:
    def test_devuelve_el_control_al_cancelar(self, monkeypatch):
        monkeypatch.setattr(descargas, "_cancelacion_pedida", lambda item_id: True)
        with pytest.raises(descargas.DescargaCancelada):
            # Sin la comprobación intermedia, esto bloquearía 60 segundos.
            descargas._esperar_cancelable(60.0, "i1")

    def test_espera_completa_si_no_hay_cancelacion(self, monkeypatch):
        monkeypatch.setattr(descargas, "_cancelacion_pedida", lambda item_id: False)
        descargas._esperar_cancelable(0.05, "i1")  # no debe lanzar


class TestSimultaneas:
    @pytest.mark.parametrize(
        ("valor", "esperado"),
        [("1", 1), ("3", 3), ("5", 5), ("99", 5), ("0", 1), ("-2", 1),
         ("abc", 3), ("", 3), (None, 3)],
    )
    def test_normalizacion(self, valor, esperado):
        # Fuera de rango se acota; lo que no es número cae al valor por defecto.
        assert descargas.normalizar_simultaneas(valor) == esperado

    def test_sin_bd_devuelve_el_valor_por_defecto(self, monkeypatch):
        def revienta(*args, **kwargs):
            raise RuntimeError("db.py no está inicializado")

        monkeypatch.setattr(descargas.db, "config_obtener", revienta)
        # Quedarse sin workers por no poder leer una preferencia sería peor
        # que ignorarla.
        assert descargas.descargas_simultaneas() == descargas.SIMULTANEAS_POR_DEFECTO


class TestPoolDeWorkers:
    """El pool se mide por su efecto, no por contar hilos: se sustituye el
    procesado por uno instrumentado y se observa cuántos corren a la vez."""

    def _medir_pico(self, simultaneas, n_items, monkeypatch, entorno):
        import threading
        import time

        db.config_guardar("descargas_simultaneas", str(simultaneas))
        for i in range(n_items):
            db.cola_agregar({"id": f"p{i}", "url": f"https://x/{i}", "titulo": f"c{i}"})

        estado = {"activos": 0, "pico": 0}
        lock = threading.Lock()

        def procesar(item):
            with lock:
                estado["activos"] += 1
                estado["pico"] = max(estado["pico"], estado["activos"])
            time.sleep(0.05)
            db.cola_actualizar_estado(item["id"], "completado")
            with lock:
                estado["activos"] -= 1

        monkeypatch.setattr(descargas, "_procesar_item", procesar)
        descargas.arrancar_worker()

        limite = time.monotonic() + 15
        while any(x["estado"] != "completado" for x in db.cola_listar()):
            if time.monotonic() > limite:
                pytest.fail("la cola no se vació a tiempo")
            time.sleep(0.01)
        while descargas._HILOS:  # que no se cuelen en el test siguiente
            time.sleep(0.01)
        return estado["pico"]

    def test_uno_procesa_de_uno_en_uno(self, entorno, monkeypatch):
        assert self._medir_pico(1, 4, monkeypatch, entorno) == 1

    def test_tres_procesan_a_la_vez(self, entorno, monkeypatch):
        assert self._medir_pico(3, 9, monkeypatch, entorno) == 3

    def test_nunca_se_pasa_del_limite(self, entorno, monkeypatch):
        # Más ítems que workers no debe abrir workers de más.
        assert self._medir_pico(2, 12, monkeypatch, entorno) <= 2

    def test_arrancar_dos_veces_no_duplica_workers(self, entorno, monkeypatch):
        import time

        db.config_guardar("descargas_simultaneas", "2")
        monkeypatch.setattr(descargas, "_procesar_item", lambda item: time.sleep(0.05))
        db.cola_agregar({"id": "z1", "url": "https://x/1", "titulo": "c"})
        descargas.arrancar_worker()
        descargas.arrancar_worker()  # idempotente: se llama en cada alta
        assert len(descargas._HILOS) <= 2
        while descargas._HILOS:
            time.sleep(0.01)


class TestLimpiezaDeTemporales:
    """Barrido de los restos que deja una descarga interrumpida.

    Estos tests borran ficheros de verdad, así que la mitad de ellos comprueba
    lo contrario: que la música terminada NO se toca.
    """

    @pytest.mark.parametrize(
        "nombre",
        ["a.mp3.part", "a.mp4.part-Frag12", "a.mp3.ytdl", "a.temp"],
    )
    def test_reconoce_los_temporales(self, nombre):
        assert descargas._es_temporal(nombre) is True

    @pytest.mark.parametrize(
        "nombre",
        ["Cancion [abc123].mp3", "video.mp4", "portada.webp", "a.partitura.mp3"],
    )
    def test_no_confunde_un_fichero_terminado(self, nombre):
        assert descargas._es_temporal(nombre) is False

    def test_borra_los_restos_de_la_descarga(self, entorno):
        destino = entorno / "Cancion [abc123].mp3"
        restos = [
            entorno / "Cancion [abc123].mp3.part",
            entorno / "Cancion [abc123].mp3.ytdl",
            entorno / "Cancion [abc123].mp3.part-Frag3",
        ]
        for r in restos:
            r.write_bytes(b"a medias")

        borrados = descargas._limpiar_temporales({str(destino)})

        assert borrados == 3
        assert not any(r.exists() for r in restos)

    def test_no_toca_la_musica_terminada(self, entorno):
        cancion = entorno / "Cancion [abc123].mp3"
        cancion.write_bytes(b"musica de verdad")
        vecina = entorno / "Cancion [abc123].mp3.backup"
        vecina.write_bytes(b"tampoco es temporal")

        descargas._limpiar_temporales({str(cancion)})

        # Lo que no lleva sufijo de temporal se queda donde está.
        assert cancion.read_bytes() == b"musica de verdad"
        assert vecina.exists()

    def test_los_corchetes_del_nombre_no_rompen_la_busqueda(self, entorno):
        # La plantilla mete el id entre corchetes, que para glob son una clase
        # de caracteres: sin escaparlos, el patrón no encontraría nada.
        resto = entorno / "Tema [xY-9_z].mp3.part"
        resto.write_bytes(b"a medias")

        borrados = descargas._limpiar_temporales({str(entorno / "Tema [xY-9_z].mp3")})

        assert borrados == 1
        assert not resto.exists()

    def test_ignora_lo_que_esta_fuera_de_descargas(self, entorno, tmp_path):
        fuera = tmp_path / "ajeno.mp3.part"
        fuera.write_bytes(b"no es nuestro")

        borrados = descargas._limpiar_temporales({str(tmp_path / "ajeno.mp3")})

        # Aunque el nombre encaje, fuera de descargas/ no se toca nada.
        assert borrados == 0
        assert fuera.exists()

    def test_una_ruta_inexistente_no_revienta(self, entorno):
        assert descargas._limpiar_temporales({str(entorno / "no-existe.mp3")}) == 0

    def test_cancelar_dispara_el_barrido(self, entorno, ydl_falso, monkeypatch):
        llamadas = []
        monkeypatch.setattr(
            descargas, "_limpiar_temporales", lambda rutas: llamadas.append(set(rutas)) or 0
        )
        db.cola_agregar(_item())
        db.cola_reclamar("i1")
        ydl_falso.programar([DownloadError("cancelado")])
        monkeypatch.setattr(descargas, "_cancelacion_pedida", lambda item_id: True)

        descargas._procesar_item(_item())

        assert llamadas, "cancelar debe barrer los restos"
        assert db.cola_listar()[0]["error"] == descargas.MENSAJE_CANCELADA

    def test_un_error_definitivo_dispara_el_barrido(self, entorno, ydl_falso, monkeypatch):
        llamadas = []
        monkeypatch.setattr(
            descargas, "_limpiar_temporales", lambda rutas: llamadas.append(set(rutas)) or 0
        )
        db.cola_agregar(_item())
        db.cola_reclamar("i1")
        ydl_falso.programar([DownloadError("ERROR: Private video")])

        descargas._procesar_item(_item())

        assert llamadas, "un fallo definitivo no deja nada aprovechable que conservar"

    def test_una_descarga_correcta_no_barre_nada(self, entorno, ydl_falso, monkeypatch):
        llamadas = []
        monkeypatch.setattr(
            descargas, "_limpiar_temporales", lambda rutas: llamadas.append(set(rutas)) or 0
        )
        db.cola_agregar(_item())
        db.cola_reclamar("i1")
        ydl_falso.programar([])  # sin fallos

        descargas._procesar_item(_item())

        assert not llamadas, "tras un éxito no hay restos que barrer"
        assert db.cola_listar()[0]["estado"] == "completado"
