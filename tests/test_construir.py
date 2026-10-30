"""Tests de ``scripts/construir.py`` (lo que no necesita construir el .exe)."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

_RUTA = Path(__file__).resolve().parent.parent / "scripts" / "construir.py"
_spec = importlib.util.spec_from_file_location("construir", _RUTA)
construir = importlib.util.module_from_spec(_spec)
# @dataclass busca su módulo en sys.modules mientras se ejecuta el script.
sys.modules[_spec.name] = construir
_spec.loader.exec_module(construir)


def test_huella_con_el_formato_de_sha256sum(tmp_path):
    archivo = tmp_path / "Sonora-windows-x64.zip"
    archivo.write_bytes(b"contenido del zip")

    huella = construir.escribir_huella(archivo)

    assert huella.name == "Sonora-windows-x64.zip.sha256"
    esperada = hashlib.sha256(b"contenido del zip").hexdigest()
    # Bytes, no texto: un '\r' antes del salto rompe 'sha256sum -c'.
    assert huella.read_bytes() == f"{esperada}  Sonora-windows-x64.zip\n".encode()
