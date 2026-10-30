"""Tests del lanzador de escritorio (``sonora.escritorio``).

Solo lo que se puede probar sin abrir una ventana ni el navegador: el puente
que lleva la ventana a pantalla completa cuando la interfaz lo pide, el icono,
la instancia única y cuándo se usa el navegador en lugar de la ventana.
"""

from __future__ import annotations

import importlib.util
import os
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from sonora import escritorio
from sonora.escritorio import (
    RUTA_ICONO,
    crear_puente_pantalla_completa,
    esperar_servidor,
    esta_maximizada,
    tomar_cerrojo_de_instancia,
)
from sonora.paths import RUTA_RECURSOS

RAIZ = Path(__file__).resolve().parent.parent


class VentanaFalsa:
    """Doble de la ventana de pywebview: apunta lo que se le pide, en orden.

    Imita lo que hace la de verdad en Windows: al salir de pantalla completa
    vuelve siempre a tamaño normal, estuviera como estuviera antes.
    """

    def __init__(self, estado=None):
        self.alternancias = 0
        self.completa = False
        self.ordenes = []
        # Sin estado no hay ventana nativa, como en una plataforma que no es Windows.
        self.native = None if estado is None else SimpleNamespace(WindowState=estado)

    def _fijar(self, estado):
        if self.native is not None:
            self.native.WindowState = estado

    def toggle_fullscreen(self):
        self.alternancias += 1
        self.completa = not self.completa
        self.ordenes.append("alternar")
        if not self.completa:
            self._fijar("Normal")

    def restore(self):
        self.ordenes.append("restaurar")
        self._fijar("Normal")

    def maximize(self):
        self.ordenes.append("maximizar")
        self._fijar("Maximized")


class TestPuentePantallaCompleta:
    def test_se_expone_con_el_nombre_que_usa_la_interfaz(self):
        # pywebview publica la función en JS con su __name__.
        puente = crear_puente_pantalla_completa(VentanaFalsa())
        assert puente.__name__ == "pantalla_completa"

    def test_entrar_y_salir_alternan_la_ventana(self):
        ventana = VentanaFalsa()
        puente = crear_puente_pantalla_completa(ventana)
        assert puente(True) is True
        assert ventana.alternancias == 1
        assert puente(False) is False
        assert ventana.alternancias == 2

    def test_avisos_repetidos_no_desparejan_la_ventana(self):
        # toggle_fullscreen solo sabe alternar: dos «entrar» seguidos no
        # pueden dejar la ventana fuera de pantalla completa.
        ventana = VentanaFalsa()
        puente = crear_puente_pantalla_completa(ventana)
        puente(True)
        puente(True)
        assert ventana.alternancias == 1
        puente(False)
        puente(False)
        assert ventana.alternancias == 2

    def test_salir_sin_haber_entrado_no_hace_nada(self):
        ventana = VentanaFalsa()
        crear_puente_pantalla_completa(ventana)(False)
        assert ventana.alternancias == 0


class TestVentanaMaximizada:
    def test_una_ventana_maximizada_vuelve_maximizada(self):
        ventana = VentanaFalsa("Maximized")
        puente = crear_puente_pantalla_completa(ventana)
        puente(True)
        puente(False)
        assert ventana.native.WindowState == "Maximized"
        # Se restaura ANTES de entrar: pywebview recuerda el tamaño que tiene la
        # ventana en ese momento, y tiene que ser el normal, no el maximizado.
        assert ventana.ordenes == ["restaurar", "alternar", "alternar", "maximizar"]

    def test_una_ventana_normal_no_se_maximiza_al_volver(self):
        ventana = VentanaFalsa("Normal")
        puente = crear_puente_pantalla_completa(ventana)
        puente(True)
        puente(False)
        assert ventana.ordenes == ["alternar", "alternar"]

    def test_cada_entrada_mira_como_esta_la_ventana_en_ese_momento(self):
        ventana = VentanaFalsa("Maximized")
        puente = crear_puente_pantalla_completa(ventana)
        puente(True)
        puente(False)
        # El usuario la deja en tamaño normal y vuelve a entrar.
        ventana.restore()
        ventana.ordenes.clear()
        puente(True)
        puente(False)
        assert ventana.ordenes == ["alternar", "alternar"]

    def test_esta_maximizada_lee_el_estado_de_la_ventana_nativa(self):
        assert esta_maximizada(VentanaFalsa("Maximized")) is True
        assert esta_maximizada(VentanaFalsa("Normal")) is False

    def test_sin_ventana_nativa_no_se_da_por_maximizada(self):
        # Fuera de Windows pywebview no expone el estado: no hay nada que reponer.
        assert esta_maximizada(VentanaFalsa()) is False
        assert esta_maximizada(object()) is False


@pytest.fixture(scope="module")
def generador():
    """El guion que dibuja el icono (vive en scripts/, fuera del paquete)."""
    spec = importlib.util.spec_from_file_location(
        "generar_icono", RAIZ / "scripts" / "generar_icono.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _imagenes_del_ico(datos: bytes) -> dict[int, bytes]:
    """Las imágenes que trae un .ico, por su lado en píxeles."""
    reservado, tipo, cuantas = struct.unpack_from("<HHH", datos)
    assert (reservado, tipo) == (0, 1), "no es un .ico"
    imagenes = {}
    for i in range(cuantas):
        lado, _, _, _, _, _, largo, posicion = struct.unpack_from("<BBBBHHII", datos, 6 + 16 * i)
        imagenes[lado or 256] = datos[posicion:posicion + largo]
    return imagenes


class TestIcono:
    def test_trae_los_tamanos_que_pide_windows(self):
        # 16-24 en la barra de título, 32-48 en la de tareas, 256 en el Explorador.
        imagenes = _imagenes_del_ico(RUTA_ICONO.read_bytes())
        assert {16, 20, 24, 32, 40, 48, 256} <= set(imagenes)

    def test_es_el_que_dibuja_el_guion(self, generador):
        # Cambiar el dibujo sin volver a generar el fichero dejaría la ventana
        # con el icono viejo. El de 256 va comprimido y no se compara byte a byte.
        imagenes = _imagenes_del_ico(RUTA_ICONO.read_bytes())
        for lado in (16, 32, 48):
            esperada = generador._como_mapa_de_bits(generador.dibujar(lado))
            assert imagenes[lado] == esperada, f"icono de {lado} px desfasado"

    def test_lleva_los_colores_del_tema_por_defecto(self, generador):
        # El icono es fijo: los de «ocaso», los mismos que el favicon de la página.
        css = (RUTA_RECURSOS / "static" / "css" / "estilo.css").read_text(encoding="utf-8")
        html = (RUTA_RECURSOS / "templates" / "index.html").read_text(encoding="utf-8")
        for nombre, color in (("a", generador.OCASO_A), ("b", generador.OCASO_B)):
            hexadecimal = "{:02x}{:02x}{:02x}".format(*color)
            assert f"--ocaso-{nombre}: #{hexadecimal};" in css
            assert f'stop-color="%23{hexadecimal}"' in html

    def test_las_esquinas_son_transparentes_y_el_centro_no(self, generador):
        filas = generador.dibujar(32)
        assert filas[0][0][3] == 0
        assert filas[16][16][3] == 255


class TestInstanciaUnica:
    """Dos Sonoras sobre la misma carpeta de datos se pisan la cola."""

    def test_la_segunda_no_consigue_el_cerrojo(self, tmp_path):
        primera = tomar_cerrojo_de_instancia(tmp_path)
        try:
            assert primera is not None
            assert tomar_cerrojo_de_instancia(tmp_path) is None
        finally:
            primera.close()

    def test_al_cerrarse_la_primera_queda_libre(self, tmp_path):
        tomar_cerrojo_de_instancia(tmp_path).close()
        segunda = tomar_cerrojo_de_instancia(tmp_path)
        assert segunda is not None
        segunda.close()

    def test_carpetas_de_datos_distintas_no_se_estorban(self, tmp_path):
        una = tomar_cerrojo_de_instancia(tmp_path / "a")
        otra = tomar_cerrojo_de_instancia(tmp_path / "b")
        try:
            # De paso: la carpeta se crea si no existía.
            assert una is not None and otra is not None
        finally:
            una.close()
            otra.close()


class TestEsperarServidor:
    def test_no_pasa_por_el_proxy_del_sistema(self, monkeypatch):
        import http.server
        import threading

        class Responde(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args):
                pass

        servidor = http.server.HTTPServer(("127.0.0.1", 0), Responde)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        try:
            # Un proxy que no existe: si el sondeo lo usara, nunca llegaría.
            for variable in ("HTTP_PROXY", "http_proxy"):
                monkeypatch.setenv(variable, "http://127.0.0.1:9")
            for variable in ("NO_PROXY", "no_proxy"):
                monkeypatch.delenv(variable, raising=False)
            url = f"http://127.0.0.1:{servidor.server_address[1]}/"
            assert esperar_servidor(url, intentos=3, espera=0.01) is True
        finally:
            servidor.shutdown()
            servidor.server_close()

    def test_sin_servidor_se_rinde(self):
        # El puerto 9 (discard) no lo escucha nadie.
        assert esperar_servidor("http://127.0.0.1:9/", intentos=2, espera=0.01) is False


# --------------------------------------------------------------------------- #
# Ventana propia o navegador
# --------------------------------------------------------------------------- #


class EventoFalso:
    """Los eventos de pywebview se suscriben con +=."""

    def __init__(self):
        self.funciones = []

    def __iadd__(self, funcion):
        self.funciones.append(funcion)
        return self

    def disparar(self):
        for funcion in self.funciones:
            funcion()


class WebviewFalso:
    """Doble del módulo webview: ``al_arrancar`` decide qué pasa en start()."""

    def __init__(self, al_arrancar):
        self.al_arrancar = al_arrancar
        self.ventana = None

    def create_window(self, *args, **kwargs):
        self.ventana = SimpleNamespace(
            expose=lambda *funciones: None, events=SimpleNamespace(shown=EventoFalso())
        )
        return self.ventana

    def start(self, **kwargs):
        self.al_arrancar(self.ventana)


class TestAbrirVentana:
    def test_sin_motor_de_ventana_se_usa_el_navegador(self):
        def sin_motor(ventana):
            # Lo que lanza pywebview en Linux sin Qt ni GTK.
            raise RuntimeError("You must have either QT or GTK with Python extensions installed")

        assert escritorio.abrir_ventana(WebviewFalso(sin_motor), "http://127.0.0.1:1") is False

    def test_una_ventana_que_se_abre_y_se_cierra_termina_la_app(self):
        webview = WebviewFalso(lambda ventana: ventana.events.shown.disparar())
        assert escritorio.abrir_ventana(webview, "http://127.0.0.1:1") is True

    def test_un_fallo_con_la_ventana_abierta_no_se_esconde(self):
        def falla_despues(ventana):
            ventana.events.shown.disparar()
            raise RuntimeError("fallo de verdad")

        with pytest.raises(RuntimeError, match="fallo de verdad"):
            escritorio.abrir_ventana(WebviewFalso(falla_despues), "http://127.0.0.1:1")

    def test_si_start_vuelve_sin_haberla_mostrado_se_usa_el_navegador(self):
        assert escritorio.abrir_ventana(WebviewFalso(lambda v: None), "http://127.0.0.1:1") is False


def _contador(cuentas):
    """Devuelve las pestañas de ``cuentas`` una a una y después cero; cuenta las llamadas."""
    llamadas = []

    def contar():
        llamadas.append(None)
        indice = len(llamadas) - 1
        return cuentas[indice] if indice < len(cuentas) else 0

    return contar, llamadas


class TestEsperarPestanas:
    def test_da_tiempo_a_que_se_abra_la_primera(self):
        contar, llamadas = _contador([0] * 30 + [1])
        escritorio.esperar_a_que_cierren_las_pestanas(gracia=0, sondeo=0, contar=contar)
        assert len(llamadas) > 30

    def test_si_no_se_abre_ninguna_acaba_rindiendose(self):
        # Sin esto, el .exe sin ventana ni consola quedaría vivo para siempre.
        contar, llamadas = _contador([])
        escritorio.esperar_a_que_cierren_las_pestanas(
            sondeo=0.01, contar=contar, espera_inicial=0.05
        )
        assert llamadas

    def test_se_cierra_al_cerrar_la_ultima(self):
        contar, llamadas = _contador([1, 2, 1])
        escritorio.esperar_a_que_cierren_las_pestanas(gracia=0, sondeo=0, contar=contar)
        assert len(llamadas) >= 4

    def test_una_recarga_no_la_cierra(self):
        # Un instante sin pestañas (la recarga) es más corto que la gracia.
        contar, llamadas = _contador([1, 0, 1, 1, 1])
        escritorio.esperar_a_que_cierren_las_pestanas(gracia=0.05, sondeo=0.01, contar=contar)
        assert len(llamadas) > 5


class TestAbrirEnNavegador:
    def test_vigila_las_pestanas_aunque_el_navegador_no_vuelva(self, monkeypatch, capsys):
        # webbrowser.open() puede no volver hasta que se cierra el navegador
        # (con la variable BROWSER): no puede tener parada la vigilancia.
        import threading

        suelta = threading.Event()
        abiertas, vigiladas = [], []

        def abrir_y_quedarse(url):
            abiertas.append(url)
            suelta.wait(5)
            return True

        monkeypatch.setattr(escritorio.webbrowser, "open", abrir_y_quedarse)
        monkeypatch.setattr(
            escritorio, "esperar_a_que_cierren_las_pestanas", lambda: vigiladas.append(None)
        )
        try:
            assert escritorio.abrir_en_navegador("http://127.0.0.1:5099") == 0
            assert vigiladas
        finally:
            suelta.set()
        assert abiertas == ["http://127.0.0.1:5099"]
        # La dirección sale en la terminal, por si el navegador no se abre solo.
        assert "http://127.0.0.1:5099" in capsys.readouterr().out

    def test_sin_navegador_avisa_con_la_direccion(self, monkeypatch):
        avisos = []
        monkeypatch.setattr(escritorio.webbrowser, "open", lambda url: False)
        monkeypatch.setattr(escritorio, "reportar_error", avisos.append)
        escritorio.abrir_pestana("http://127.0.0.1:5099")
        assert "http://127.0.0.1:5099" in avisos[0]

    def test_ctrl_c_la_cierra_sin_error(self, monkeypatch):
        def interrumpir():
            raise KeyboardInterrupt

        monkeypatch.setattr(escritorio.webbrowser, "open", lambda url: True)
        monkeypatch.setattr(escritorio, "esperar_a_que_cierren_las_pestanas", interrumpir)
        assert escritorio.abrir_en_navegador("http://127.0.0.1:5099") == 0


class TestInstanciaAnotada:
    def test_anota_su_proceso_y_su_direccion(self, tmp_path):
        escritorio.anotar_instancia(tmp_path, "http://127.0.0.1:5099")
        assert escritorio.leer_instancia(tmp_path) == {
            "pid": os.getpid(),
            "url": "http://127.0.0.1:5099",
        }

    def test_sin_direccion_borra_la_de_una_sesion_anterior(self, tmp_path):
        escritorio.anotar_instancia(tmp_path, "http://127.0.0.1:5099")
        escritorio.anotar_instancia(tmp_path, "")
        assert escritorio.leer_instancia(tmp_path) is None

    @pytest.mark.parametrize(
        "contenido",
        [
            '{"pid": 1, "url": "https://web-mala.example"}',
            '{"pid": 1, "url": "http://127.0.0.1:5099/../x"}',
            '{"pid": "1", "url": "http://127.0.0.1:5099"}',
            '{"url": "http://127.0.0.1:5099"}',
            "http://127.0.0.1:5099",
        ],
    )
    def test_lo_que_no_es_fiable_no_vale(self, tmp_path, contenido):
        (tmp_path / escritorio.NOMBRE_INSTANCIA).write_text(contenido, encoding="utf-8")
        assert escritorio.leer_instancia(tmp_path) is None

    def test_sin_fichero_no_hay_instancia(self, tmp_path):
        assert escritorio.leer_instancia(tmp_path) is None


class TestVolverALaQueYaEsta:
    @pytest.fixture()
    def anotada(self, tmp_path, monkeypatch):
        abiertas, buscadas = [], []
        monkeypatch.setattr(escritorio.webbrowser, "open", lambda url: abiertas.append(url) or True)
        escritorio.anotar_instancia(tmp_path, "http://127.0.0.1:5099")
        return tmp_path, abiertas, buscadas

    def test_con_ventana_la_trae_al_frente(self, anotada, monkeypatch):
        carpeta, abiertas, buscadas = anotada
        monkeypatch.setattr(
            escritorio, "mostrar_ventana_existente", lambda pid: buscadas.append(pid) or True
        )
        assert escritorio.volver_a_la_que_ya_esta(carpeta) is True
        # Busca la ventana de ESE proceso, y no abre ninguna pestaña.
        assert buscadas == [os.getpid()]
        assert abiertas == []

    def test_en_modo_navegador_abre_otra_pestana(self, anotada, monkeypatch):
        carpeta, abiertas, _ = anotada
        monkeypatch.setattr(escritorio, "mostrar_ventana_existente", lambda pid: False)
        assert escritorio.volver_a_la_que_ya_esta(carpeta) is True
        assert abiertas == ["http://127.0.0.1:5099"]

    def test_sin_instancia_anotada_no_hace_nada(self, tmp_path, monkeypatch):
        monkeypatch.setattr(escritorio.webbrowser, "open", lambda url: pytest.fail(url))
        assert escritorio.volver_a_la_que_ya_esta(tmp_path) is False

    def test_no_confunde_otra_ventana_que_se_llame_igual(self):
        # Regresión: se buscaba cualquier ventana titulada «Sonora», y valían
        # el Explorador en la carpeta del zip o IntelliJ con el proyecto. Este
        # proceso no tiene ventanas: aunque haya otras con ese título, no.
        assert escritorio.mostrar_ventana_existente(os.getpid()) is False


class TestModoDeArranque:
    """main() elige entre la ventana y el navegador; el resto va con dobles."""

    @pytest.fixture()
    def arranque(self, tmp_path, monkeypatch):
        modos = []
        resultado = {"ventana": True}

        def abrir_ventana(webview, url):
            modos.append("ventana")
            return resultado["ventana"]

        monkeypatch.setattr(escritorio.paths, "DIR_BASE", tmp_path)
        monkeypatch.setattr(escritorio, "crear_app", lambda: object())
        monkeypatch.setattr(escritorio, "arrancar_servidor", lambda app, puerto: None)
        monkeypatch.setattr(escritorio, "esperar_servidor", lambda url: True)
        monkeypatch.setattr(escritorio, "identificar_app", lambda: None)
        monkeypatch.setattr(escritorio, "abrir_ventana", abrir_ventana)
        monkeypatch.setattr(
            escritorio, "abrir_en_navegador", lambda url: modos.append("navegador") or 0
        )
        yield modos, resultado
        # main() guarda el cerrojo en un global: se suelta para el siguiente test.
        if escritorio._cerrojo_de_instancia is not None:
            escritorio._cerrojo_de_instancia.close()
            escritorio._cerrojo_de_instancia = None

    def test_por_defecto_abre_la_ventana(self, arranque):
        modos, _ = arranque
        assert escritorio.main([]) == 0
        assert modos == ["ventana"]

    def test_si_la_ventana_no_se_abre_usa_el_navegador(self, arranque):
        modos, resultado = arranque
        resultado["ventana"] = False
        assert escritorio.main([]) == 0
        assert modos == ["ventana", "navegador"]

    def test_con_navegador_ni_lo_intenta_con_la_ventana(self, arranque):
        modos, _ = arranque
        assert escritorio.main(["--navegador"]) == 0
        assert modos == ["navegador"]

    def test_deja_anotada_su_instancia(self, arranque, tmp_path):
        escritorio.main(["--navegador"])
        instancia = escritorio.leer_instancia(tmp_path)
        assert instancia["pid"] == os.getpid()
        assert instancia["url"].startswith("http://127.0.0.1:")

    @pytest.mark.parametrize(("vuelve", "avisa"), [(True, False), (False, True)])
    def test_si_ya_esta_abierta_vuelve_a_ella(
        self, arranque, tmp_path, monkeypatch, vuelve, avisa
    ):
        modos, _ = arranque
        avisos = []
        otra = tomar_cerrojo_de_instancia(tmp_path)  # la instancia que ya está abierta
        try:
            monkeypatch.setattr(escritorio, "volver_a_la_que_ya_esta", lambda carpeta: vuelve)
            monkeypatch.setattr(escritorio, "reportar_error", avisos.append)
            monkeypatch.setattr(escritorio, "crear_app", lambda: pytest.fail("no debía arrancar"))
            assert escritorio.main([]) == 0
        finally:
            otra.close()
        assert modos == []
        assert avisos == (["Sonora ya está abierta."] if avisa else [])
