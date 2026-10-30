"""Tests de ``sonora.ydl_opts`` (opciones compartidas CLI + app)."""

from __future__ import annotations

import pytest

import sonora.ydl_opts as ydl_opts
from sonora.ydl_opts import (
    BITRATE_POR_DEFECTO,
    BITRATES_VALIDOS,
    FORMATO_POR_DEFECTO,
    RESOLUCION_POR_DEFECTO,
    RESOLUCIONES_VALIDAS,
    RUNTIMES_JS,
    detectar_runtime_js,
    normalizar_bitrate,
    normalizar_formato,
    normalizar_resolucion,
    opciones_mp3,
    opciones_runtime_js,
    opciones_video,
)


class TestNormalizarBitrate:
    @pytest.mark.parametrize("valido", BITRATES_VALIDOS)
    def test_validos_se_respetan(self, valido):
        assert normalizar_bitrate(valido) == valido

    @pytest.mark.parametrize("invalido", ["999", "0", "abc", "", "320.0", "-128"])
    def test_invalidos_caen_al_por_defecto(self, invalido):
        assert normalizar_bitrate(invalido) == BITRATE_POR_DEFECTO

    def test_none_cae_al_por_defecto(self):
        assert normalizar_bitrate(None) == BITRATE_POR_DEFECTO

    def test_recorta_espacios(self):
        assert normalizar_bitrate("  192  ") == "192"

    def test_entero_valido(self):
        # str(320) == "320": los enteros válidos también se aceptan.
        assert normalizar_bitrate(320) == "320"


class TestOpcionesMp3:
    def test_outtmpl_incluye_id_anticolision(self, tmp_path):
        opciones = opciones_mp3(tmp_path)
        assert "[%(id)s]" in opciones["outtmpl"]
        assert opciones["outtmpl"].startswith(str(tmp_path))

    def test_postprocessors_correctos(self, tmp_path):
        opciones = opciones_mp3(tmp_path)
        claves = [pp["key"] for pp in opciones["postprocessors"]]
        assert claves == ["FFmpegExtractAudio", "FFmpegMetadata", "EmbedThumbnail"]
        extractor = opciones["postprocessors"][0]
        assert extractor["preferredcodec"] == "mp3"
        assert extractor["preferredquality"] == BITRATE_POR_DEFECTO

    def test_bitrate_se_respeta_tal_cual_para_la_cli(self, tmp_path):
        # La CLI admite cualquier bitrate numérico: la whitelist se aplica en
        # la capa API (normalizar_bitrate), no aquí.
        opciones = opciones_mp3(tmp_path, bitrate="77")
        assert opciones["postprocessors"][0]["preferredquality"] == "77"

    def test_bitrate_vacio_cae_al_por_defecto(self, tmp_path):
        opciones = opciones_mp3(tmp_path, bitrate="")
        assert opciones["postprocessors"][0]["preferredquality"] == BITRATE_POR_DEFECTO

    def test_opciones_base(self, tmp_path):
        opciones = opciones_mp3(tmp_path)
        assert opciones["format"] == "bestaudio/best"
        assert opciones["noplaylist"] is True
        assert opciones["ignoreerrors"] is False
        assert opciones["writethumbnail"] is True


class TestNormalizarFormato:
    @pytest.mark.parametrize("valido", ["audio", "video", "AUDIO", " Video "])
    def test_validos_se_normalizan(self, valido):
        assert normalizar_formato(valido) in ("audio", "video")

    @pytest.mark.parametrize("invalido", ["", None, "mp3", "peli", 3])
    def test_invalidos_caen_al_por_defecto(self, invalido):
        assert normalizar_formato(invalido) == FORMATO_POR_DEFECTO


class TestNormalizarResolucion:
    @pytest.mark.parametrize("valido", RESOLUCIONES_VALIDAS)
    def test_validos_se_respetan(self, valido):
        assert normalizar_resolucion(valido) == valido

    @pytest.mark.parametrize("invalido", ["", None, "8k", "1081", "abc"])
    def test_invalidos_caen_al_por_defecto(self, invalido):
        assert normalizar_resolucion(invalido) == RESOLUCION_POR_DEFECTO


class TestOpcionesVideo:
    def test_outtmpl_incluye_id_anticolision(self, tmp_path):
        opciones = opciones_video(tmp_path)
        assert "[%(id)s]" in opciones["outtmpl"]

    def test_merge_mp4_y_sin_extraer_audio(self, tmp_path):
        opciones = opciones_video(tmp_path, "720")
        assert opciones["merge_output_format"] == "mp4"
        claves = [pp["key"] for pp in opciones["postprocessors"]]
        # Vídeo: metadatos sí, extracción de audio y carátula no.
        assert "FFmpegExtractAudio" not in claves
        assert "EmbedThumbnail" not in claves
        assert "FFmpegMetadata" in claves

    def test_formato_limita_por_altura(self, tmp_path):
        opciones = opciones_video(tmp_path, "720")
        assert "height<=720" in opciones["format"]

    def test_best_no_limita_altura(self, tmp_path):
        opciones = opciones_video(tmp_path, "best")
        assert "height" not in opciones["format"]
        assert opciones["format"] == "bestvideo+bestaudio/best"

    def test_resolucion_invalida_cae_al_por_defecto(self, tmp_path):
        opciones = opciones_video(tmp_path, "9999")
        assert f"height<={RESOLUCION_POR_DEFECTO}" in opciones["format"]


class TestRuntimeJS:
    """Autodetección del runtime de JavaScript que resuelve las firmas."""

    @pytest.fixture(autouse=True)
    def herramientas(self, tmp_path, monkeypatch):
        """Carpeta de programas incluidos, vacía salvo que el test ponga algo."""
        carpeta = tmp_path / "bin"
        carpeta.mkdir()
        monkeypatch.setattr(ydl_opts.paths, "DIR_HERRAMIENTAS", carpeta)
        return carpeta

    def test_el_deno_incluido_gana_al_del_sistema(self, monkeypatch, herramientas):
        deno = herramientas / "deno.exe"
        deno.write_bytes(b"")
        monkeypatch.setattr(ydl_opts.shutil, "which", lambda nombre: f"/usr/bin/{nombre}")
        assert detectar_runtime_js() == "deno"
        # No está en el PATH: yt-dlp tiene que recibir su ruta.
        assert opciones_runtime_js()["js_runtimes"] == {"deno": {"path": str(deno)}}

    def test_el_incluido_basta_sin_nada_en_el_path(self, monkeypatch, herramientas):
        (herramientas / "deno.exe").write_bytes(b"")
        monkeypatch.setattr(ydl_opts.shutil, "which", lambda nombre: None)
        assert detectar_runtime_js() == "deno"
        assert opciones_runtime_js()["remote_components"] == ["ejs:github"]

    def test_detecta_el_primero_disponible(self, monkeypatch):
        # Solo 'node' instalado: aunque 'deno' se prefiera, se elige node.
        monkeypatch.setattr(
            ydl_opts.shutil, "which", lambda nombre: "/usr/bin/node" if nombre == "node" else None
        )
        assert detectar_runtime_js() == "node"

    def test_respeta_el_orden_de_preferencia(self, monkeypatch):
        # Con todos instalados gana el primero de RUNTIMES_JS.
        monkeypatch.setattr(ydl_opts.shutil, "which", lambda nombre: f"/usr/bin/{nombre}")
        assert detectar_runtime_js() == RUNTIMES_JS[0]

    def test_sin_runtime_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(ydl_opts.shutil, "which", lambda nombre: None)
        assert detectar_runtime_js() is None

    def test_opciones_incluyen_runtime_y_solver(self, monkeypatch):
        monkeypatch.setattr(
            ydl_opts.shutil, "which", lambda nombre: "/usr/bin/node" if nombre == "node" else None
        )
        opciones = opciones_runtime_js()
        # La API de Python espera un dict {runtime: {config}}, no una lista.
        assert opciones["js_runtimes"] == {"node": {}}
        assert "ejs:github" in opciones["remote_components"]

    def test_sin_runtime_no_aporta_opciones(self, monkeypatch):
        monkeypatch.setattr(ydl_opts.shutil, "which", lambda nombre: None)
        assert opciones_runtime_js() == {}

    def test_bases_degradan_sin_runtime(self, monkeypatch, tmp_path):
        # Sin runtime la app debe seguir descargando: nada de js_runtimes,
        # y el resto de opciones intactas.
        monkeypatch.setattr(ydl_opts.shutil, "which", lambda nombre: None)
        for opciones in (opciones_mp3(tmp_path), opciones_video(tmp_path)):
            assert "js_runtimes" not in opciones
            assert "remote_components" not in opciones
            assert opciones["format"]

    def test_bases_incorporan_runtime(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ydl_opts.shutil, "which", lambda nombre: f"/usr/bin/{nombre}")
        for opciones in (opciones_mp3(tmp_path), opciones_video(tmp_path)):
            assert opciones["js_runtimes"] == {RUNTIMES_JS[0]: {}}
            assert opciones["remote_components"] == ["ejs:github"]
