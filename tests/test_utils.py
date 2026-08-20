"""Tests de ``sonora.utils``."""

from __future__ import annotations

from sonora.utils import colapsar_error, formatear_duracion, thumbnail_desde_id


class TestFormatearDuracion:
    def test_none(self):
        assert formatear_duracion(None) == ""

    def test_negativo(self):
        assert formatear_duracion(-5) == ""

    def test_59_segundos(self):
        assert formatear_duracion(59) == "0:59"

    def test_61_segundos(self):
        assert formatear_duracion(61) == "1:01"

    def test_con_horas(self):
        assert formatear_duracion(3661) == "1:01:01"

    def test_no_numerico(self):
        assert formatear_duracion("abc") == ""

    def test_numerico_como_texto(self):
        # La función acepta números en forma de cadena ('float(segundos)').
        assert formatear_duracion("61") == "1:01"


class TestColapsarError:
    def test_colapsa_saltos_de_linea(self):
        assert colapsar_error("linea 1\nlinea 2\r\n  linea   3") == "linea 1 linea 2 linea 3"

    def test_trunca_a_500(self):
        mensaje = "x" * 1000
        resultado = colapsar_error(mensaje)
        assert len(resultado) == 500
        assert resultado == "x" * 500

    def test_no_str(self):
        # Tolera cualquier tipo (usa str() internamente).
        assert colapsar_error(ValueError("boom")) == "boom"


class TestThumbnailDesdeId:
    def test_id_valido(self):
        assert thumbnail_desde_id("dQw4w9WgXcQ") == (
            "https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg"
        )

    def test_id_vacio(self):
        assert thumbnail_desde_id("") == ""
