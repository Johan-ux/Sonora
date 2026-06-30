# -*- mode: python ; coding: utf-8 -*-
# Spec de PyInstaller para la app de escritorio "Mi Música".
# Empaqueta a una carpeta (one-folder) con el nombre 'Mi Musica'.
# Punto de entrada: desktop.py
# Construir con:  python -m PyInstaller mi_musica.spec --noconfirm
#
# Notas de empaquetado:
# - 'datas' incluye las carpetas 'templates' y 'static' para que Flask las
#   encuentre vía sys._MEIPASS (RUTA_RECURSOS en app.py).
# - console=False porque es una app de ventana (pywebview); no queremos consola.

from PyInstaller.utils.hooks import collect_submodules

# Recolectar submódulos de las dependencias dinámicas para evitar fallos por
# imports que PyInstaller no detecta estáticamente.
hidden = []
hidden += collect_submodules('mi_musica')   # paquete propio (servicios, api, etc.)
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

# Datos a incrustar: plantillas y estáticos (ahora dentro del paquete mi_musica).
# Se colocan en la raíz de _MEIPASS como 'templates'/'static', que es donde los
# busca RUTA_RECURSOS de mi_musica.paths cuando la app está empaquetada.
datas = [
    ('mi_musica/templates', 'templates'),
    ('mi_musica/static', 'static'),
]


a = Analysis(
    ['desktop.py'],
    pathex=[],
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
    name='Mi Musica',
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
    # icon='icono.ico',       # opcional: descomenta si añades un icono
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Mi Musica',
)
