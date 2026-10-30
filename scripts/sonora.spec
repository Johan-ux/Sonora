# -*- mode: python ; coding: utf-8 -*-
# Spec de PyInstaller para la app de escritorio "Sonora".
# Empaqueta a una carpeta (one-folder) con el nombre 'Sonora'.
# Punto de entrada: sonora/__main__.py (el mismo de 'python -m sonora').
# Construir con:  python scripts/construir.py
# (o, más cómodo, con scripts\construir_exe.bat), que antes descarga ffmpeg y
# deno a build/herramientas/ y después comprime el resultado.
#
# Notas de empaquetado:
# - El spec vive en scripts/, así que todas las rutas se calculan desde SPECPATH
#   (carpeta del spec) hacia la raíz del repositorio: funciona sea cual sea el
#   directorio desde el que se invoque a PyInstaller.
# - 'datas' incluye las carpetas 'templates' y 'static' para que Flask las
#   encuentre vía sys._MEIPASS (RUTA_RECURSOS en sonora/paths.py).
# - 'binaries' lleva ffmpeg, ffprobe y deno a 'bin' (DIR_HERRAMIENTAS en
#   sonora/paths.py): así el ejecutable funciona sin instalar nada.
# - console=False porque es una app de ventana (pywebview); no queremos consola.

import os
import re

from PyInstaller.utils.hooks import collect_submodules, copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

# Raíz del repositorio (carpeta padre de scripts/).
RAIZ = os.path.abspath(os.path.join(SPECPATH, os.pardir))

# Propiedades del .exe (las que enseñan el Explorador y el Administrador de
# tareas), con la versión de sonora/__init__.py.
with open(os.path.join(RAIZ, 'sonora', '__init__.py'), encoding='utf-8') as fichero:
    VERSION = re.search(r'^__version__ = "([^"]+)"', fichero.read(), re.M).group(1)
NUMEROS = tuple(int(n) for n in re.findall(r'\d+', VERSION)[:3])
NUMEROS += (0,) * (4 - len(NUMEROS))
PROPIEDADES = VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMEROS, prodvers=NUMEROS),
    kids=[
        # 0C0A04B0: español (alfabetización internacional), en Unicode.
        StringFileInfo([StringTable('0C0A04B0', [
            StringStruct('ProductName', 'Sonora'),
            StringStruct('FileDescription', 'Sonora'),
            StringStruct('ProductVersion', VERSION),
            StringStruct('FileVersion', VERSION),
            StringStruct('InternalName', 'Sonora'),
            StringStruct('OriginalFilename', 'Sonora.exe'),
            StringStruct('LegalCopyright', 'Copyright (c) 2026 Johan-ux. Licencia MIT.'),
        ])]),
        VarFileInfo([VarStruct('Translation', [0x0C0A, 1200])]),
    ],
)

# Programas que acompañan al ejecutable. Sin ellos saldría un .exe que solo
# funciona donde ya estén instalados: mejor no construirlo.
HERRAMIENTAS = os.path.join(RAIZ, 'build', 'herramientas')
PROGRAMAS = ('ffmpeg.exe', 'ffprobe.exe', 'deno.exe')
faltan = [p for p in PROGRAMAS if not os.path.isfile(os.path.join(HERRAMIENTAS, p))]
if faltan:
    raise SystemExit(
        f"Faltan {', '.join(faltan)} en {HERRAMIENTAS}: construye con "
        "'python scripts/construir.py', que los descarga."
    )

# Recolectar submódulos de las dependencias dinámicas para evitar fallos por
# imports que PyInstaller no detecta estáticamente.
hidden = []
hidden += collect_submodules('sonora')   # paquete propio (servicios, api, etc.)
hidden += collect_submodules('yt_dlp')
hidden += collect_submodules('mutagen')
hidden += collect_submodules('webview')
hidden += [
    'webview.platforms.edgechromium',  # backend por defecto en Windows
    'webview.platforms.winforms',
    'webview.platforms.cef',
    'flask',
    'jinja2',
    'werkzeug',
]

# Datos a incrustar: plantillas y estáticos (dentro del paquete sonora).
# Se colocan en la raíz de _MEIPASS como 'templates'/'static', que es donde los
# busca RUTA_RECURSOS de sonora.paths cuando la app está empaquetada.
datas = [
    (os.path.join(RAIZ, 'sonora', 'templates'), 'templates'),
    (os.path.join(RAIZ, 'sonora', 'static'), 'static'),
]
# La versión de yt-dlp que va dentro, para saber si la descargada es más nueva
# (sonora/actualizacion.py la lee de estos metadatos sin importar yt-dlp).
datas += copy_metadata('yt-dlp')

binaries = [(os.path.join(HERRAMIENTAS, p), 'bin') for p in PROGRAMAS]


a = Analysis(
    [os.path.join(RAIZ, 'sonora', '__main__.py')],
    # La raíz en pathex para que 'import sonora' se resuelva durante el análisis
    # aunque PyInstaller se ejecute desde otro directorio.
    pathex=[RAIZ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Sonora',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # Sin UPX aunque esté instalado: los antivirus desconfían de los binarios
    # comprimidos con él, y este .exe se reparte para abrirlo sin más.
    upx=False,
    console=False,            # app de ventana: sin consola
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # El mismo icono que usa la ventana (lo genera scripts/generar_icono.py).
    icon=os.path.join(RAIZ, 'sonora', 'static', 'img', 'sonora.ico'),
    version=PROPIEDADES,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Sonora',
)
