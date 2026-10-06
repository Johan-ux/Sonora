"""Tests del worker de descargas: reintentos automáticos y cancelación.

Nunca se descarga nada de verdad: se sustituye ``yt_dlp.YoutubeDL`` por un
doble que falla o funciona según convenga, y se acorta la espera entre
reintentos para que la suite no tarde.
"""

from __future__ import annotations

from pathlib import Path

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
            "", "audio", "320", "1080", lambda d: None, lambda d: None,
            descargas._carpeta_temporal("i1"),
        )
        assert opciones["match_filter"] is descargas._rechazar_directos

    def test_el_que_aun_no_ha_empezado_no_se_reintenta(self):
        mensaje = "ERROR: [youtube] abc: This live event will begin in 3 hours."
        assert descargas._es_error_permanente(mensaje) is True


class TestSinFfmpeg:
    @pytest.mark.parametrize(
        "mensaje",
        [
            "ERROR: Postprocessing: ffprobe and ffmpeg not found. Please install or provide "
            "the path using --ffmpeg-location",
            "ERROR: You have requested merging of multiple formats but ffmpeg is not installed",
        ],
    )
    def test_no_se_reintenta(self, mensaje):
        # Sin ffmpeg el tercer intento falla igual que el primero.
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

    def test_lo_anadido_con_la_tanda_en_marcha_no_baja_de_uno_en_uno(self, entorno, monkeypatch):
        # Con una sola canción en la cola, dos de los tres workers se van
        # nada más arrancar. Lo que se añada después tiene que reponerlos.
        import threading
        import time

        db.config_guardar("descargas_simultaneas", "3")
        db.cola_agregar({"id": "a0", "url": "https://x/0", "titulo": "c0"})
        estado = {"activos": 0, "pico": 0}
        lock = threading.Lock()
        soltar = threading.Event()

        def procesar(item):
            with lock:
                estado["activos"] += 1
                estado["pico"] = max(estado["pico"], estado["activos"])
            soltar.wait(10)
            db.cola_actualizar_estado(item["id"], "completado")
            with lock:
                estado["activos"] -= 1

        def vivos():
            with descargas._LOCK_WORKER:
                return sum(1 for hilo in descargas._HILOS if hilo.is_alive())

        def esperar(condicion, que):
            limite = time.monotonic() + 10
            while not condicion():
                if time.monotonic() > limite:
                    soltar.set()
                    pytest.fail(que)
                time.sleep(0.01)

        monkeypatch.setattr(descargas, "_procesar_item", procesar)
        descargas.arrancar_worker()
        esperar(lambda: estado["activos"] == 1 and vivos() == 1, "no quedó un único worker")

        for i in (1, 2, 3):
            db.cola_agregar({"id": f"a{i}", "url": f"https://x/{i}", "titulo": f"c{i}"})
        descargas.reponer_workers()
        esperar(lambda: estado["pico"] == 3, "los workers no se repusieron")

        soltar.set()
        esperar(lambda: vivos() == 0, "los workers no terminaron")
        assert estado["pico"] == 3

    def test_sin_tanda_en_marcha_anadir_no_arranca_nada(self, entorno, monkeypatch):
        # Las descargas las arranca el usuario: añadir a la cola no descarga.
        llamadas = []
        monkeypatch.setattr(descargas, "arrancar_worker", lambda: llamadas.append(1))
        db.cola_agregar({"id": "q1", "url": "https://x/1", "titulo": "c"})

        descargas.reponer_workers()

        assert llamadas == []
        assert descargas.hay_tanda_en_marcha() is False


class _DejaRestos(_YoutubeDLFalso):
    """Como el doble de siempre, pero deja en la carpeta de trabajo lo que
    dejaría yt-dlp a medias antes de fallar o de acabar."""

    def extract_info(self, url, download=True):
        temporal = Path(self.opciones["paths"]["temp"])
        temporal.mkdir(parents=True, exist_ok=True)
        for nombre in ("Prueba [abc123].f399.mp4", "Prueba [abc123].webm.part", "Prueba.webp"):
            (temporal / nombre).write_bytes(b"a medias")
        return super().extract_info(url, download)


@pytest.fixture()
def ydl_con_restos(monkeypatch):
    monkeypatch.setattr(descargas.yt_dlp, "YoutubeDL", _DejaRestos)
    return _DejaRestos


class TestCarpetaDeTrabajo:
    """yt-dlp baja y convierte fuera de la carpeta de música.

    Lo que hay a medias lleva extensiones de música de verdad ('.f399.mp4',
    '.temp.mp4'): dentro de descargas, la biblioteca lo listaría y un cancelado
    lo dejaría allí para siempre.
    """

    def test_queda_fuera_de_la_carpeta_de_musica(self, entorno):
        from sonora.paths import rel_descargas

        temporal = descargas._carpeta_temporal("i1")
        # rel_descargas devuelve '' para lo que no cuelga de descargas/.
        assert rel_descargas(temporal) == ""
        assert temporal.parent.parent == entorno.parent

    @pytest.mark.parametrize("formato", ["audio", "video"])
    def test_las_opciones_separan_destino_y_trabajo(self, entorno, formato):
        temporal = descargas._carpeta_temporal("i1")
        opciones = descargas._construir_opciones_descarga(
            "Rock", formato, "320", "1080", lambda d: None, lambda d: None, temporal
        )
        assert opciones["paths"] == {"home": str(entorno / "Rock"), "temp": str(temporal)}
        # Con una ruta absoluta en la plantilla, yt-dlp ignoraría 'paths'.
        assert not Path(opciones["outtmpl"]).is_absolute()
        assert Path(opciones["outtmpl"]).parent == Path(".")

    def test_cancelar_no_deja_nada_a_medias(self, entorno, ydl_con_restos, monkeypatch):
        db.cola_agregar(_item())
        db.cola_reclamar("i1")
        ydl_con_restos.programar([DownloadError("cancelado")])
        monkeypatch.setattr(descargas, "_cancelacion_pedida", lambda item_id: True)

        descargas._procesar_item(_item())

        assert not descargas._carpeta_temporal("i1").exists()
        assert db.cola_listar()[0]["error"] == descargas.MENSAJE_CANCELADA

    def test_un_error_definitivo_tampoco(self, entorno, ydl_con_restos):
        db.cola_agregar(_item())
        db.cola_reclamar("i1")
        ydl_con_restos.programar([DownloadError("ERROR: Private video")])

        descargas._procesar_item(_item())

        assert not descargas._carpeta_temporal("i1").exists()

    def test_una_descarga_correcta_recoge_su_carpeta(self, entorno, ydl_con_restos):
        db.cola_agregar(_item())
        db.cola_reclamar("i1")
        ydl_con_restos.programar([])  # sin fallos

        descargas._procesar_item(_item())

        assert not descargas._carpeta_temporal("i1").exists()
        assert db.cola_listar()[0]["estado"] == "completado"

    def test_la_musica_terminada_no_se_toca(self, entorno, ydl_con_restos, monkeypatch):
        cancion = entorno / "Cancion [abc123].mp3"
        cancion.write_bytes(b"musica de verdad")
        db.cola_agregar(_item())
        db.cola_reclamar("i1")
        ydl_con_restos.programar([DownloadError("cancelado")])
        monkeypatch.setattr(descargas, "_cancelacion_pedida", lambda item_id: True)

        descargas._procesar_item(_item())

        assert cancion.read_bytes() == b"musica de verdad"
        # Y en la carpeta de música no ha aparecido nada más.
        assert [p.name for p in entorno.iterdir()] == [cancion.name]


class TestTemporalesHuerfanos:
    """Barrido al arrancar de las carpetas de trabajo que ya no son de nadie."""

    def _carpeta_con_restos(self, item_id):
        carpeta = descargas._carpeta_temporal(item_id)
        carpeta.mkdir(parents=True)
        (carpeta / "Tema [abc].webm.part").write_bytes(b"a medias")
        return carpeta

    def test_borra_las_de_items_que_ya_no_estan_en_la_cola(self, entorno):
        huerfana = self._carpeta_con_restos("borrado")

        assert descargas.limpiar_temporales_huerfanos() == 1
        assert not huerfana.exists()

    def test_conserva_las_de_los_pendientes_para_reanudar(self, entorno):
        # Una descarga cortada por un cierre inesperado vuelve a la cola: con
        # su '.part' intacto continúa por donde iba.
        db.cola_agregar(_item("pendiente"))
        db.cola_agregar(_item("bajando") | {"url": "https://x/otra"})
        db.cola_reclamar("bajando")
        carpetas = [self._carpeta_con_restos("pendiente"), self._carpeta_con_restos("bajando")]

        assert descargas.limpiar_temporales_huerfanos() == 0
        assert all((c / "Tema [abc].webm.part").exists() for c in carpetas)

    def test_las_de_terminados_o_fallidos_si_se_borran(self, entorno):
        db.cola_agregar(_item("fallo"))
        db.cola_actualizar_estado("fallo", "error", "no pudo ser")
        carpeta = self._carpeta_con_restos("fallo")

        assert descargas.limpiar_temporales_huerfanos() == 1
        assert not carpeta.exists()

    def test_sin_carpeta_temporal_no_revienta(self, entorno):
        assert descargas.limpiar_temporales_huerfanos() == 0


class TestEventoDeUnItem:
    """Los cambios de una sola fila viajan solos, no con la cola entera."""

    @pytest.fixture()
    def eventos(self, monkeypatch):
        emitidos = []
        monkeypatch.setattr(descargas.sse, "emitir", emitidos.append)
        return emitidos

    def test_una_descarga_no_manda_la_cola_entera(self, entorno, ydl_falso, eventos):
        db.cola_agregar(_item())
        db.cola_reclamar("i1")
        ydl_falso.programar([])

        descargas._procesar_item(_item())

        assert "cola_actualizada" not in [e["tipo"] for e in eventos]
        de_item = [e["item"] for e in eventos if e["tipo"] == "item_actualizado"]
        assert [(i["id"], i["estado"]) for i in de_item] == [
            ("i1", "descargando"),
            ("i1", "completado"),
        ]

    def test_lleva_el_progreso_vivo(self, entorno, eventos, monkeypatch):
        db.cola_agregar(_item())
        monkeypatch.setitem(descargas.PROGRESO_ACTIVO, "i1", 42.5)
        descargas.emitir_item_actualizado("i1")
        assert eventos[0]["item"]["progreso"] == 42.5

    def test_si_el_item_ya_no_existe_se_manda_la_cola_para_resincronizar(self, entorno, eventos):
        descargas.emitir_item_actualizado("fantasma")
        assert [e["tipo"] for e in eventos] == ["cola_actualizada"]
