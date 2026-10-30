"""Tests de ``sonora.paths``: anti path-traversal y rutas relativas."""

from __future__ import annotations

import os

import pytest

import sonora.paths as paths
from sonora.paths import rel_descargas, resolver_dentro_descargas


@pytest.fixture()
def base(tmp_path, monkeypatch):
    """CARPETA_DESCARGAS apuntando a un directorio temporal real."""
    descargas = tmp_path / "descargas"
    descargas.mkdir()
    monkeypatch.setattr(paths, "CARPETA_DESCARGAS", descargas)
    return descargas.resolve()


def test_cadena_vacia_devuelve_base(base):
    assert resolver_dentro_descargas("") == base


def test_none_equivale_a_base(base):
    # La función tolera None ('rel or ""').
    assert resolver_dentro_descargas(None) == base


def test_subcarpeta_valida(base):
    assert resolver_dentro_descargas("rock/clasicos") == base / "rock" / "clasicos"


def test_traversal_directo_devuelve_none(base):
    assert resolver_dentro_descargas("../fuera") is None


def test_traversal_indirecto_devuelve_none(base):
    # 'a/../../fuera' resuelve a <base>/../fuera: fuera de la base.
    assert resolver_dentro_descargas("a/../../fuera") is None


def test_barras_invertidas_se_normalizan(base):
    # '\' se trata igual que '/'.
    assert resolver_dentro_descargas("sub\\anidada") == base / "sub" / "anidada"
    assert resolver_dentro_descargas("..\\fuera") is None


def test_ruta_absoluta_inyectada(base):
    """Una ruta absoluta inyectada nunca debe escapar de la base.

    En Windows, 'C:\\...' es absoluta: pathlib descarta la base al concatenar
    y el resultado queda fuera -> None. En POSIX la función neutraliza el
    prefijo '/' con strip('/') (la ruta pasa a ser relativa BAJO la base), así
    que allí comprobamos la garantía real: el resultado jamás sale de la base.
    """
    if os.name == "nt":
        assert resolver_dentro_descargas("C:\\Windows\\System32") is None
        assert resolver_dentro_descargas("C:/Windows/System32") is None
    else:
        resultado = resolver_dentro_descargas("/etc/passwd")
        assert resultado is None or base in resultado.parents


def test_carpeta_hermana_con_el_mismo_prefijo(base, tmp_path):
    # 'descargas-otra' empieza como 'descargas', pero está fuera.
    (tmp_path / "descargas-otra").mkdir()
    assert resolver_dentro_descargas("../descargas-otra") is None
    assert resolver_dentro_descargas("../descargas-otra/cancion.mp3") is None


def test_enlace_que_sale_de_la_base(base, tmp_path):
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    try:
        (base / "enlace").symlink_to(fuera, target_is_directory=True)
    except OSError:
        pytest.skip("este sistema no deja crear enlaces simbólicos")
    assert resolver_dentro_descargas("enlace") is None
    assert resolver_dentro_descargas("enlace/cancion.mp3") is None


def test_byte_nulo_devuelve_none(base):
    assert resolver_dentro_descargas("a\x00b") is None


def test_rel_descargas_dentro_y_fuera(base, tmp_path):
    dentro = base / "sub" / "cancion.mp3"
    dentro.parent.mkdir(parents=True)
    dentro.write_bytes(b"")
    assert rel_descargas(dentro) == "sub/cancion.mp3"

    fuera = tmp_path / "fuera.mp3"
    fuera.write_bytes(b"")
    assert rel_descargas(fuera) == ""
