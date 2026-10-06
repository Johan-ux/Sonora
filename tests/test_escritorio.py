"""Tests del lanzador de escritorio (``sonora.escritorio``).

Solo lo que se puede probar sin abrir una ventana: el puente que lleva la
ventana a pantalla completa cuando la interfaz lo pide.
"""

from __future__ import annotations

from types import SimpleNamespace

from sonora.escritorio import crear_puente_pantalla_completa, esta_maximizada


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
