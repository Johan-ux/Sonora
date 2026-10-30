"""Construye Sonora para Windows: una carpeta que se abre sin instalar nada.

    python scripts/construir.py

Pasos:

1. Descarga ffmpeg, ffprobe y deno en versiones fijas, comprueba su huella
   SHA-256 y deja los ejecutables en ``build/herramientas/`` (lo descargado se
   guarda en ``build/descargas/`` y no se vuelve a bajar).
2. Ejecuta PyInstaller con ``scripts/sonora.spec``, que mete esos programas en
   el ejecutable. Resultado: ``dist/Sonora/Sonora.exe``.
3. Añade ``dist/Sonora/licencias/`` con la licencia de Sonora y las de todo lo
   que va dentro. Repartir ffmpeg y mutagen (GPL) obliga a acompañarlos de su
   licencia y de dónde conseguir su código.
4. Comprime la carpeta en ``dist/Sonora-windows-x64.zip``: es lo que se reparte.

Para cambiar de versión de ffmpeg o deno se tocan la URL y la huella en
``DESCARGAS`` (las huellas las publica GitHub junto a cada fichero).
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

RAIZ = Path(__file__).resolve().parent.parent
BUILD = RAIZ / "build"
DIST = RAIZ / "dist"
SPEC = RAIZ / "scripts" / "sonora.spec"
NOMBRE_ZIP = "Sonora-windows-x64"
REPOSITORIO = "https://github.com/Johan-ux/Sonora"

VERSION_FFMPEG = "9.0.2"
VERSION_DENO = "2.9.8"
_FFMPEG = f"ffmpeg-{VERSION_FFMPEG}-essentials_build"


@dataclass(frozen=True)
class Descarga:
    url: str
    sha256: str
    # Qué sacar del zip y adónde, relativo a build/. Si lo descargado no es un
    # zip, la clave vacía representa el propio fichero.
    extraer: dict[str, str]


DESCARGAS = (
    Descarga(
        url=(
            "https://github.com/GyanD/codexffmpeg/releases/download/"
            f"{VERSION_FFMPEG}/{_FFMPEG}.zip"
        ),
        sha256="60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba",
        extraer={
            f"{_FFMPEG}/bin/ffmpeg.exe": "herramientas/ffmpeg.exe",
            f"{_FFMPEG}/bin/ffprobe.exe": "herramientas/ffprobe.exe",
            f"{_FFMPEG}/LICENSE": "licencias/ffmpeg/LICENSE.txt",
            # Dice con qué código y qué bibliotecas se compiló.
            f"{_FFMPEG}/README.txt": "licencias/ffmpeg/README.txt",
        },
    ),
    Descarga(
        url=(
            f"https://github.com/denoland/deno/releases/download/v{VERSION_DENO}/"
            "deno-x86_64-pc-windows-msvc.zip"
        ),
        sha256="cba84b26e0df5ae7f74fc66b86a95b866872a86292ebd84fa1e959927edd93bf",
        extraer={"deno.exe": "herramientas/deno.exe"},
    ),
    Descarga(
        url=f"https://raw.githubusercontent.com/denoland/deno/v{VERSION_DENO}/LICENSE.md",
        sha256="f62497fffecc0852960c8d3e6934b9db86d16396e9b604072e923892cae3a588",
        extraer={"": "licencias/deno/LICENSE.md"},
    ),
)

# Nombres con los que los paquetes de Python publican sus licencias.
PREFIJOS_LICENCIA = ("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS")


def _huella(ruta: Path) -> str:
    sha = hashlib.sha256()
    with open(ruta, "rb") as fichero:
        while bloque := fichero.read(1024 * 1024):
            sha.update(bloque)
    return sha.hexdigest()


def _descargar(descarga: Descarga) -> Path:
    """Devuelve el fichero descargado y verificado (de la caché si ya está)."""
    destino = BUILD / "descargas" / descarga.url.rsplit("/", 1)[-1]
    if destino.is_file() and _huella(destino) == descarga.sha256:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    print(f"Descargando {descarga.url}")
    parcial = destino.with_name(destino.name + ".part")
    peticion = urllib.request.Request(descarga.url, headers={"User-Agent": "Sonora"})
    with urllib.request.urlopen(peticion, timeout=120) as respuesta, open(parcial, "wb") as f:
        shutil.copyfileobj(respuesta, f, 1024 * 1024)
    huella = _huella(parcial)
    if huella != descarga.sha256:
        parcial.unlink()
        raise SystemExit(
            f"La huella de {descarga.url} no coincide:\n"
            f"  esperada {descarga.sha256}\n  obtenida {huella}"
        )
    parcial.replace(destino)
    return destino


def preparar_herramientas() -> None:
    for descarga in DESCARGAS:
        fichero = _descargar(descarga)
        for miembro, relativo in descarga.extraer.items():
            destino = BUILD / relativo
            destino.parent.mkdir(parents=True, exist_ok=True)
            if not miembro:
                shutil.copyfile(fichero, destino)
                continue
            with zipfile.ZipFile(fichero) as zip_, zip_.open(miembro) as origen, \
                    open(destino, "wb") as salida:
                shutil.copyfileobj(origen, salida, 1024 * 1024)


def _dependencias() -> list[importlib.metadata.Distribution]:
    """Los paquetes de requirements.txt y todo lo que arrastran."""
    pendientes = []
    for linea in (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines():
        linea = linea.split("#", 1)[0].strip()
        if linea:
            pendientes.append(Requirement(linea).name)
    vistos: dict[str, importlib.metadata.Distribution] = {}
    while pendientes:
        nombre = canonicalize_name(pendientes.pop())
        if nombre in vistos:
            continue
        try:
            dist = importlib.metadata.distribution(nombre)
        except importlib.metadata.PackageNotFoundError:
            continue
        vistos[nombre] = dist
        for requisito in dist.requires or []:
            req = Requirement(requisito)
            # Solo lo que se instala sin extras en esta plataforma.
            if req.marker is None or req.marker.evaluate({"extra": ""}):
                pendientes.append(req.name)
    return sorted(vistos.values(), key=lambda d: d.metadata["Name"].lower())


def _licencia_declarada(dist: importlib.metadata.Distribution) -> str:
    meta = dist.metadata
    expresion = meta.get("License-Expression")
    if expresion:
        return expresion
    clasificadores = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    if clasificadores:
        return ", ".join(clasificadores)
    # El campo License a veces trae el texto entero: basta su primera línea.
    return (meta.get("License") or "ver licencia").strip().splitlines()[0]


def escribir_licencias(destino: Path) -> None:
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(BUILD / "licencias", destino)
    shutil.copyfile(RAIZ / "LICENSE", destino / "Sonora-LICENSE.txt")
    licencia_python = Path(sys.base_prefix) / "LICENSE.txt"
    if licencia_python.is_file():
        shutil.copyfile(licencia_python, destino / "Python-LICENSE.txt")

    lineas = []
    for dist in _dependencias():
        nombre, version = dist.metadata["Name"], dist.version
        lineas.append(f"      - {nombre} {version}: {_licencia_declarada(dist)}")
        carpeta = destino / "python" / nombre
        for fichero in dist.files or []:
            ruta = Path(str(fichero))
            en_dist_info = ruta.parts and ruta.parts[0].endswith(".dist-info")
            if en_dist_info and ruta.name.upper().startswith(PREFIJOS_LICENCIA):
                carpeta.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(dist.locate_file(fichero), carpeta / ruta.name)

    version_python = ".".join(map(str, sys.version_info[:3]))
    (destino / "LEEME.txt").write_text(
        "Sonora se distribuye bajo licencia MIT (Sonora-LICENSE.txt).\n"
        f"Código fuente: {REPOSITORIO}\n"
        "\n"
        "Este programa incluye software de terceros, cada uno con su licencia:\n"
        "\n"
        f"  - Python {version_python}: PSF License (Python-LICENSE.txt)\n"
        f"  - FFmpeg {VERSION_FFMPEG}, compilación «essentials» de gyan.dev: GPL v3\n"
        "    (ffmpeg/). Código fuente: https://ffmpeg.org/download.html y\n"
        "    https://github.com/FFmpeg/FFmpeg; ffmpeg/README.txt detalla la\n"
        "    compilación y las bibliotecas que lleva.\n"
        f"  - Deno {VERSION_DENO}: MIT (deno/). Código fuente:\n"
        "    https://github.com/denoland/deno\n"
        "  - Paquetes de Python (textos en python/; código fuente en https://pypi.org):\n"
        + "\n".join(lineas)
        + "\n\n"
        "FFmpeg y mutagen son software libre bajo la GPL: puedes redistribuirlos y\n"
        "modificarlos según sus términos, y obtener su código fuente en las\n"
        "direcciones indicadas.\n",
        encoding="utf-8",
    )


def main() -> int:
    preparar_herramientas()
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm", "--clean"],
        cwd=RAIZ,
        check=True,
    )
    carpeta = DIST / "Sonora"
    escribir_licencias(carpeta / "licencias")
    print("Comprimiendo...")
    archivo = shutil.make_archive(str(DIST / NOMBRE_ZIP), "zip", root_dir=DIST, base_dir="Sonora")
    print(f"\nListo:\n  {carpeta / 'Sonora.exe'}\n  {archivo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
