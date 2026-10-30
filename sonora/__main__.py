"""Punto de entrada ejecutable del paquete: ``python -m sonora``.

Es además el script que PyInstaller empaqueta (ver ``scripts/sonora.spec``).
Usa import absoluto a propósito: al ejecutarse como ``__main__`` (empaquetado)
no hay contexto de paquete y un import relativo fallaría.
"""

import sys

from sonora import actualizacion

if __name__ == "__main__":
    # El yt-dlp que la app empaquetada descargó tiene que ir delante en
    # sys.path antes del primer 'import yt_dlp', y escritorio lo arrastra todo.
    actualizacion.activar()

    from sonora.escritorio import main

    sys.exit(main())
