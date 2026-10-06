# -*- mode: python ; coding: utf-8 -*-
# Spec de PyInstaller para la app de escritorio "Sonora".
# Empaqueta a una carpeta (one-folder) con el nombre 'Sonora'.
# Punto de entrada: sonora/__main__.py (el mismo de 'python -m sonora').
# Construir con:  python -m PyInstaller scripts/sonora.spec --noconfirm
# (o, más cómodo, con scripts\construir_exe.bat)
#
# Notas de empaquetado:
# - El spec vive en scripts/, así que todas las rutas se calculan desde SPECPATH
#   (carpeta del spec) hacia la raíz del repositorio: funciona sea cual sea el
#   directorio desde el que se invoque a PyInstaller.
# - 'datas' incluye las carpetas 'templates' y 'static' para que Flask las
#   encuentre vía sys._MEIPASS (RUTA_RECURSOS en sonora/paths.py).
# - console=False porque es una app de ventana (pywebview); no queremos consola.

import os

from PyInstaller.utils.hooks import collect_submodules

# Raíz del repositorio (carpeta padre de scripts/).
RAIZ = os.path.abspath(os.path.join(SPECPATH, os.pardir))

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


a = Analysis(
    [os.path.join(RAIZ, 'sonora', '__main__.py')],
    # La raíz en pathex para que 'import sonora' se resuelva durante el análisis
    # aunque PyInstaller se ejecute desde otro directorio.
    pathex=[RAIZ],
    binaries=[],
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
    upx=True,
    console=False,            # app de ventana: sin consola
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # El mismo icono que usa la ventana (lo genera scripts/generar_icono.py).
    icon=os.path.join(RAIZ, 'sonora', 'static', 'img', 'sonora.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Sonora',
)
