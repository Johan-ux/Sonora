"""Punto de entrada ejecutable del paquete: ``python -m sonora``.

Es además el script que PyInstaller empaqueta (ver ``scripts/sonora.spec``).
Usa import absoluto a propósito: al ejecutarse como ``__main__`` (empaquetado)
no hay contexto de paquete y un import relativo fallaría.
"""

import sys

from sonora.escritorio import main

if __name__ == "__main__":
    sys.exit(main())
