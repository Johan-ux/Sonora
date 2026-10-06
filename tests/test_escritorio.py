"""Tests del lanzador de escritorio (``sonora.escritorio``).

Solo lo que se puede probar sin abrir una ventana: el puente que lleva la
ventana a pantalla completa cuando la interfaz lo pide.
"""

from __future__ import annotations

from sonora.escritorio import crear_puente_pantalla_completa


class VentanaFalsa:
    """Doble de la ventana de pywebview: solo cuenta las alternancias."""

    def __init__(self):
        self.alternancias = 0

    def toggle_fullscreen(self):
        self.alternancias += 1


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
