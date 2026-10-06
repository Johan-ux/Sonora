"""Tests de ``sonora.salud`` (chequeo de entorno y actualización de yt-dlp)."""

from __future__ import annotations

import datetime
import subprocess

import pytest

from sonora import salud


@pytest.fixture(autouse=True)
def _sin_cache_pypi(monkeypatch):
    """Cada test arranca sin la caché de PyPI de los anteriores."""
    monkeypatch.setattr(salud, "_cache_pypi", None)


class TestCompararVersiones:
    @pytest.mark.parametrize(
        ("instalada", "ultima", "esperado"),
        [
            ("2026.08.19", "2026.09.02", True),
            ("2026.3.17", "2026.08.19", True),
            ("2026.08.19", "2026.08.19", False),
            ("2026.09.02", "2026.08.19", False),
            # PyPI publica '2026.8.19' y pip informa '2026.08.19': el mismo
            # número con distinto relleno no puede leerse como actualización.
            ("2026.08.19", "2026.8.19", False),
            # Las versiones de desarrollo llevan un cuarto componente.
            ("2026.08.19", "2026.08.19.232030", True),
        ],
    )
    def test_comparacion(self, instalada, ultima, esperado):
        assert salud.hay_version_nueva(instalada, ultima) is esperado

    @pytest.mark.parametrize("basura", ["", None, "raro", "v2026", "nightly"])
    def test_versiones_irreconocibles_no_avisan(self, basura):
        # Ante algo que no se sabe leer, callar: mejor eso que un aviso falso.
        assert salud.hay_version_nueva(basura, "2026.08.19") is False
        assert salud.hay_version_nueva("2026.08.19", basura) is False


class TestAntiguedad:
    def test_calcula_los_dias_desde_la_version(self):
        hace_diez = datetime.date.today() - datetime.timedelta(days=10)
        version = f"{hace_diez.year}.{hace_diez.month:02d}.{hace_diez.day:02d}"
        assert salud.dias_de_antiguedad(version) == 10

    def test_version_ilegible_devuelve_menos_uno(self):
        assert salud.dias_de_antiguedad("raro") == -1

    def test_fecha_imposible_no_revienta(self):
        # '2026.13.45' parsea como números pero no es una fecha real.
        assert salud.dias_de_antiguedad("2026.13.45") == -1


class _RespuestaPypi:
    """Respuesta mínima de urlopen con el JSON que publica PyPI."""

    def __init__(self, version):
        self._version = version

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        import json as _json

        return _json.dumps({"info": {"version": self._version}}).encode("utf-8")


class TestUltimaVersionPypi:
    def test_lee_la_version_del_json(self, monkeypatch):
        monkeypatch.setattr(
            salud.urllib.request, "urlopen",
            lambda p, timeout=None: _RespuestaPypi("2026.09.02"),
        )
        assert salud.ultima_version_pypi() == "2026.09.02"

    def test_una_respuesta_buena_se_cachea(self, monkeypatch):
        llamadas = []

        def contar(peticion, timeout=None):
            llamadas.append(1)
            return _RespuestaPypi("2026.09.02")

        monkeypatch.setattr(salud.urllib.request, "urlopen", contar)
        salud.ultima_version_pypi()
        salud.ultima_version_pypi()
        # La segunda sale de la caché: abrir la app no debe martillear PyPI.
        assert len(llamadas) == 1

    def test_forzar_salta_la_cache(self, monkeypatch):
        llamadas = []

        def contar(peticion, timeout=None):
            llamadas.append(1)
            return _RespuestaPypi("2026.09.02")

        monkeypatch.setattr(salud.urllib.request, "urlopen", contar)
        salud.ultima_version_pypi()
        # Tras actualizar hay que releer la versión sin esperar al TTL.
        salud.ultima_version_pypi(forzar=True)
        assert len(llamadas) == 2

    def test_un_fallo_no_se_cachea(self, monkeypatch):
        llamadas = []

        def falla(peticion, timeout=None):
            llamadas.append(1)
            raise OSError("sin red")

        monkeypatch.setattr(salud.urllib.request, "urlopen", falla)
        salud.ultima_version_pypi()
        # Un corte de red puntual no debe silenciar el aviso durante 6 horas.
        salud.ultima_version_pypi()
        assert len(llamadas) == 2

    def test_sin_red_devuelve_cadena_vacia(self, monkeypatch):
        def cae(peticion, timeout=None):
            raise OSError("sin red")

        monkeypatch.setattr(salud.urllib.request, "urlopen", cae)
        assert salud.ultima_version_pypi() == ""

    def test_respuesta_inesperada_no_revienta(self, monkeypatch):
        class RespuestaRara:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"esto no es json"

        monkeypatch.setattr(
            salud.urllib.request, "urlopen", lambda p, timeout=None: RespuestaRara()
        )
        assert salud.ultima_version_pypi() == ""


class TestEstado:
    def test_sin_red_no_inventa_actualizacion(self, monkeypatch):
        estado = salud.estado(consultar_red=False)
        assert estado["yt_dlp"]["ultima"] == ""
        assert estado["yt_dlp"]["hay_actualizacion"] is False

    def test_incluye_ffmpeg_y_runtime(self, monkeypatch):
        estado = salud.estado(consultar_red=False)
        assert "disponible" in estado["ffmpeg"]
        assert "disponible" in estado["runtime_js"]

    def test_empaquetada_marca_no_actualizable(self, monkeypatch):
        # Dentro del .exe, yt-dlp va congelado: pip no puede actualizarlo.
        monkeypatch.setattr(salud, "empaquetada", lambda: True)
        estado = salud.estado(consultar_red=False)
        assert estado["yt_dlp"]["actualizable"] is False
        assert estado["empaquetada"] is True


class TestActualizar:
    def test_empaquetada_no_ejecuta_pip(self, monkeypatch):
        monkeypatch.setattr(salud, "empaquetada", lambda: True)

        def no_debe_llamarse(*args, **kwargs):
            raise AssertionError("no se debe invocar a pip en la app empaquetada")

        monkeypatch.setattr(salud.subprocess, "run", no_debe_llamarse)
        resultado = salud.actualizar_yt_dlp()
        assert resultado["ok"] is False
        assert "reconstruir" in resultado["mensaje"]

    def test_exito_pide_reiniciar(self, monkeypatch):
        monkeypatch.setattr(salud, "empaquetada", lambda: False)
        monkeypatch.setattr(
            salud.subprocess, "run",
            lambda *a, **k: subprocess.CompletedProcess(a, 0, "instalado", ""),
        )
        monkeypatch.setattr(salud, "ultima_version_pypi", lambda forzar=False: "2026.09.02")
        resultado = salud.actualizar_yt_dlp()
        assert resultado["ok"] is True
        assert resultado["version"] == "2026.09.02"
        assert "Reinicia" in resultado["mensaje"]

    def test_pip_sin_shell_y_con_el_interprete_actual(self, monkeypatch):
        capturado = {}

        def espia(orden, **kwargs):
            capturado["orden"] = orden
            capturado["shell"] = kwargs.get("shell")
            return subprocess.CompletedProcess(orden, 0, "", "")

        monkeypatch.setattr(salud, "empaquetada", lambda: False)
        monkeypatch.setattr(salud.subprocess, "run", espia)
        monkeypatch.setattr(salud, "ultima_version_pypi", lambda forzar=False: "2026.09.02")
        salud.actualizar_yt_dlp()
        assert capturado["shell"] is False
        assert capturado["orden"][0] == salud.sys.executable
        assert capturado["orden"][1:] == ["-m", "pip", "install", "--upgrade", "yt-dlp"]

    def test_fallo_de_pip_se_reporta(self, monkeypatch):
        monkeypatch.setattr(salud, "empaquetada", lambda: False)
        monkeypatch.setattr(
            salud.subprocess, "run",
            lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "ERROR: no such package"),
        )
        resultado = salud.actualizar_yt_dlp()
        assert resultado["ok"] is False
        assert "no such package" in resultado["mensaje"]

    def test_timeout_se_reporta(self, monkeypatch):
        def caduca(*a, **k):
            raise subprocess.TimeoutExpired("pip", 1)

        monkeypatch.setattr(salud, "empaquetada", lambda: False)
        monkeypatch.setattr(salud.subprocess, "run", caduca)
        resultado = salud.actualizar_yt_dlp()
        assert resultado["ok"] is False
        assert "demasiado" in resultado["mensaje"]


class TestApiSalud:
    def test_get_devuelve_el_estado(self, client):
        respuesta = client.get("/api/salud?red=0")
        assert respuesta.status_code == 200
        datos = respuesta.get_json()
        assert "yt_dlp" in datos and "ffmpeg" in datos and "runtime_js" in datos

    def test_post_fallido_responde_409_con_error(self, client, monkeypatch):
        monkeypatch.setattr(salud, "empaquetada", lambda: True)
        respuesta = client.post("/api/salud/actualizar")
        assert respuesta.status_code == 409
        datos = respuesta.get_json()
        assert datos["ok"] is False
        # 'error' es la clave que lee el frontend al fallar una petición.
        assert datos["error"]

    def test_post_correcto_responde_200(self, client, monkeypatch):
        monkeypatch.setattr(
            salud, "actualizar_yt_dlp",
            lambda: {"ok": True, "mensaje": "listo", "version": "2026.09.02"},
        )
        respuesta = client.post("/api/salud/actualizar")
        assert respuesta.status_code == 200
        assert respuesta.get_json()["ok"] is True


class TestReinicioPendiente:
    """Tras actualizar yt-dlp con la app abierta, no se usa hasta reiniciar."""

    def _pip(self, monkeypatch, codigo):
        monkeypatch.setattr(salud, "empaquetada", lambda: False)
        monkeypatch.setattr(
            salud.subprocess, "run",
            lambda *a, **k: subprocess.CompletedProcess(a, codigo, "", "ERROR: algo"),
        )
        monkeypatch.setattr(salud, "ultima_version_pypi", lambda forzar=False: "2026.09.02")

    def test_de_entrada_no_hay_nada_pendiente(self):
        assert salud.reinicio_pendiente() is False
        assert salud.estado(consultar_red=False)["reinicio_pendiente"] is False

    def test_actualizar_con_exito_lo_deja_pendiente(self, monkeypatch):
        self._pip(monkeypatch, 0)
        assert salud.actualizar_yt_dlp()["ok"] is True
        assert salud.reinicio_pendiente() is True
        assert salud.estado(consultar_red=False)["reinicio_pendiente"] is True

    def test_si_pip_falla_no_hay_nada_que_reiniciar(self, monkeypatch):
        self._pip(monkeypatch, 1)
        assert salud.actualizar_yt_dlp()["ok"] is False
        assert salud.reinicio_pendiente() is False


class TestConsultaRecordada:
    """La consulta a PyPI se puede traer de una sesión anterior."""

    def _sin_red(self, monkeypatch):
        def no_debe_llamarse(*args, **kwargs):
            raise AssertionError("no debía consultarse PyPI")

        monkeypatch.setattr(salud.urllib.request, "urlopen", no_debe_llamarse)

    def test_una_reciente_evita_la_red(self, monkeypatch):
        import time

        self._sin_red(monkeypatch)
        salud.recordar_pypi(time.time() - 60, "2026.09.02")
        assert salud.ultima_version_pypi() == "2026.09.02"

    @pytest.mark.parametrize("desfase", [-(salud.TTL_CACHE + 60), 3600.0])
    def test_una_caducada_o_del_futuro_no_vale(self, monkeypatch, desfase):
        import time

        salud.recordar_pypi(time.time() + desfase, "2026.01.01")
        monkeypatch.setattr(
            salud.urllib.request, "urlopen",
            lambda p, timeout=None: _RespuestaPypi("2026.09.02"),
        )
        assert salud.ultima_version_pypi() == "2026.09.02"

    def test_sin_version_no_se_recuerda_nada(self):
        salud.recordar_pypi(1.0, "")
        assert salud.cache_pypi() is None


class TestApiSaludEntreSesiones:
    def test_la_consulta_se_guarda_y_se_recupera_al_volver_a_abrir(self, client, monkeypatch):
        from sonora import db

        monkeypatch.setattr(
            salud.urllib.request, "urlopen",
            lambda p, timeout=None: _RespuestaPypi("2026.09.02"),
        )
        assert client.get("/api/salud").get_json()["yt_dlp"]["ultima"] == "2026.09.02"
        assert db.config_obtener("salud_pypi").endswith("|2026.09.02")

        # Otra sesión: la memoria empieza vacía y PyPI no contesta.
        monkeypatch.setattr(salud, "_cache_pypi", None)

        def sin_red(*args, **kwargs):
            raise OSError("sin red")

        monkeypatch.setattr(salud.urllib.request, "urlopen", sin_red)
        assert client.get("/api/salud").get_json()["yt_dlp"]["ultima"] == "2026.09.02"

    def test_no_se_actualiza_con_descargas_en_marcha(self, client, monkeypatch):
        from sonora.servicios import descargas

        def no_debe_llamarse():
            raise AssertionError("pip no debía ejecutarse")

        monkeypatch.setattr(descargas, "hay_tanda_en_marcha", lambda: True)
        monkeypatch.setattr(salud, "actualizar_yt_dlp", no_debe_llamarse)
        respuesta = client.post("/api/salud/actualizar")
        assert respuesta.status_code == 409
        assert "descargas en marcha" in respuesta.get_json()["error"]

    def test_tras_actualizar_se_cierra_el_paso_a_yt_dlp(self, client, monkeypatch):
        monkeypatch.setattr(salud, "_reinicio_pendiente", True)
        for ruta in ("/api/buscar", "/api/cola/descargar", "/api/cola/reintentar"):
            respuesta = client.post(ruta, json={"q": "algo", "todos": True})
            assert respuesta.status_code == 409, ruta
            assert "reinicia" in respuesta.get_json()["error"].lower()
        assert client.get("/api/previa/dQw4w9WgXcQ").status_code == 409
        # Lo que no toca yt-dlp sigue funcionando: ver la cola, añadir, la biblioteca…
        assert client.get("/api/cola").status_code == 200
        assert client.post("/api/cola/agregar", json={"url": "https://x/1"}).status_code == 200
        assert client.get("/api/biblioteca").status_code == 200
