# Arquitectura y estructura del proyecto

La app está organizada como un **paquete de Python** siguiendo el patrón
*application factory + blueprints* de Flask, con capas bien separadas: rutas
HTTP (`api/`) → lógica de negocio (`servicios/`) → persistencia (`db.py`).

## Estructura

```text
sonora/                    Paquete principal (app de escritorio + CLI)
├── __main__.py            Punto de entrada: python -m sonora (y del .exe)
├── escritorio.py          Servidor Flask en hilo daemon + ventana pywebview
├── cli.py                 CLI de descarga por lotes (python -m sonora.cli)
├── factory.py             crear_app() + preparar() y el guard de Origin
├── paths.py               Rutas de datos/recursos y validación anti path-traversal
├── ffmpeg.py              Localización de ffmpeg (compartida con la CLI)
├── ydl_opts.py            Opciones de yt-dlp compartidas (app + CLI)
├── utils.py               Utilidades varias (sin dependencias de Flask)
├── db.py                  Persistencia en SQLite (cola, historial, configuración)
├── sse.py                 Difusión de eventos en tiempo real (Server-Sent Events)
├── salud.py               Chequeo del entorno (versión de yt-dlp, ffmpeg, runtime JS)
├── servicios/             Lógica de negocio
│   ├── youtube.py         Búsqueda y expansión de playlists/canales/mixes (yt-dlp)
│   ├── descargas.py       Worker de descarga + cancelación + progreso
│   └── biblioteca.py      Escaneo de la música con caché de tags (mutagen)
├── api/                   Blueprints HTTP (rutas de la API)
│   ├── vistas.py          /
│   ├── busqueda.py        /api/buscar
│   ├── cola.py            /api/cola*, /api/historial
│   ├── eventos.py         /api/eventos (SSE)
│   ├── biblioteca.py      /api/biblioteca, /audio, /api/abrir-carpeta
│   ├── carpetas.py        /api/carpetas*
│   ├── config.py          /api/config
│   └── salud.py           /api/salud, /api/salud/actualizar
├── templates/index.html   Interfaz (HTML)
└── static/css, static/js  Estilos y lógica de frontend

datos/                     Datos locales en desarrollo (ignorada por git)
├── descargas/             MP3 descargados
└── biblioteca.db          SQLite: cola, historial y preferencias

docs/                      Esta documentación
ejemplos/urls.example.txt  Fichero de URLs de ejemplo para la CLI
scripts/                   iniciar.bat, construir_exe.bat y sonora.spec
tests/                     Suite de pytest (paths, db, utils, ydl_opts, API)
.github/workflows/ci.yml   CI: tests en Ubuntu y Windows
pyproject.toml             Configuración de herramientas (pytest)
requirements.txt           Dependencias de la app
requirements-dev.txt       Dependencias de desarrollo (pytest)
```

## Decisiones de diseño

- **Todo el código vive en el paquete `sonora`.** Los dos puntos de entrada
  (app de escritorio y CLI) son módulos del paquete, no scripts sueltos en la
  raíz: se invocan con `python -m sonora` y `python -m sonora.cli`, y comparten
  sin duplicación la localización de ffmpeg (`ffmpeg.py`) y las opciones de
  yt-dlp (`ydl_opts.py`).
- **Los datos nunca se mezclan con el código.** `paths.py` centraliza el cálculo
  de la carpeta de datos: `datos/` en desarrollo, `%LOCALAPPDATA%\Sonora` en el
  ejecutable. Además migra automáticamente los datos de ubicaciones antiguas.
- **Seguridad de rutas**: cualquier ruta que llegue por HTTP pasa por
  `resolver_dentro_descargas()`, que garantiza que no escapa de la carpeta de
  descargas (anti path-traversal). Está cubierto por tests.
- **El servidor solo escucha en `127.0.0.1`** y en un puerto libre elegido en
  cada arranque; el hilo del servidor es *daemon*, así que muere al cerrar la
  ventana.
- **Las preferencias de la interfaz se guardan en el backend**, no en el
  `localStorage` del navegador: la ventana usa un perfil privado y el puerto
  cambia en cada arranque, así que lo que guarde la página no sobrevive al
  cierre. El volumen y la posición, tamaño y modo de la ventana de vídeo pasan
  por `/api/config` como el resto de la configuración.
- **La pantalla completa la pone la ventana, no la página.** WebView2 solo
  estira el elemento hasta el borde de la ventana; `escritorio.py` expone
  `pantalla_completa()` a la interfaz, que la llama en cada `fullscreenchange`
  para que la ventana ocupe de verdad el monitor (también con el reproductor de
  la vista previa).

## Tests y CI

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

La suite cubre la validación anti path-traversal, la capa SQLite (incluido el
reclamo atómico de ítems del worker), los helpers y el contrato de la API HTTP
(sin tocar la red). Los tests no arrancan nunca el worker de descargas ni salen
a internet, y usan una BD temporal por test.

En GitHub, [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) ejecuta los
tests en Ubuntu y Windows con cada push.
