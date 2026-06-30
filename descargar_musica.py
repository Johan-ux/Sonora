#!/usr/bin/env python3
"""Descarga el MP3 de mejor calidad desde URLs de YouTube.

Lee las URLs de un fichero de texto (separadas por comas y/o saltos de línea),
extrae el audio a MP3 con yt-dlp a un bitrate fijo (320 kbps por defecto),
incrusta la carátula y los metadatos, y continúa aunque alguna URL falle.

Características:
    * Bitrate fijo (CBR) configurable, 320 kbps por defecto.
    * Incrustación de carátula (thumbnail) y metadatos en el MP3.
    * Soporte de cookies (fichero Netscape o exportadas del navegador) para
      evitar bloqueos de YouTube desde la IP del servidor.
    * Registro de las descargas fallidas en un fichero de log.

Requisitos de sistema:
    * ffmpeg debe estar instalado y disponible en el PATH.

Uso:
    python descargar_musica.py urls.txt
    python descargar_musica.py urls.txt -o ./descargas
    python descargar_musica.py urls.txt -o ./descargas --cookies cookies.txt
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import yt_dlp
    from yt_dlp.cookies import SUPPORTED_BROWSERS
    from yt_dlp.utils import DownloadError
except ImportError:  # pragma: no cover - guía al usuario si falta la dependencia
    sys.exit(
        "Falta la dependencia 'yt-dlp'.\n"
        "Instálala con: pip install -r requirements.txt"
    )

# La localización robusta de ffmpeg se comparte con la app de escritorio.
from mi_musica.ffmpeg import localizar_ffmpeg


# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #

BITRATE_POR_DEFECTO = "320"
NOMBRE_LOG_FALLIDOS = "descargas_fallidas.log"


@dataclass(frozen=True)
class Config:
    """Parámetros de ejecución resueltos desde la CLI."""

    fichero_entrada: Path
    carpeta_salida: Path
    bitrate: str
    fichero_cookies: Path | None
    cookies_navegador: tuple[str, ...] | None
    log_fallidos: Path
    ffmpeg_location: Path | None


# --------------------------------------------------------------------------- #
# Lectura de URLs
# --------------------------------------------------------------------------- #

def leer_urls(fichero_entrada: Path) -> list[str]:
    """Lee y normaliza las URLs de un fichero de texto.

    Las URLs pueden estar separadas por comas y/o saltos de línea. Se ignoran
    los espacios sobrantes, las líneas en blanco y las que empiezan por '#'
    (comentarios). Se eliminan duplicados conservando el orden de aparición.

    Args:
        fichero_entrada: Ruta al fichero de texto con las URLs.

    Returns:
        Lista de URLs únicas y normalizadas.

    Raises:
        OSError: Si el fichero de entrada no se puede leer.
    """
    # utf-8-sig descarta el BOM que añaden el Bloc de notas y otros editores en
    # Windows; sin esto el BOM se pegaría a la primera URL y rompería la
    # detección de líneas de comentario que empiezan por '#'.
    contenido = fichero_entrada.read_text(encoding="utf-8-sig")

    urls: list[str] = []
    vistas: set[str] = set()
    for linea in contenido.splitlines():
        if linea.lstrip().startswith("#"):
            continue
        for fragmento in linea.split(","):
            url = fragmento.strip()
            if url and url not in vistas:
                vistas.add(url)
                urls.append(url)
    return urls


# --------------------------------------------------------------------------- #
# Opciones de yt-dlp
# --------------------------------------------------------------------------- #

def construir_opciones_ydl(config: Config) -> dict:
    """Construye el diccionario de opciones para yt-dlp.

    Configura la extracción a MP3 con bitrate fijo, la incrustación de carátula
    y metadatos, y el soporte de cookies si se ha indicado.

    Args:
        config: Configuración de ejecución.

    Returns:
        Diccionario de opciones listo para ``yt_dlp.YoutubeDL``.
    """
    opciones: dict = {
        # Mejor pista de audio disponible (con respaldo al mejor formato).
        "format": "bestaudio/best",
        # Plantilla del nombre de salida dentro de la carpeta de destino.
        "outtmpl": str(config.carpeta_salida / "%(title)s.%(ext)s"),
        # Necesario para poder incrustar la carátula posteriormente.
        "writethumbnail": True,
        # Gestionamos los errores nosotros (uno por URL); no los silenciamos.
        "ignoreerrors": False,
        # No expandir listas de reproducción accidentalmente.
        "noplaylist": True,
        "postprocessors": [
            # 1) Extrae el audio y lo convierte a MP3 con bitrate fijo (CBR).
            #    Un valor > 10 hace que yt-dlp use '-b:a <valor>k' (bitrate
            #    fijo) en lugar de VBR ('-q:a'). 320 => 320 kbps constantes.
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": config.bitrate,
            },
            # 2) Escribe los metadatos (título, artista, etc.) en el MP3.
            {
                "key": "FFmpegMetadata",
                "add_metadata": True,
            },
            # 3) Incrusta la carátula. Convierte la miniatura (webp/png) al
            #    formato adecuado para el MP3 cuando hace falta.
            {
                "key": "EmbedThumbnail",
                "already_have_thumbnail": False,
            },
        ],
    }

    if config.fichero_cookies is not None:
        opciones["cookiefile"] = str(config.fichero_cookies)
    if config.cookies_navegador is not None:
        opciones["cookiesfrombrowser"] = config.cookies_navegador
    if config.ffmpeg_location is not None:
        opciones["ffmpeg_location"] = str(config.ffmpeg_location)

    return opciones


# --------------------------------------------------------------------------- #
# Registro de fallos
# --------------------------------------------------------------------------- #

def registrar_fallo(log_fallidos: Path, url: str, error: str) -> None:
    """Añade una línea al log de descargas fallidas.

    El formato es ``<timestamp ISO-8601>\\t<url>\\t<error>``, una línea por fallo,
    en modo «append» para no perder el registro si el proceso se interrumpe.

    Args:
        log_fallidos: Ruta del fichero de log.
        url: URL que ha fallado.
        error: Mensaje de error asociado.
    """
    marca_tiempo = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    mensaje = " ".join(error.split())  # colapsa saltos de línea y espacios
    try:
        with log_fallidos.open("a", encoding="utf-8") as fichero:
            fichero.write(f"{marca_tiempo}\t{url}\t{mensaje}\n")
    except OSError as exc:
        # El registro nunca debe abortar el lote (requisito: continuar si falla).
        print(
            f"  [AVISO] No se pudo escribir en el log de fallos ({log_fallidos}): {exc}",
            file=sys.stderr,
        )


# --------------------------------------------------------------------------- #
# Descarga
# --------------------------------------------------------------------------- #

def descargar_todas(urls: list[str], config: Config) -> tuple[list[str], list[str]]:
    """Descarga todas las URLs, continuando aunque alguna falle.

    Args:
        urls: Lista de URLs a descargar.
        config: Configuración de ejecución.

    Returns:
        Tupla ``(exitos, fallos)`` con las listas de URLs correctas y fallidas.
    """
    opciones = construir_opciones_ydl(config)
    exitos: list[str] = []
    fallos: list[str] = []
    total = len(urls)

    with yt_dlp.YoutubeDL(opciones) as ydl:
        for indice, url in enumerate(urls, start=1):
            print(f"\n[{indice}/{total}] Descargando: {url}")
            try:
                codigo = ydl.download([url])
            except DownloadError as error:
                print(f"  [ERROR] No se pudo descargar: {url}", file=sys.stderr)
                registrar_fallo(config.log_fallidos, url, str(error))
                fallos.append(url)
            except Exception as error:  # noqa: BLE001 - robustez: nunca abortar el lote
                print(f"  [ERROR] Fallo inesperado en: {url} ({error})", file=sys.stderr)
                registrar_fallo(config.log_fallidos, url, repr(error))
                fallos.append(url)
            else:
                # ydl.download devuelve un código != 0 si la descarga falló.
                if codigo:
                    print(f"  [ERROR] No se pudo descargar: {url}", file=sys.stderr)
                    registrar_fallo(config.log_fallidos, url, "Código de salida no nulo de yt-dlp")
                    fallos.append(url)
                else:
                    exitos.append(url)

    return exitos, fallos


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parsear_navegador(spec: str) -> tuple[str, ...]:
    """Parsea la especificación de navegador para extraer cookies.

    Formato aceptado: ``NAVEGADOR[:PERFIL]`` (p. ej. ``chrome`` o
    ``firefox:default``).

    Args:
        spec: Cadena con el navegador y, opcionalmente, el perfil.

    Returns:
        Tupla compatible con la opción ``cookiesfrombrowser`` de yt-dlp.
    """
    navegador, separador, perfil = spec.partition(":")
    if separador and perfil:
        return (navegador, perfil)
    return (navegador,)


def parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    """Define y parsea los argumentos de la línea de comandos."""
    parser = argparse.ArgumentParser(
        prog="descargar_musica.py",
        description=(
            "Descarga el MP3 de mejor calidad desde URLs de YouTube leídas de "
            "un fichero de texto (separadas por comas)."
        ),
    )
    parser.add_argument(
        "fichero_entrada",
        type=Path,
        help="Fichero de texto con las URLs (separadas por comas y/o saltos de línea).",
    )
    parser.add_argument(
        "-o",
        "--salida",
        type=Path,
        default=Path("descargas"),
        help="Carpeta de salida donde se guardarán los MP3 (por defecto: descargas).",
    )
    parser.add_argument(
        "-b",
        "--bitrate",
        default=BITRATE_POR_DEFECTO,
        help=f"Bitrate fijo del MP3 en kbps, CBR (por defecto: {BITRATE_POR_DEFECTO}).",
    )
    parser.add_argument(
        "--cookies",
        type=Path,
        default=None,
        metavar="FICHERO",
        help="Fichero de cookies en formato Netscape (para evitar bloqueos).",
    )
    parser.add_argument(
        "--cookies-navegador",
        default=None,
        metavar="NAVEGADOR[:PERFIL]",
        help=(
            "Extrae las cookies de un navegador instalado "
            "(p. ej. 'chrome', 'firefox:default')."
        ),
    )
    parser.add_argument(
        "--log-fallidos",
        type=Path,
        default=None,
        metavar="FICHERO",
        help=(
            "Fichero donde registrar las descargas fallidas "
            f"(por defecto: <salida>/{NOMBRE_LOG_FALLIDOS})."
        ),
    )
    parser.add_argument(
        "--ffmpeg",
        type=Path,
        default=None,
        metavar="RUTA",
        help=(
            "Ruta al binario de ffmpeg o a su carpeta. Si se omite, se busca en "
            "el PATH y en las ubicaciones habituales (incluida la de winget)."
        ),
    )
    return parser.parse_args(argv)


def construir_config(args: argparse.Namespace) -> Config:
    """Convierte los argumentos parseados en un objeto ``Config`` validado."""
    carpeta_salida: Path = args.salida
    log_fallidos: Path = args.log_fallidos or (carpeta_salida / NOMBRE_LOG_FALLIDOS)
    cookies_navegador = (
        parsear_navegador(args.cookies_navegador) if args.cookies_navegador else None
    )
    return Config(
        fichero_entrada=args.fichero_entrada,
        carpeta_salida=carpeta_salida,
        bitrate=str(args.bitrate),
        fichero_cookies=args.cookies,
        cookies_navegador=cookies_navegador,
        log_fallidos=log_fallidos,
        ffmpeg_location=localizar_ffmpeg(args.ffmpeg),
    )


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de la aplicación.

    Returns:
        Código de salida: 0 si todo correcto, 1 si hubo algún fallo de descarga,
        2 ante errores de configuración (fichero inexistente, sin URLs, etc.).
    """
    args = parsear_argumentos(argv)
    config = construir_config(args)

    if not config.fichero_entrada.is_file():
        print(
            f"[ERROR] El fichero de entrada no existe: {config.fichero_entrada}",
            file=sys.stderr,
        )
        return 2

    if config.fichero_cookies is not None and not config.fichero_cookies.is_file():
        print(
            f"[ERROR] El fichero de cookies no existe: {config.fichero_cookies}",
            file=sys.stderr,
        )
        return 2

    if config.cookies_navegador is not None:
        navegador = config.cookies_navegador[0].lower()
        if navegador not in SUPPORTED_BROWSERS:
            soportados = ", ".join(sorted(SUPPORTED_BROWSERS))
            print(
                f"[ERROR] Navegador no soportado para cookies: '{navegador}'. "
                f"Navegadores válidos: {soportados}.",
                file=sys.stderr,
            )
            return 2

    try:
        urls = leer_urls(config.fichero_entrada)
    except OSError as error:
        print(f"[ERROR] No se pudo leer el fichero de entrada: {error}", file=sys.stderr)
        return 2

    if not urls:
        print("[ERROR] No se encontraron URLs en el fichero de entrada.", file=sys.stderr)
        return 2

    config.carpeta_salida.mkdir(parents=True, exist_ok=True)
    config.log_fallidos.parent.mkdir(parents=True, exist_ok=True)

    print(f"URLs a procesar: {len(urls)}")
    print(f"Carpeta de salida: {config.carpeta_salida.resolve()}")
    print(f"Bitrate: {config.bitrate} kbps (fijo)")

    if config.ffmpeg_location is not None:
        print(f"ffmpeg: {config.ffmpeg_location}")
    else:
        print(
            "[AVISO] No se encontró ffmpeg (ni en el PATH ni en las ubicaciones "
            "habituales). La conversión a MP3 fallará.\n"
            "        - Si acabas de instalarlo (p. ej. con winget), reinicia la "
            "terminal para recargar el PATH.\n"
            "        - O indica su ruta con --ffmpeg C:\\ruta\\a\\ffmpeg\\bin",
            file=sys.stderr,
        )

    exitos, fallos = descargar_todas(urls, config)

    print("\n" + "=" * 60)
    print(f"Completadas: {len(exitos)}/{len(urls)}")
    if fallos:
        print(f"Fallidas:    {len(fallos)} (ver {config.log_fallidos})")
        for url in fallos:
            print(f"  - {url}")
        return 1

    print("Todas las descargas se completaron correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
