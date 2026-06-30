"""Utilidades varias, sin dependencias de Flask."""

from __future__ import annotations

from datetime import datetime, timezone


def ahora_iso() -> str:
    """Marca de tiempo local en formato ISO-8601 (con precisión de segundos)."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def formatear_duracion(segundos) -> str:
    """Formatea una duración en segundos como ``"M:SS"`` (o ``"H:MM:SS"``).

    Devuelve cadena vacía si la duración es desconocida o no numérica.
    """
    try:
        total = int(float(segundos))
    except (TypeError, ValueError):
        return ""
    if total < 0:
        return ""
    horas, resto = divmod(total, 3600)
    minutos, segs = divmod(resto, 60)
    if horas:
        return f"{horas}:{minutos:02d}:{segs:02d}"
    return f"{minutos}:{segs:02d}"


def colapsar_error(mensaje) -> str:
    """Colapsa saltos de línea y espacios de un mensaje de error (máx. 500)."""
    return " ".join(str(mensaje).split())[:500]


def thumbnail_desde_id(video_id: str) -> str:
    """Construye una URL de miniatura de YouTube a partir del id de vídeo."""
    if not video_id:
        return ""
    return f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
