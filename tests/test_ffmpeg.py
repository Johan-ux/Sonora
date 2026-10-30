"""Tests de ``sonora.ffmpeg`` (dónde se busca ffmpeg)."""

from __future__ import annotations

import pytest

import sonora.ffmpeg as ffmpeg


@pytest.fixture()
def herramientas(tmp_path, monkeypatch):
    """Carpeta de programas incluidos en el ejecutable, vacía de entrada."""
    carpeta = tmp_path / "bin"
    carpeta.mkdir()
    monkeypatch.setattr(ffmpeg.paths, "DIR_HERRAMIENTAS", carpeta)
    return carpeta


@pytest.fixture()
def del_sistema(tmp_path, monkeypatch):
    """Un ffmpeg «instalado en el sistema» (en el PATH) y nada en winget."""
    carpeta = tmp_path / "sistema"
    carpeta.mkdir()
    (carpeta / "ffmpeg.exe").write_bytes(b"")
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda nombre: str(carpeta / "ffmpeg.exe"))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    return carpeta


def test_el_incluido_gana_al_del_sistema(herramientas, del_sistema):
    (herramientas / "ffmpeg.exe").write_bytes(b"")
    assert ffmpeg.localizar_ffmpeg() == herramientas


def test_sin_incluido_se_usa_el_del_sistema(herramientas, del_sistema):
    assert ffmpeg.localizar_ffmpeg() == del_sistema


def test_la_ruta_explicita_va_por_delante(herramientas, del_sistema, tmp_path):
    (herramientas / "ffmpeg.exe").write_bytes(b"")
    propia = tmp_path / "propia"
    propia.mkdir()
    (propia / "ffmpeg.exe").write_bytes(b"")
    assert ffmpeg.localizar_ffmpeg(propia) == propia
