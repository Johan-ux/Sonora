"""Tests del lanzador de escritorio (``sonora.escritorio``).

Solo lo que se puede probar sin abrir una ventana: el puente que lleva la
ventana a pantalla completa cuando la interfaz lo pide, y el icono.
"""

from __future__ import annotations

import importlib.util
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

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
