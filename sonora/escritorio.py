"""
Lanzador de la app de escritorio "Sonora".

Punto de entrada de la aplicación: crea el servidor Flask (paquete `sonora`),
lo arranca en un hilo daemon sobre 127.0.0.1 en un puerto libre, espera a que
responda y abre una ventana nativa con pywebview apuntando a ese servidor.

Si la ventana no puede abrirse (en Linux pywebview no trae motor de ventana; en
un Windows sin WebView2 tampoco hay con qué), la interfaz se abre en el
navegador: es la misma página. También se pide con `--navegador`.

Se invoca con `python -m sonora` (ver `sonora/__main__.py`) y está pensado para
funcionar tanto en desarrollo como empaquetado con PyInstaller (consola oculta,
sin depender del cwd).
"""

import argparse
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

# `crear_app()` inicializa la base de datos (vía preparar()) y registra los
# blueprints, devolviendo la aplicación lista para servir.
from . import paths, sse
from .factory import crear_app
from .paths import RUTA_RECURSOS

# Icono de la ventana: la marca con los colores de «ocaso», el tema por defecto.
# Va fijo aunque se elija otro tema (lo genera scripts/generar_icono.py).
RUTA_ICONO = RUTA_RECURSOS / "static" / "img" / "sonora.ico"
# Nombre con el que Windows identifica la app (ver identificar_app).
ID_APP_WINDOWS = "Sonora.Escritorio"

# Fichero que reserva la carpeta de datos para una sola instancia de la app.
NOMBRE_CERROJO = "sonora.lock"
# Se guarda aquí mientras viva el proceso: si el fichero se cerrase, el
# cerrojo se soltaría.
_cerrojo_de_instancia = None

# Título de la ventana y dimensiones (según contrato).
TITULO_VENTANA = "Sonora"
ANCHO_VENTANA = 1200
ALTO_VENTANA = 780
ANCHO_MINIMO = 940
ALTO_MINIMO = 600
# Fondo de la ventana antes de que cargue la página (--fondo-0 en estilo.css).
COLOR_FONDO = "#000000"

# Host fijo: solo accesible localmente.
HOST = "127.0.0.1"

# La instancia abierta (su proceso y su dirección), para que otro arranque
# pueda volver a ella (ver volver_a_la_que_ya_esta).
NOMBRE_INSTANCIA = "sonora.instancia"
# En modo navegador, cuánto se espera sin ninguna pestaña antes de cerrar: da
# tiempo a recargar o a volver a abrirla. Cerrar una pestaña tarda además hasta
# medio minuto en notarse (el latido del SSE, en api/eventos.py).
GRACIA_SIN_PESTANAS = 30.0
# Si en este tiempo no llega a abrirse ninguna pestaña, la app se cierra: sin
# ventana ni consola (el .exe) quedaría un proceso invisible para siempre.
ESPERA_PRIMERA_PESTANA = 300.0


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
    # Sin proxy. urllib aplica el del sistema (o HTTP_PROXY) también a
    # 127.0.0.1, y entonces quien contesta —o deja de contestar— es el proxy:
    # un 502 suyo daría por viva una app que aún no escucha.
    abrir = urllib.request.build_opener(urllib.request.ProxyHandler({})).open
    for _ in range(intentos):
        try:
            with abrir(url_base, timeout=1) as resp:
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


def tomar_cerrojo_de_instancia(carpeta):
    """Reserva la carpeta de datos para este proceso.

    Devuelve el fichero abierto que sostiene el cerrojo, o ``None`` si ya lo
    tiene otra instancia. Dos Sonoras sobre los mismos datos se pisan: al
    arrancar, la segunda devuelve a la cola lo que la primera está descargando,
    y el mismo vídeo acaba bajándose dos veces a la vez sobre los mismos
    ficheros.

    El cerrojo es del sistema operativo sobre un fichero abierto: se suelta
    solo cuando el proceso termina, también si se cierra mal, así que nunca hay
    que limpiarlo a mano. Lanza ``OSError`` si la carpeta no se puede crear.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    fichero = open(carpeta / NOMBRE_CERROJO, "a+b")  # noqa: SIM115 - debe seguir abierto
    try:
        if os.name == "nt":
            import msvcrt

            fichero.seek(0)
            msvcrt.locking(fichero.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fichero.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fichero.close()
        return None
    return fichero


def mostrar_ventana_existente(pid: int) -> bool:
    """Trae al frente la ventana de la instancia que ya está abierta.

    Se busca entre las ventanas de *su* proceso: por el título solo, valdría
    cualquiera que se llame «Sonora», como el Explorador abierto en la carpeta
    del zip o un IDE con el proyecto. Devuelve True si la encontró. Solo sabe
    hacerlo en Windows; en otra plataforma devuelve False.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        usuario = ctypes.windll.user32
        encontradas = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def mirar(hwnd, _):
            dueno = wintypes.DWORD()
            usuario.GetWindowThreadProcessId(hwnd, ctypes.byref(dueno))
            if dueno.value == pid and usuario.IsWindowVisible(hwnd):
                titulo = ctypes.create_unicode_buffer(256)
                usuario.GetWindowTextW(hwnd, titulo, len(titulo))
                if titulo.value == TITULO_VENTANA:
                    encontradas.append(hwnd)
                    return False
            return True

        usuario.EnumWindows(mirar, 0)
        if not encontradas:
            return False
        ventana = encontradas[0]
        if usuario.IsIconic(ventana):
            usuario.ShowWindow(ventana, 9)  # SW_RESTORE: estaba minimizada
        usuario.SetForegroundWindow(ventana)
        return True
    except Exception:  # noqa: BLE001 - es una cortesía: nunca debe romper la salida
        return False


def identificar_app() -> None:
    """Da a la app un nombre propio ante Windows cuando corre sobre el intérprete.

    Lanzada con ``python -m sonora``, Windows agrupa la ventana con Python y
    enseña el icono de este en la barra de tareas, tenga la ventana el que
    tenga. Con un identificador propio usa el de la ventana.

    Empaquetada no hace falta (el ``.exe`` ya lleva su icono) y sería
    contraproducente: un acceso directo anclado dejaría de corresponderse con
    la ventana abierta.
    """
    if sys.platform != "win32" or getattr(sys, "frozen", False):
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ID_APP_WINDOWS)
    except Exception:  # noqa: BLE001 - es cosmético: nunca debe impedir el arranque
        pass


def esta_maximizada(ventana) -> bool:
    """Indica si la ventana está maximizada.

    pywebview no lo cuenta: se le pregunta a la ventana nativa, que en Windows
    es un formulario de WinForms. En otra plataforma no se sabe y se dice que no.
    """
    estado = getattr(getattr(ventana, "native", None), "WindowState", None)
    return str(estado) == "Maximized"


def crear_puente_pantalla_completa(ventana):
    """Devuelve la función que la interfaz llama al entrar o salir de pantalla completa.

    Cuando una página pide pantalla completa, WebView2 solo estira el elemento
    hasta ocupar la *ventana*: quitar el marco y ocupar el monitor le toca a la
    aplicación anfitriona, y pywebview no lo hace por su cuenta. La interfaz
    avisa aquí en cada ``fullscreenchange`` y la ventana la acompaña.

    ``ventana.toggle_fullscreen()`` solo sabe alternar, así que el estado se
    lleva aquí para que dos avisos iguales seguidos no lo desparejen.

    Al salir, pywebview deja la ventana en tamaño normal aunque estuviera
    maximizada, y con las medidas que tenía al entrar: quedaría sin maximizar y
    del tamaño de la pantalla. Por eso una ventana maximizada se restaura antes
    de entrar (así lo que pywebview recuerda es su tamaño normal de verdad) y
    se vuelve a maximizar al salir.
    """
    cerrojo = threading.Lock()
    estado = {"completa": False, "maximizada": False}

    def pantalla_completa(activar) -> bool:
        activar = bool(activar)
        with cerrojo:
            if activar == estado["completa"]:
                return activar
            estado["completa"] = activar
            if activar:
                estado["maximizada"] = esta_maximizada(ventana)
                if estado["maximizada"]:
                    ventana.restore()
                ventana.toggle_fullscreen()
            else:
                ventana.toggle_fullscreen()
                if estado["maximizada"]:
                    ventana.maximize()
        return activar

    return pantalla_completa


def abrir_ventana(webview, url_base: str) -> bool:
    """Abre la ventana propia y bloquea hasta que se cierra.

    Devuelve ``False`` si la ventana no llegó a abrirse: pywebview lanza al
    arrancar cuando no encuentra con qué dibujarla (en Linux no trae motor de
    ventana; en un Windows sin WebView2 tampoco hay). Entonces se usa el
    navegador. Un fallo con la ventana ya abierta sí es un error y se propaga.
    """
    ventana = webview.create_window(
        TITULO_VENTANA,
        url_base,
        width=ANCHO_VENTANA,
        height=ALTO_VENTANA,
        min_size=(ANCHO_MINIMO, ALTO_MINIMO),
        # El negro de la interfaz desde el primer instante: sin esto la ventana
        # abre en blanco hasta que carga la página.
        background_color=COLOR_FONDO,
    )
    # Disponible en la interfaz como ``pywebview.api.pantalla_completa(bool)``.
    ventana.expose(crear_puente_pantalla_completa(ventana))
    mostrada = threading.Event()
    ventana.events.shown += lambda *_: mostrada.set()

    # webview.start() bloquea en el hilo principal hasta que se cierra la ventana.
    # Al volver, el proceso termina y los hilos daemon (servidor) mueren con él.
    # Sin el icono, la ventana enseñaría el del ejecutable (el de Python).
    try:
        webview.start(icon=str(RUTA_ICONO))
    except Exception:
        # Sin ventana queda el navegador; con ella abierta, el fallo es de verdad.
        if mostrada.is_set():
            raise
        return False
    return mostrada.is_set()


def esperar_a_que_cierren_las_pestanas(
    gracia: float = GRACIA_SIN_PESTANAS,
    sondeo: float = 1.0,
    contar=sse.numero_clientes,
    espera_inicial: float = ESPERA_PRIMERA_PESTANA,
) -> None:
    """Bloquea mientras haya alguna pestaña de Sonora abierta en el navegador.

    Cada pestaña mantiene abierta su conexión de eventos (``/api/eventos``).
    Para la primera se espera hasta ``espera_inicial``: el navegador puede
    tardar en arrancar, o hay que abrir la dirección a mano. Después, la app se
    da por cerrada cuando lleva ``gracia`` segundos sin ninguna, para que una
    recarga no la cierre.
    """
    inicio = time.monotonic()
    hubo_pestana = False
    sin_pestanas_desde = None
    while True:
        if contar():
            hubo_pestana, sin_pestanas_desde = True, None
        elif hubo_pestana:
            if sin_pestanas_desde is None:
                sin_pestanas_desde = time.monotonic()
            elif time.monotonic() - sin_pestanas_desde >= gracia:
                return
        elif time.monotonic() - inicio >= espera_inicial:
            return
        time.sleep(sondeo)


def abrir_pestana(url_base: str) -> None:
    """Abre ``url_base`` en el navegador predeterminado; si no puede, lo dice."""
    if not webbrowser.open(url_base):
        reportar_error(f"No se pudo abrir el navegador. Abre esta dirección: {url_base}")


def abrir_en_navegador(url_base: str) -> int:
    """La interfaz en el navegador predeterminado, mientras quede alguna pestaña.

    Sin ventana no hay nada que cerrar para terminar: la app se cierra sola un
    rato después de cerrar la última pestaña, o con Ctrl+C en la terminal.
    """
    print(
        f"Sonora está abierta en el navegador: {url_base}\n"
        "Se cierra sola al cerrar su pestaña (o con Ctrl+C).",
        flush=True,
    )
    # En otro hilo: webbrowser.open() puede no volver hasta que se cierre el
    # navegador (si lo lanza él, como con la variable BROWSER), y mientras
    # tanto hay que estar pendiente de las pestañas.
    threading.Thread(
        target=abrir_pestana, args=(url_base,), name="abrir-navegador", daemon=True
    ).start()
    try:
        esperar_a_que_cierren_las_pestanas()
    except KeyboardInterrupt:
        pass
    return 0


def anotar_instancia(carpeta, url_base: str) -> None:
    """Deja anotados el proceso y la dirección de esta instancia.

    ``url_base`` vacía borra lo anotado por una sesión anterior: hasta que esta
    sirva su dirección, otro arranque no debe volver a la de entonces.
    """
    fichero = carpeta / NOMBRE_INSTANCIA
    try:
        if url_base:
            datos = {"pid": os.getpid(), "url": url_base}
            fichero.write_text(json.dumps(datos), encoding="utf-8")
        else:
            fichero.unlink(missing_ok=True)
    except OSError:
        pass  # sin ella, otro arranque solo dirá que Sonora ya está abierta


def leer_instancia(carpeta) -> dict | None:
    """La instancia anotada (``{"pid", "url"}``), o ``None`` si no hay o no es fiable.

    Solo se acepta una dirección local: el fichero lo podría haber tocado cualquiera.
    """
    try:
        datos = json.loads((carpeta / NOMBRE_INSTANCIA).read_text(encoding="utf-8"))
        pid, url = datos["pid"], datos["url"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(pid, int) or not isinstance(url, str):
        return None
    if not re.fullmatch(rf"http://{re.escape(HOST)}:\d{{1,5}}", url):
        return None
    return {"pid": pid, "url": url}


def volver_a_la_que_ya_esta(carpeta) -> bool:
    """Trae al frente la instancia en marcha: su ventana o, si no tiene, una pestaña."""
    instancia = leer_instancia(carpeta)
    if instancia is None:
        return False
    return mostrar_ventana_existente(instancia["pid"]) or webbrowser.open(instancia["url"])


def main(argv: list[str] | None = None) -> int:
    """Orquesta el arranque: servidor en hilo daemon + ventana (o navegador)."""
    parser = argparse.ArgumentParser(
        prog="python -m sonora",
        description="Abre Sonora en su ventana o, si no puede, en el navegador.",
    )
    parser.add_argument(
        "--navegador",
        action="store_true",
        help="abrir la interfaz en el navegador en vez de en la ventana propia",
    )
    argumentos = parser.parse_args(argv)

    # pywebview se importa aquí: si falta, la app se abre igual en el navegador.
    webview = None
    if not argumentos.navegador:
        try:
            import webview
        except ImportError:
            webview = None

    # Una sola instancia por carpeta de datos, y se comprueba antes de tocar la
    # base de datos: crear_app() ya da por interrumpido lo que encuentra
    # descargándose.
    global _cerrojo_de_instancia
    try:
        _cerrojo_de_instancia = tomar_cerrojo_de_instancia(paths.DIR_BASE)
    except OSError as exc:
        reportar_error(
            f"No se pudo preparar la carpeta de datos de la aplicación: {exc}"
        )
        return 1
    if _cerrojo_de_instancia is None:
        if not volver_a_la_que_ya_esta(paths.DIR_BASE):
            reportar_error("Sonora ya está abierta.")
        return 0
    anotar_instancia(paths.DIR_BASE, "")

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
    anotar_instancia(paths.DIR_BASE, url_base)

    if webview is not None:
        # Antes de crear la ventana: Windows decide con qué app agruparla al abrirla.
        identificar_app()
        if abrir_ventana(webview, url_base):
            return 0
        print("No se pudo abrir la ventana de Sonora: se abre en el navegador.", file=sys.stderr)
    return abrir_en_navegador(url_base)
