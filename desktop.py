# -*- coding: utf-8 -*-
"""
Lanzador de la app de escritorio "Mi Música".

Punto de entrada de la aplicación: crea el servidor Flask (paquete `mi_musica`),
lo arranca en un hilo daemon sobre 127.0.0.1 en un puerto libre, espera a que
responda y abre una ventana nativa con pywebview apuntando a ese servidor.

Está pensado para funcionar tanto en desarrollo (`python desktop.py`) como
empaquetado con PyInstaller (consola oculta, sin depender del cwd).
"""

import socket
import sys
import threading
import time
import urllib.error
import urllib.request

# La fábrica de la app vive en el paquete `mi_musica`. `crear_app()` inicializa
# la base de datos (vía preparar()) y registra los blueprints, devolviendo la
# aplicación lista para servir.
from mi_musica.factory import crear_app

# Título de la ventana y dimensiones (según contrato).
TITULO_VENTANA = "🎵 Mi Música"
ANCHO_VENTANA = 1200
ALTO_VENTANA = 780
ANCHO_MINIMO = 940
ALTO_MINIMO = 600

# Host fijo: solo accesible localmente.
HOST = "127.0.0.1"


def buscar_puerto_libre() -> int:
    """Pide al sistema operativo un puerto TCP libre (bind a puerto 0).

    Devolvemos el número de puerto y cerramos el socket; existe una pequeña
    ventana de carrera hasta que Flask lo vuelve a tomar, pero en uso personal
    sobre loopback es perfectamente fiable.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def arrancar_servidor(app, puerto: int) -> None:
    """Arranca el servidor Flask. Se ejecuta dentro de un hilo daemon.

    `use_reloader=False` es imprescindible: el reloader relanzaría el proceso
    y no tiene sentido (ni funciona) bajo pywebview/empaquetado. `threaded=True`
    permite atender el SSE y peticiones concurrentes. `debug=False` en producción.
    """
    try:
        app.run(
            host=HOST,
            port=puerto,
            debug=False,
            use_reloader=False,
            threaded=True,
        )
    except Exception as exc:  # pragma: no cover - el hilo no debe tumbar el proceso
        # Si el servidor muere, lo registramos por stderr (visible en dev).
        # La ventana detectará que '/' no responde y mostrará el fallo de espera.
        print(f"[desktop] El servidor Flask se detuvo: {exc}", file=sys.stderr)


def esperar_servidor(url_base: str, intentos: int = 100, espera: float = 0.1) -> bool:
    """Sondea HTTP GET a '/' hasta que el servidor responda (o se agoten intentos).

    Devuelve True si el servidor respondió, False si se agotó el tiempo
    (~10 s por defecto). Cualquier respuesta HTTP (incluido un código de error)
    cuenta como "vivo": lo que nos interesa es que el socket acepte y conteste.
    """
    for _ in range(intentos):
        try:
            with urllib.request.urlopen(url_base, timeout=1) as resp:
                # Basta con que conteste algo.
                resp.read(1)
                return True
        except urllib.error.HTTPError:
            # Respondió con un código HTTP (p. ej. 404): el servidor está vivo.
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            # Aún no escucha; reintentamos.
            time.sleep(espera)
    return False


def main() -> int:
    """Orquesta el arranque: servidor en hilo daemon + ventana pywebview."""
    # Importamos pywebview aquí para poder dar un mensaje de instalación claro
    # si no está disponible, sin romper el resto del arranque.
    try:
        import webview
    except ImportError:
        print(
            "ERROR: Falta la dependencia 'pywebview'.\n"
            "Instálala con:\n\n"
            "    python -m pip install pywebview\n\n"
            "(o instala todas las dependencias con "
            "'python -m pip install -r requirements.txt').",
            file=sys.stderr,
        )
        return 1

    # Creamos la app (crear_app inicializa la BD y reanuda descargas interrumpidas
    # ANTES de servir: si no, la primera llamada a la base de datos reventaría).
    try:
        app = crear_app()
    except Exception as exc:
        print(f"ERROR: No se pudo inicializar la aplicación: {exc}", file=sys.stderr)
        return 1

    puerto = buscar_puerto_libre()
    url_base = f"http://{HOST}:{puerto}"

    # Servidor Flask en un hilo daemon: morirá automáticamente al cerrar la ventana.
    hilo_servidor = threading.Thread(
        target=arrancar_servidor,
        args=(app, puerto),
        name="servidor-flask",
        daemon=True,
    )
    hilo_servidor.start()

    # Esperamos a que el servidor esté listo antes de abrir la ventana, para
    # evitar mostrar una página de error de conexión.
    if not esperar_servidor(url_base + "/"):
        print(
            "ERROR: El servidor Flask no respondió a tiempo. "
            "Revisa que el puerto esté libre y que el paquete mi_musica arranque sin errores.",
            file=sys.stderr,
        )
        return 1

    # Creamos la ventana nativa apuntando al servidor local.
    webview.create_window(
        TITULO_VENTANA,
        url_base,
        width=ANCHO_VENTANA,
        height=ALTO_VENTANA,
        min_size=(ANCHO_MINIMO, ALTO_MINIMO),
    )

    # webview.start() bloquea en el hilo principal hasta que se cierra la ventana.
    # Al volver, el proceso termina y los hilos daemon (servidor) mueren con él.
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
