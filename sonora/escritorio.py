"""
Lanzador de la app de escritorio "Sonora".

Punto de entrada de la aplicación: crea el servidor Flask (paquete `sonora`),
lo arranca en un hilo daemon sobre 127.0.0.1 en un puerto libre, espera a que
responda y abre una ventana nativa con pywebview apuntando a ese servidor.

Se invoca con `python -m sonora` (ver `sonora/__main__.py`) y está pensado para
funcionar tanto en desarrollo como empaquetado con PyInstaller (consola oculta,
sin depender del cwd).
"""

import socket
import sys
import threading
import time
import urllib.error
import urllib.request

# `crear_app()` inicializa la base de datos (vía preparar()) y registra los
# blueprints, devolviendo la aplicación lista para servir.
from .factory import crear_app

# Título de la ventana y dimensiones (según contrato).
TITULO_VENTANA = "Sonora"
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
    except Exception as exc:  # noqa: BLE001 # pragma: no cover - no tumbar el proceso
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


def reportar_error(mensaje: str) -> None:
    """Muestra un error de arranque de forma visible.

    Por stderr siempre; empaquetado con PyInstaller (``console=False``) stderr
    es invisible, así que en Windows se muestra además un MessageBox nativo:
    sin esto la app simplemente «no abriría» sin explicación alguna.
    """
    print(f"ERROR: {mensaje}", file=sys.stderr)
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, mensaje, TITULO_VENTANA, 0x10)
        except Exception:  # noqa: BLE001 - el aviso nunca debe romper el arranque
            pass


def crear_puente_pantalla_completa(ventana):
    """Devuelve la función que la interfaz llama al entrar o salir de pantalla completa.

    Cuando una página pide pantalla completa, WebView2 solo estira el elemento
    hasta ocupar la *ventana*: quitar el marco y ocupar el monitor le toca a la
    aplicación anfitriona, y pywebview no lo hace por su cuenta. La interfaz
    avisa aquí en cada ``fullscreenchange`` y la ventana la acompaña.

    ``ventana.toggle_fullscreen()`` solo sabe alternar, así que el estado se
    lleva aquí para que dos avisos iguales seguidos no lo desparejen.
    """
    cerrojo = threading.Lock()
    estado = {"completa": False}

    def pantalla_completa(activar) -> bool:
        activar = bool(activar)
        with cerrojo:
            if activar != estado["completa"]:
                estado["completa"] = activar
                ventana.toggle_fullscreen()
        return activar

    return pantalla_completa


def main() -> int:
    """Orquesta el arranque: servidor en hilo daemon + ventana pywebview."""
    # Importamos pywebview aquí para poder dar un mensaje de instalación claro
    # si no está disponible, sin romper el resto del arranque.
    try:
        import webview
    except ImportError:
        reportar_error(
            "Falta la dependencia 'pywebview'.\n"
            "Instálala con:\n\n"
            "    python -m pip install pywebview\n\n"
            "(o instala todas las dependencias con "
            "'python -m pip install -r requirements.txt')."
        )
        return 1

    # Creamos la app (crear_app inicializa la BD y reanuda descargas interrumpidas
    # ANTES de servir: si no, la primera llamada a la base de datos reventaría).
    try:
        app = crear_app()
    except ImportError as exc:
        reportar_error(
            f"Falta una dependencia de Python: {exc}.\n"
            "Instálalas con: python -m pip install -r requirements.txt"
        )
        return 1
    except OSError as exc:
        reportar_error(
            f"No se pudo preparar la carpeta de datos de la aplicación: {exc}"
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        reportar_error(f"No se pudo inicializar la aplicación: {exc}")
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
        reportar_error(
            "El servidor local no respondió a tiempo. "
            "Revisa que el puerto esté libre y que el paquete sonora arranque sin errores."
        )
        return 1

    # Creamos la ventana nativa apuntando al servidor local.
    ventana = webview.create_window(
        TITULO_VENTANA,
        url_base,
        width=ANCHO_VENTANA,
        height=ALTO_VENTANA,
        min_size=(ANCHO_MINIMO, ALTO_MINIMO),
    )
    # Disponible en la interfaz como ``pywebview.api.pantalla_completa(bool)``.
    ventana.expose(crear_puente_pantalla_completa(ventana))

    # webview.start() bloquea en el hilo principal hasta que se cierra la ventana.
    # Al volver, el proceso termina y los hilos daemon (servidor) mueren con él.
    webview.start()
    return 0
