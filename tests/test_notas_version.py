"""Tests de ``scripts/notas_version.py`` (notas de la release desde el changelog)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from sonora import __version__

_RUTA = Path(__file__).resolve().parent.parent / "scripts" / "notas_version.py"
_spec = importlib.util.spec_from_file_location("notas_version", _RUTA)
notas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(notas)

CHANGELOG = """\
# Registro de cambios

## [Sin publicar]

## [1.1.0] - 2026-12-01

Un párrafo que el changelog
parte en dos líneas.

### Añadido

- Una función nueva que no cabe
  en una sola línea.
- Otra corta.

```text
el código
se queda como está
```

## [1.0.0] - 2026-10-30

- La primera.

[Sin publicar]: https://example.org/compare
[1.1.0]: https://example.org/1.1.0
"""


class TestSeccion:
    def test_va_hasta_la_siguiente_version(self):
        lineas = notas.seccion(CHANGELOG, "1.1.0")
        assert lineas[1] == "Un párrafo que el changelog"
        assert not any("La primera" in linea for linea in lineas)

    def test_la_ultima_no_arrastra_los_enlaces(self):
        lineas = notas.seccion(CHANGELOG, "1.0.0")
        assert [linea for linea in lineas if linea.strip()] == ["- La primera."]

    def test_sin_esa_version_no_hay_nada(self):
        assert notas.seccion(CHANGELOG, "9.9.9") == []


class TestUnir:
    @pytest.fixture()
    def resultado(self):
        return notas.unir(notas.seccion(CHANGELOG, "1.1.0")).splitlines()

    def test_une_parrafos_y_elementos_partidos(self, resultado):
        assert "Un párrafo que el changelog parte en dos líneas." in resultado
        assert "- Una función nueva que no cabe en una sola línea." in resultado

    def test_respeta_titulos_y_elementos_separados(self, resultado):
        assert "### Añadido" in resultado
        assert "- Otra corta." in resultado

    def test_no_toca_el_codigo(self, resultado):
        assert resultado[resultado.index("```text") + 1 :][:2] == [
            "el código",
            "se queda como está",
        ]

    def test_quita_las_lineas_vacias_de_los_extremos(self):
        assert notas.unir(["", "- Algo.", ""]) == "- Algo."


class TestMain:
    def test_la_version_actual_tiene_sus_notas(self, capsys):
        # Lo que comprueba la publicación: si falla, la release no sale.
        assert notas.main(["notas_version.py", __version__]) == 0
        salida = capsys.readouterr().out
        assert salida.strip()
        assert not any(linea.startswith("  ") for linea in salida.splitlines())

    def test_una_version_sin_seccion_falla(self, capsys):
        assert notas.main(["notas_version.py", "9.9.9"]) == 1
        assert "9.9.9" in capsys.readouterr().err
