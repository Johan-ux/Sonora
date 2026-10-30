"""Paquete de la app de escritorio «Sonora».

Arquitectura: *application factory + blueprints* de Flask, con capas claras:

    __init__.py        Este módulo: solo la versión (no importa nada a propósito).
    factory.py         crear_app() y preparar() (punto de ensamblaje).
    paths.py           Rutas de datos/recursos y validación anti path-traversal.
    ffmpeg.py          Localización de ffmpeg (compartida con la CLI).
    utils.py           Utilidades varias (sin dependencias de Flask).
    db.py              Persistencia en SQLite.
    sse.py             Difusión de eventos en tiempo real (Server-Sent Events).
    servicios/         Lógica de negocio: youtube, descargas, biblioteca.
    api/               Blueprints HTTP (todas las rutas de la API).
    templates/, static/  Interfaz (HTML, CSS, JS).

El ``__init__`` no importa nada a propósito: así, importar una utilidad suelta
(p. ej. ``sonora.ffmpeg`` desde la CLI) no arrastra Flask ni el resto de la app.
Para obtener la aplicación, importa ``crear_app`` de ``sonora.factory``.
"""

# La versión de la app, en un solo sitio. La etiqueta de cada release es «v» +
# esto (lo comprueba .github/workflows/publicar.yml) y va en las propiedades
# del .exe (scripts/sonora.spec) y en la vista de Configuración.
__version__ = "1.0.0"
