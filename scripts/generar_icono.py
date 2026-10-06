"""Genera el icono de la app: ``sonora/static/img/sonora.ico``.

Es el mismo dibujo que la marca de la barra lateral y el favicon de la página
(``sonora/templates/index.html``): un cuadrado negro de esquinas redondas con
cuatro barras en degradado. Dentro de la app la marca toma el color del tema
elegido; el icono de la ventana no puede cambiar con él, así que va fijo con
los colores de «ocaso», el tema por defecto.

Solo usa la biblioteca estándar, para no añadir dependencias por un fichero
que se genera una vez. Se vuelve a ejecutar si cambia el dibujo:

    python scripts/generar_icono.py
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "sonora" / "static" / "img" / "sonora.ico"

# El dibujo, en las unidades del viewBox del SVG (32 x 32).
LADO = 32.0
RADIO_FONDO = 7.0
GROSOR = 3.0
# Barras: (x, y de arriba, y de abajo), como en el <path> de la plantilla.
BARRAS = ((8.0, 12.0, 20.0), (13.0, 9.0, 23.0), (18.0, 12.0, 20.0), (23.0, 14.0, 17.0))

FONDO = (0, 0, 0)
OCASO_A = (0xFF, 0x4F, 0x9A)  # --ocaso-a en estilo.css
OCASO_B = (0xFF, 0xA0, 0x40)  # --ocaso-b

# Tamaños que pide Windows según dónde enseñe el icono y la escala de pantalla
# (16-24 en la barra de título, 32-48 en la barra de tareas, 256 en el Explorador).
TAMANOS = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _limitar(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def _distancia_fondo(x: float, y: float) -> float:
    """Distancia con signo al cuadrado redondeado (negativa por dentro)."""
    medio = LADO / 2
    qx = abs(x - medio) - (medio - RADIO_FONDO)
    qy = abs(y - medio) - (medio - RADIO_FONDO)
    fuera = math.sqrt(max(qx, 0.0) ** 2 + max(qy, 0.0) ** 2)
    return fuera + min(max(qx, qy), 0.0) - RADIO_FONDO


def _redondear(valor: float) -> int:
    """Al entero más cercano, con los medios siempre hacia arriba."""
    return int(valor + 0.5)


def _barras_en_pixeles(lado: int) -> list[tuple[float, float, float, float]]:
    """Las barras a ``lado`` píxeles: (x del eje, y del primer centro, y del último, radio).

    Los bordes se llevan a la rejilla de píxeles. Escaladas tal cual, a 16 o
    20 píxeles cada barra mide píxel y medio y cae a caballo entre dos
    columnas: salen borrosas y se funden unas con otras.
    """
    escala = lado / LADO
    ancho = max(1, _redondear(GROSOR * escala))
    paso = max(ancho + 1, _redondear((BARRAS[1][0] - BARRAS[0][0]) * escala))
    izquierda = _redondear((lado - (paso * (len(BARRAS) - 1) + ancho)) / 2)
    radio = ancho / 2
    barras = []
    for i, (_, arriba, abajo) in enumerate(BARRAS):
        primero = _redondear((arriba - GROSOR / 2) * escala) + radio
        ultimo = _redondear((abajo + GROSOR / 2) * escala) - radio
        barras.append((izquierda + i * paso + radio, primero, max(primero, ultimo), radio))
    return barras


def _distancia_barras(barras: list[tuple[float, float, float, float]], x: float, y: float) -> float:
    """Distancia con signo, en píxeles, a la barra más cercana (extremos redondos)."""
    return min(
        math.sqrt((x - eje) ** 2 + (y - _limitar(y, primero, ultimo)) ** 2) - radio
        for eje, primero, ultimo, radio in barras
    )


def _color_degradado(x: float, y: float) -> tuple[float, float, float]:
    """Color del degradado en diagonal, de la esquina de las barras a la opuesta."""
    xs = [barra[0] for barra in BARRAS]
    arriba = min(barra[1] for barra in BARRAS)
    abajo = max(barra[2] for barra in BARRAS)
    t = ((x - min(xs)) / (max(xs) - min(xs)) + (y - arriba) / (abajo - arriba)) / 2
    t = _limitar(t, 0.0, 1.0)
    return tuple(a + (b - a) * t for a, b in zip(OCASO_A, OCASO_B))


def dibujar(lado: int) -> list[list[tuple[int, int, int, int]]]:
    """Filas de píxeles (r, g, b, alfa) del icono a ``lado`` x ``lado``.

    El borde de cada forma se suaviza con su distancia al centro del píxel,
    que para figuras tan simples da el mismo resultado que sobremuestrear.
    """
    escala = lado / LADO
    barras = _barras_en_pixeles(lado)
    filas = []
    for py in range(lado):
        fila = []
        for px in range(lado):
            x = (px + 0.5) / escala
            y = (py + 0.5) / escala
            alfa = _limitar(0.5 - _distancia_fondo(x, y) * escala, 0.0, 1.0)
            barra = _limitar(0.5 - _distancia_barras(barras, px + 0.5, py + 0.5), 0.0, 1.0)
            color = _color_degradado(x, y)
            rgb = tuple(round(f + (c - f) * barra) for f, c in zip(FONDO, color))
            fila.append((*rgb, round(alfa * 255)))
        filas.append(fila)
    return filas


def _como_png(filas: list[list[tuple[int, int, int, int]]]) -> bytes:
    """Empaqueta los píxeles como PNG de 32 bits."""

    def trozo(tipo: bytes, datos: bytes) -> bytes:
        cuerpo = tipo + datos
        return struct.pack(">I", len(datos)) + cuerpo + struct.pack(">I", zlib.crc32(cuerpo))

    lado = len(filas)
    crudo = b"".join(b"\x00" + bytes(v for pixel in fila for v in pixel) for fila in filas)
    return (
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", lado, lado, 8, 6, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(crudo, 9))
        + trozo(b"IEND", b"")
    )


def _como_mapa_de_bits(filas: list[list[tuple[int, int, int, int]]]) -> bytes:
    """Empaqueta los píxeles como el mapa de bits clásico de un .ico.

    Va de abajo arriba y en BGRA, seguido de una máscara de un bit por píxel
    (1 = transparente) que Windows sigue exigiendo aunque haya canal alfa.
    """
    lado = len(filas)
    cabecera = struct.pack("<IiiHHIIiiII", 40, lado, lado * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    color = b"".join(
        bytes(v for r, g, b, a in fila for v in (b, g, r, a)) for fila in reversed(filas)
    )
    ancho_mascara = (lado + 31) // 32 * 4
    mascara = bytearray()
    for fila in reversed(filas):
        bits = bytearray(ancho_mascara)
        for i, pixel in enumerate(fila):
            if pixel[3] == 0:
                bits[i // 8] |= 0x80 >> (i % 8)
        mascara += bits
    return cabecera + color + bytes(mascara)


def construir_ico() -> bytes:
    """Contenido completo del .ico, con una imagen por tamaño."""
    imagenes = []
    for lado in TAMANOS:
        filas = dibujar(lado)
        # 256 va en PNG, como hace Windows desde Vista; el resto, sin comprimir,
        # que es lo que entiende cualquier lector de iconos.
        imagenes.append(_como_png(filas) if lado >= 256 else _como_mapa_de_bits(filas))

    salida = bytearray(struct.pack("<HHH", 0, 1, len(TAMANOS)))
    posicion = 6 + 16 * len(TAMANOS)
    for lado, imagen in zip(TAMANOS, imagenes):
        # En la entrada, 0 significa 256.
        medida = lado % 256
        salida += struct.pack("<BBBBHHII", medida, medida, 0, 0, 1, 32, len(imagen), posicion)
        posicion += len(imagen)
    for imagen in imagenes:
        salida += imagen
    return bytes(salida)


def main() -> int:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_bytes(construir_ico())
    print(f"Icono escrito en {DESTINO} ({DESTINO.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
