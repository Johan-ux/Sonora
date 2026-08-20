"""Tests de ``sonora.ydl_opts`` (opciones compartidas CLI + app)."""

from __future__ import annotations

import pytest

from sonora.ydl_opts import (
    BITRATE_POR_DEFECTO,
    BITRATES_VALIDOS,
    FORMATO_POR_DEFECTO,
    RESOLUCION_POR_DEFECTO,
    RESOLUCIONES_VALIDAS,
    normalizar_bitrate,
    normalizar_formato,
    normalizar_resolucion,
    opciones_mp3,
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
