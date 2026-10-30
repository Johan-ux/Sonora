"""Notas de una versión para su release de GitHub, sacadas de CHANGELOG.md.

    python scripts/notas_version.py 1.0.0 > notas.md

Toma la sección ``## [1.0.0]`` hasta la siguiente (o hasta los enlaces del
final) y une las líneas que el changelog parte a 80 columnas: en una release,
GitHub muestra cada salto de línea como un salto de verdad, y las frases
saldrían cortadas por la mitad. Sale con código 1 si no encuentra la sección.
Lo usa ``.github/workflows/publicar.yml``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"

# Líneas que abren un bloque nuevo de Markdown: nunca continúan la anterior.
INICIO_DE_BLOQUE = re.compile(r"\s*(#|>|\||```|[-*+]\s|\d+\.\s)")
DEFINICION_DE_ENLACE = re.compile(r"\[[^\]]+\]: ")


def seccion(texto: str, version: str) -> list[str]:
    """Las líneas de la sección de ``version``, sin su título."""
    lineas = texto.splitlines()
    titulo = f"## [{version}]"
    inicio = next((i for i, linea in enumerate(lineas) if linea.startswith(titulo)), None)
    if inicio is None:
        return []
    fin = next(
        (
            i
            for i in range(inicio + 1, len(lineas))
            if lineas[i].startswith("## [") or DEFINICION_DE_ENLACE.match(lineas[i])
        ),
        len(lineas),
    )
    return lineas[inicio + 1 : fin]


def unir(lineas: list[str]) -> str:
    """Une cada línea partida a la anterior; respeta títulos, listas y código."""
    salida: list[str] = []
    en_codigo = False
    for linea in lineas:
        if linea.lstrip().startswith("```"):
            en_codigo = not en_codigo
            salida.append(linea)
            continue
        anterior = salida[-1] if salida else ""
        continua = (
            not en_codigo
            and anterior.strip()
            and linea.strip()
            and not INICIO_DE_BLOQUE.match(linea)
            and not anterior.lstrip().startswith(("#", "```"))
        )
        if continua:
            salida[-1] = anterior.rstrip() + " " + linea.strip()
        else:
            salida.append(linea)
    return "\n".join(salida).strip("\n")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Uso: python scripts/notas_version.py <versión>", file=sys.stderr)
        return 2
    lineas = seccion(CHANGELOG.read_text(encoding="utf-8"), argv[1])
    if not any(linea.strip() for linea in lineas):
        print(f"CHANGELOG.md no tiene la sección [{argv[1]}].", file=sys.stderr)
        return 1
    # En Windows, la salida redirigida a un fichero no es UTF-8 por defecto.
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    print(unir(lineas))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
