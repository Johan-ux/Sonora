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
├── factory.py             crear_app() + preparar() y el guard de Host y Origin
├── paths.py               Rutas de datos/recursos y validación anti path-traversal
├── ffmpeg.py              Localización de ffmpeg (compartida con la CLI)
├── ydl_opts.py            Opciones de yt-dlp compartidas (app + CLI)
├── utils.py               Utilidades varias (sin dependencias de Flask)
├── db.py                  Persistencia en SQLite (cola, historial, configuración)
├── sse.py                 Difusión de eventos en tiempo real (Server-Sent Events)
├── salud.py               Chequeo del entorno (versión de yt-dlp, ffmpeg, runtime JS)
├── actualizacion.py       yt-dlp actualizable dentro del .exe (wheel de PyPI)
├── servicios/             Lógica de negocio
│   ├── youtube.py         Búsqueda y expansión de playlists/canales/mixes (yt-dlp)
│   ├── descargas.py       Worker de descarga + cancelación + progreso
│   ├── previa.py          Reproductor propio de la vista previa (ffmpeg al vuelo)
│   └── biblioteca.py      Escaneo de la música con caché de tags (mutagen)
├── api/                   Blueprints HTTP (rutas de la API)
│   ├── vistas.py          /
│   ├── busqueda.py        /api/buscar
│   ├── previa.py          /api/previa, /previa/<id>.mp4, /api/abrir-youtube
│   ├── cola.py            /api/cola*, /api/historial
│   ├── eventos.py         /api/eventos (SSE)
│   ├── biblioteca.py      /api/biblioteca, /audio, /api/abrir-carpeta
│   ├── carpetas.py        /api/carpetas*
│   ├── config.py          /api/config
│   └── salud.py           /api/salud, /api/salud/actualizar
├── templates/index.html   Interfaz (HTML)
└── static/css, js, img    Estilos, lógica de frontend e icono de la app

datos/                     Datos locales en desarrollo (ignorada por git)
├── descargas/             Música y vídeos descargados
├── temporal/              Trabajo de las descargas en curso (una carpeta por ítem)
├── sonora.lock            Cerrojo de instancia única
├── yt-dlp/                Solo en el .exe: el yt-dlp descargado por la app
└── biblioteca.db          SQLite: cola, historial y preferencias

docs/                      Esta documentación
ejemplos/urls.example.txt  Fichero de URLs de ejemplo para la CLI
scripts/                   iniciar.bat, construir.py (+ construir_exe.bat), sonora.spec
                           y generar_icono.py
tests/                     Suite de pytest (paths, db, utils, ydl_opts, API)
.github/workflows/ci.yml   CI: tests en Ubuntu y Windows
.github/workflows/publicar.yml  Construye el zip para Windows y lo publica en Releases
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
- **El ejecutable no depende de nada instalado.** Lleva dentro ffmpeg, ffprobe
  y deno (`_internal/bin/`, `paths.DIR_HERRAMIENTAS`), que `ffmpeg.py` y
  `ydl_opts.py` prefieren a los del sistema. yt-dlp va congelado en el binario,
  pero caduca en semanas: `actualizacion.py` baja de PyPI el *wheel* nuevo a
  la carpeta de datos y, al arrancar y antes del primer `import yt_dlp`, lo
  pone delante en `sys.path`. Un wheel es un zip de Python puro y Python
  importa desde un zip sin descomprimirlo, así que no hace falta pip ni
  reescribir el `.exe`.
- **Los datos nunca se mezclan con el código.** `paths.py` centraliza el cálculo
  de la carpeta de datos: `datos/` en desarrollo, `%LOCALAPPDATA%\Sonora` en el
  ejecutable. Además migra automáticamente los datos de ubicaciones antiguas.
- **Seguridad de rutas**: cualquier ruta que llegue por HTTP pasa por
  `resolver_dentro_descargas()`, que garantiza que no escapa de la carpeta de
  descargas (anti path-traversal). Está cubierto por tests.
- **El servidor solo escucha en `127.0.0.1`** y en un puerto libre elegido en
  cada arranque; el hilo del servidor es *daemon*, así que muere al cerrar la
  ventana. Escuchar en loopback no lo aísla del navegador, así que cada
  petición pasa dos comprobaciones: la cabecera `Host` tiene que nombrar a
  esta máquina (contra el *DNS rebinding*) y, si cambia estado, su `Origin`
  tiene que ser la propia app.
- **Una sola instancia por carpeta de datos.** Al arrancar, `escritorio.py`
  toma un cerrojo del sistema operativo sobre `sonora.lock`; si ya lo tiene
  otro proceso, trae su ventana al frente y sale sin tocar la base de datos.
  El cerrojo se suelta solo cuando el proceso muere, también si muere mal.
- **Lo que está a medias no pisa la carpeta de música.** yt-dlp baja y
  convierte en `temporal/<id del ítem>/` (opción `paths`) y solo al acabar
  mueve el resultado a `descargas/`. Sus intermedios llevan extensiones de
  música de verdad (`.f399.mp4`, `.temp.mp4`…): dentro de `descargas/`, la
  biblioteca los listaría y una cancelación los dejaría allí. Al terminar
  —bien, mal o cancelada— se borra la carpeta entera; las de ítems que
  siguen pendientes tras un cierre inesperado se conservan para reanudar.
- **La cola viaja por SSE, y los cambios de una fila viajan solos.** Altas,
  bajas y limpiezas mandan la cola entera (`cola_actualizada`); que una
  descarga empiece, termine o falle manda solo ese ítem (`item_actualizado`)
  y la interfaz sustituye esa fila. Con una playlist de mil canciones, la
  cola entera en cada cambio serían dos mil repintados de mil filas.
- **Las preferencias de la interfaz se guardan en el backend**, no en el
  `localStorage` del navegador: la ventana usa un perfil privado y el puerto
  cambia en cada arranque, así que lo que guarde la página no sobrevive al
  cierre. El volumen, el tema de color y la posición, tamaño y modo de la
  ventana de vídeo pasan por `/api/config` como el resto de la configuración.
  El tema, además, va ya puesto en el HTML que sirve `/` (`<html data-tema>`)
  para que la ventana no abra con un color y salte a otro.
- **La pantalla completa la pone la ventana, no la página.** WebView2 solo
  estira el elemento hasta el borde de la ventana; `escritorio.py` expone
  `pantalla_completa()` a la interfaz, que la llama en cada `fullscreenchange`
  para que la ventana ocupe de verdad el monitor (también con el reproductor de
  la vista previa). Al salir, pywebview deja siempre la ventana en tamaño
  normal: si estaba maximizada, el puente la restaura antes de entrar y la
  vuelve a maximizar al salir, para que quede como estaba.
- **El icono de la ventana es fijo.** Dentro de la app la marca toma el color
  del tema elegido, pero el icono de la ventana y de la barra de tareas no
  puede seguirlo: lleva siempre los colores de «ocaso», el tema por defecto.
  Es `sonora/static/img/sonora.ico`, que dibuja `scripts/generar_icono.py`
  (solo biblioteca estándar) a partir de las mismas medidas que el SVG de la
  plantilla; hay que volver a ejecutarlo si cambia el dibujo. Lanzada con
  `python -m sonora`, la app se identifica ante Windows con un nombre propio:
  sin eso la barra de tareas enseñaría el icono de Python.
- **El movimiento responde siempre a una acción.** Las animaciones son
  cortas (140–220 ms) y están juntas en la sección «Movimiento» de
  `estilo.css`: cambio de vista, diálogos, menús, el filtro desplegable y el
  cambio de tema (este con una transición de vista, porque un degradado no
  se puede animar con una transición corriente). Las listas que se repintan
  a menudo no se animan, y con «reducir movimiento» no se anima nada.

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
