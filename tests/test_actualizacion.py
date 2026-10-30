"""Tests de ``sonora.actualizacion`` (yt-dlp actualizable dentro del .exe)."""

from __future__ import annotations

import hashlib
import importlib
import io
import json
import sys
import zipfile

import pytest

from sonora import actualizacion, salud

VERSION_INCLUIDA = "2026.10.01"
URL_WHEEL = "https://files.pythonhosted.org/packages/ab/cd/yt_dlp-2026.10.26-py3-none-any.whl"


@pytest.fixture()
def carpeta(tmp_path, monkeypatch):
    """Datos del usuario en tmp_path; devuelve dónde van los wheels."""
    monkeypatch.setattr(actualizacion.paths, "DIR_BASE", tmp_path)
    return tmp_path / "yt-dlp"


@pytest.fixture()
def empaquetada(monkeypatch):
    monkeypatch.setattr(salud, "empaquetada", lambda: True)
    monkeypatch.setattr(actualizacion, "version_incluida", lambda: VERSION_INCLUIDA)
    # activar() toca sys.path: cada test lo deja como lo encontró.
    monkeypatch.setattr(sys, "path", list(sys.path))


def _wheel(miembros: dict[str, str]) -> bytes:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w") as zip_:
        for nombre, contenido in miembros.items():
            zip_.writestr(nombre, contenido)
    return memoria.getvalue()


def _guardar(carpeta, version: str, contenido: bytes = b"") -> object:
    carpeta.mkdir(exist_ok=True)
    ruta = carpeta / f"yt_dlp-{version}-py3-none-any.whl"
    ruta.write_bytes(contenido)
    return ruta


class TestVersionDe:
    @pytest.mark.parametrize(
        ("nombre", "esperada"),
        [
            ("yt_dlp-2026.10.26-py3-none-any.whl", "2026.10.26"),
            ("yt_dlp-2026.10.26.232030-py3-none-any.whl", "2026.10.26.232030"),
            ("yt_dlp-2026.10.26.tar.gz", ""),
            ("otro-2026.10.26-py3-none-any.whl", ""),
            ("yt_dlp-2026.10.26-cp314-win_amd64.whl", ""),
        ],
    )
    def test_solo_reconoce_el_wheel_universal(self, nombre, esperada, tmp_path):
        assert actualizacion.version_de(tmp_path / nombre) == esperada


class TestActivar:
    def test_en_desarrollo_no_hace_nada(self, carpeta, monkeypatch):
        monkeypatch.setattr(salud, "empaquetada", lambda: False)
        wheel = _guardar(carpeta, "2099.1.1")
        antes = list(sys.path)
        assert actualizacion.activar() == ""
        assert sys.path == antes
        assert wheel.exists()

    def test_sin_carpeta_no_hace_nada(self, carpeta, empaquetada):
        antes = list(sys.path)
        assert actualizacion.activar() == ""
        assert sys.path == antes

    def test_pone_delante_el_mas_nuevo_y_borra_el_resto(self, carpeta, empaquetada):
        viejo = _guardar(carpeta, "2026.10.20")
        nuevo = _guardar(carpeta, "2026.10.26")
        a_medias = carpeta / "yt_dlp-2026.10.27-py3-none-any.whl.part"
        a_medias.write_bytes(b"")
        assert actualizacion.activar() == "2026.10.26"
        assert sys.path[0] == str(nuevo)
        assert not viejo.exists()
        assert not a_medias.exists()

    def test_si_no_mejora_al_incluido_se_borra(self, carpeta, empaquetada):
        # Pasa al instalar un Sonora más nuevo que trae un yt-dlp más reciente.
        wheel = _guardar(carpeta, VERSION_INCLUIDA)
        antes = list(sys.path)
        assert actualizacion.activar() == ""
        assert sys.path == antes
        assert not wheel.exists()

    def test_sin_metadatos_se_usa_el_descargado(self, carpeta, empaquetada, monkeypatch):
        monkeypatch.setattr(actualizacion, "version_incluida", lambda: "")
        wheel = _guardar(carpeta, "2026.09.01")
        assert actualizacion.activar() == "2026.09.01"
        assert sys.path[0] == str(wheel)

    def test_python_importa_desde_el_wheel(self, carpeta, empaquetada):
        # Lo que de verdad importa: con el wheel en sys.path, el import lo coge
        # de ahí sin descomprimir nada (como hará 'import yt_dlp').
        contenido = _wheel({"sonora_prueba_wheel/__init__.py": "VALOR = 42\n"})
        _guardar(carpeta, "2099.1.1", contenido)
        actualizacion.activar()
        try:
            modulo = importlib.import_module("sonora_prueba_wheel")
            assert modulo.VALOR == 42
        finally:
            sys.modules.pop("sonora_prueba_wheel", None)


class _PyPIFalso:
    """urlopen falso: sirve el JSON de PyPI y el wheel."""

    def __init__(self, wheel: bytes, *, url=URL_WHEEL, sha256=None, version="2026.10.26"):
        self.wheel = wheel
        self.pedidas: list[str] = []
        self.json = {
            "info": {"version": version},
            "urls": [
                {"filename": "yt_dlp-2026.10.26.tar.gz", "url": "https://x/sdist",
                 "digests": {"sha256": "0" * 64}},
                {"filename": url.rsplit("/", 1)[-1], "url": url,
                 "digests": {"sha256": sha256 or hashlib.sha256(wheel).hexdigest()}},
            ],
        }

    def __call__(self, peticion, timeout=None):
        url = peticion.full_url
        self.pedidas.append(url)
        if url == salud.URL_PYPI:
            return io.BytesIO(json.dumps(self.json).encode("utf-8"))
        return io.BytesIO(self.wheel)


class TestDescargar:
    WHEEL = _wheel({"yt_dlp/__init__.py": "", "yt_dlp/version.py": ""})

    def _servir(self, monkeypatch, pypi):
        monkeypatch.setattr(actualizacion.urllib.request, "urlopen", pypi)
        return pypi

    def test_deja_el_wheel_listo_para_el_arranque(self, carpeta, monkeypatch):
        self._servir(monkeypatch, _PyPIFalso(self.WHEEL))
        assert actualizacion.descargar() == "2026.10.26"
        guardado = carpeta / "yt_dlp-2026.10.26-py3-none-any.whl"
        assert guardado.read_bytes() == self.WHEEL
        assert list(carpeta.iterdir()) == [guardado]

    def test_una_huella_distinta_no_deja_nada(self, carpeta, monkeypatch):
        self._servir(monkeypatch, _PyPIFalso(self.WHEEL, sha256="f" * 64))
        with pytest.raises(actualizacion.ErrorActualizacion, match="dañada"):
            actualizacion.descargar()
        assert list(carpeta.iterdir()) == []

    def test_un_zip_sin_yt_dlp_no_vale(self, carpeta, monkeypatch):
        self._servir(monkeypatch, _PyPIFalso(_wheel({"otra_cosa.py": ""})))
        with pytest.raises(actualizacion.ErrorActualizacion, match="no contiene"):
            actualizacion.descargar()
        assert list(carpeta.iterdir()) == []

    def test_solo_descarga_del_almacen_de_pypi(self, carpeta, monkeypatch):
        url = "https://otro.example/yt_dlp-2026.10.26-py3-none-any.whl"
        pypi = self._servir(monkeypatch, _PyPIFalso(self.WHEEL, url=url))
        with pytest.raises(actualizacion.ErrorActualizacion, match="inesperado"):
            actualizacion.descargar()
        assert pypi.pedidas == [salud.URL_PYPI]

    def test_el_wheel_tiene_que_ser_de_la_version_anunciada(self, carpeta, monkeypatch):
        self._servir(monkeypatch, _PyPIFalso(self.WHEEL, version="2026.10.27"))
        with pytest.raises(actualizacion.ErrorActualizacion, match="versión anunciada"):
            actualizacion.descargar()

    def test_sin_red_se_explica(self, carpeta, monkeypatch):
        def sin_red(*args, **kwargs):
            raise OSError("sin red")

        monkeypatch.setattr(actualizacion.urllib.request, "urlopen", sin_red)
        with pytest.raises(actualizacion.ErrorActualizacion, match="No se pudo consultar PyPI"):
            actualizacion.descargar()
