"""Tests del ensamblaje de la app (``sonora.factory``).

El grueso son las peticiones de origen ajeno: Sonora escucha en loopback, pero
mientras la ventana está abierta cualquier web puede enviarle un POST, así que
el guard de ``Origin`` es lo único que separa una pestaña cualquiera de vaciar
la cola o el historial.
"""

from __future__ import annotations

import pytest

from sonora.factory import _origen_permitido

# Endpoints que cambian estado sin necesitar cuerpo: los alcanzables por un
# <form> cross-origin, que no puede fijar Content-Type: application/json.
RUTAS_SENSIBLES = ("/api/historial/limpiar", "/api/cola/limpiar", "/api/abrir-carpeta")

BASE = "http://127.0.0.1:5099"


class TestOrigenPermitido:
    @pytest.mark.parametrize(
        "origen",
        [
            "http://127.0.0.1:5099",
            "http://localhost:5099",
            "https://127.0.0.1:5099",
        ],
    )
    def test_loopback_se_acepta(self, origen):
        assert _origen_permitido(origen, "127.0.0.1:5099") is True

    @pytest.mark.parametrize(
        "origen",
        [
            "https://web-mala.example",
            "http://ejemplo.com",
            # Un host que solo *empieza* por la IP no es la IP.
            "http://127.0.0.1.atacante.com:5099",
            # Esquemas que no son web no tienen por qué mandar nada.
            "file://",
            "null",
            "",
        ],
    )
    def test_origen_ajeno_se_rechaza(self, origen):
        assert _origen_permitido(origen, "127.0.0.1:5099") is False


class TestGuardDeOrigen:
    @pytest.mark.parametrize("ruta", RUTAS_SENSIBLES)
    def test_post_de_web_ajena_se_bloquea(self, client, ruta):
        # Exactamente lo que puede enviar un <form> desde cualquier página.
        respuesta = client.post(
            ruta,
            data="x=1",
            content_type="application/x-www-form-urlencoded",
            headers={"Origin": "https://web-mala.example"},
        )
        assert respuesta.status_code == 403

    @pytest.mark.parametrize("ruta", RUTAS_SENSIBLES)
    def test_la_propia_app_no_se_bloquea(self, client, ruta):
        respuesta = client.post(
            ruta, json={}, headers={"Origin": BASE}, base_url=BASE
        )
        assert respuesta.status_code != 403

    def test_sin_origin_se_permite(self, client):
        # La CLI, curl y los propios tests no mandan Origin; el objetivo del
        # guard es el navegador ajeno, que siempre lo envía.
        assert client.post("/api/cola/limpiar", json={}).status_code != 403

    def test_las_lecturas_no_se_bloquean(self, client):
        # Un GET no cambia nada, y bloquearlo rompería enlaces legítimos.
        respuesta = client.get(
            "/api/salud?red=0", headers={"Origin": "https://web-mala.example"}
        )
        assert respuesta.status_code == 200

    def test_el_bloqueo_responde_json(self, client):
        # El frontend construye sus mensajes de error leyendo 'error'.
        respuesta = client.post(
            "/api/cola/limpiar", json={}, headers={"Origin": "https://web-mala.example"}
        )
        assert respuesta.get_json()["error"]
