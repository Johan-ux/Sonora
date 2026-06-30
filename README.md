# 🎵 Mi Música — Descargador, reproductor y biblioteca de escritorio

**Mi Música** es una **app de escritorio** (ventana propia, no el navegador) para
descargar música de YouTube a **MP3 de alta calidad** y reproducirla desde tu
propia biblioteca local. Combina tres cosas en una sola ventana:

- 🔎 **Buscador integrado** de YouTube (sin abrir el navegador ni iframes).
- ⬇️ **Descargador** a MP3 (320 kbps por defecto, configurable) con **carátula**
  y **metadatos** incrustados.
- 🎧 **Reproductor + biblioteca** para escuchar lo que ya tienes descargado.

Construida con **Python + Flask + pywebview** y empaquetable a un `.exe` con
**PyInstaller**.

> ⚠️ Proyecto de uso **personal y privado**. No es comercial.

---

## ✨ Funciones

- 🔎 **Buscador integrado**: busca por canción, artista o pega una URL/playlist.
  Los resultados se muestran dentro de la propia app.
- 📥 **Cola persistente**: añade canciones a una cola que **sobrevive al
  reinicio** (se guarda en SQLite). Elige la carpeta de destino y la calidad.
- 🎵 **Descarga a MP3**: bitrate configurable (128 / 192 / 256 / **320** kbps),
  con **carátula** (thumbnail) y **metadatos** (título, artista…) incrustados.
- 📚 **Biblioteca**: explora la música ya descargada; lee las etiquetas (título,
  artista, álbum, duración) directamente de los ficheros.
- ▶️ **Reproductor integrado**: barra de reproducción persistente con
  play/pausa, anterior/siguiente, barra de búsqueda (seek) y volumen.
- 🗂️ **Playlists / álbumes**: pega la URL de una playlist y añade **todo** a la
  cola de una vez.
- 🕑 **Historial** de descargas completadas.

---

## ✅ Requisitos

- **Python 3.9+** (probado con Python 3.14 en Windows 11).
- **ffmpeg** instalado (dependencia de **sistema**, no se instala con pip).

### Instalar ffmpeg

```bash
# Windows (winget o Chocolatey)
winget install Gyan.FFmpeg
# choco install ffmpeg

# Debian / Ubuntu
sudo apt install ffmpeg

# macOS (Homebrew)
brew install ffmpeg
```

> **Windows (winget):** tras instalar ffmpeg, **reinicia la terminal** para que
> recargue el `PATH`. Si no quieres reiniciar, no pasa nada: la app
> **autodetecta** ffmpeg en la ubicación de winget. La app es compatible con
> Windows, pero también puedes ejecutarla en Linux/macOS desde el código fuente.

---

## 📦 Instalación

```bash
# 1) (Recomendado) crear un entorno virtual
python -m venv .venv
.venv\Scripts\activate        # Linux/macOS: source .venv/bin/activate

# 2) Instalar las dependencias de Python
pip install -r requirements.txt
```

Dependencias principales (ver `requirements.txt`): `yt-dlp`, `flask`, `mutagen`
y `pywebview`.

---

## 🚀 Uso (desarrollo)

La forma más sencilla en Windows es ejecutar el atajo:

```bash
iniciar.bat
```

`iniciar.bat` activa el entorno virtual (`.venv`) y lanza la app. De forma
equivalente, puedes ejecutarla directamente:

```bash
python desktop.py
```

En ambos casos se abre la **ventana propia** de "🎵 Mi Música" (no el navegador).
Por dentro, la app arranca un pequeño servidor Flask en `127.0.0.1` sobre un
puerto libre y abre esa ventana con `pywebview`. Al cerrar la ventana, la app
termina por completo.

### De un vistazo

- **Buscar**: escribe y pulsa Enter (o pega una URL/playlist). Pulsa **＋** para
  añadir un resultado a la cola.
- **Cola**: elige carpeta de destino (botón explorar) y calidad, y pulsa
  **Descargar**. El progreso se actualiza en vivo.
- **Biblioteca**: pulsa el botón de play de cualquier pista para escucharla; usa
  anterior/siguiente para recorrer la lista.
- **Historial**: consulta lo descargado anteriormente.

---

## 🏗️ Empaquetado a `.exe`

Puedes generar un ejecutable de Windows con **PyInstaller** (se instala aparte;
**no** está en `requirements.txt`):

```bash
construir_exe.bat
```

`construir_exe.bat` instala PyInstaller si falta y ejecuta:

```bash
python -m PyInstaller mi_musica.spec --noconfirm
```

El resultado queda en `dist/` (por ejemplo `dist/Mi Musica/Mi Musica.exe`). Esa
carpeta es autocontenida: copia la carpeta `dist/Mi Musica/` a donde quieras y
ejecuta el `.exe`. La música descargada y la base de datos se guardan **junto al
ejecutable** (carpeta `descargas/` y fichero `biblioteca.db`).

> Recuerda que **ffmpeg sigue siendo necesario** en el sistema (o autodetectable)
> también para el ejecutable empaquetado.

---

## 🖥️ CLI (modo terminal)

El script original de línea de comandos **`descargar_musica.py` sigue disponible**
y plenamente funcional si prefieres descargar desde la terminal sin abrir la app:

1. Crea tu fichero de URLs a partir del ejemplo:

   ```bash
   cp urls.example.txt urls.txt
   ```

   Edita `urls.txt` con tus enlaces (separados por comas y/o saltos de línea).
   Las líneas que empiezan por `#` se ignoran.

2. Ejecuta el script:

   ```bash
   # Carpeta de salida por defecto: ./descargas
   python descargar_musica.py urls.txt

   # Especificando carpeta de salida
   python descargar_musica.py urls.txt -o ./mi_musica
   ```

### Opciones de la CLI

| Opción                    | Descripción                                                       | Por defecto                       |
| ------------------------- | ----------------------------------------------------------------- | --------------------------------- |
| `fichero_entrada`         | Fichero de texto con las URLs (separadas por comas).              | —                                 |
| `-o`, `--salida`          | Carpeta de salida donde se guardan los MP3.                       | `descargas`                       |
| `-b`, `--bitrate`         | Bitrate fijo del MP3 en kbps (CBR).                               | `320`                             |
| `--cookies FICHERO`       | Fichero de cookies en formato Netscape.                           | —                                 |
| `--cookies-navegador NAV` | Extrae cookies de un navegador: `chrome`, `firefox:default`, etc. | —                                 |
| `--log-fallidos FICHERO`  | Fichero donde registrar las descargas fallidas.                   | `<salida>/descargas_fallidas.log` |
| `--ffmpeg RUTA`           | Ruta al binario de ffmpeg o su carpeta (si no está en el PATH).   | autodetección                     |

Consulta la ayuda completa con:

```bash
python descargar_musica.py --help
```

---

## 🍪 Cookies (evitar bloqueos de YouTube)

Cuando se descarga desde la IP de un servidor, YouTube puede pedir verificación
(«Sign in to confirm you're not a bot»). Las cookies de una sesión autenticada
suelen resolverlo. Hay dos formas de pasarlas (desde la **CLI**):

- **Fichero de cookies (Netscape):** expórtalas con una extensión del navegador
  (p. ej. *Get cookies.txt*) y pásalo con:

  ```bash
  python descargar_musica.py urls.txt --cookies cookies.txt
  ```

- **Directamente desde el navegador** (en la misma máquina donde está instalado):

  ```bash
  python descargar_musica.py urls.txt --cookies-navegador chrome
  python descargar_musica.py urls.txt --cookies-navegador firefox:default
  ```

> ⚠️ El fichero de cookies contiene credenciales de sesión: trátalo como
> información sensible y **no lo subas al repositorio** (ya está en `.gitignore`).

---

## 📁 Estructura del proyecto

La app está organizada como un **paquete de Python** siguiendo el patrón
*application factory + blueprints* de Flask, con capas bien separadas:

```text
mi_musica/                 Paquete principal de la app de escritorio
├── factory.py             crear_app() + preparar() (ensamblaje de la app)
├── paths.py               Rutas de datos/recursos y validación anti path-traversal
├── ffmpeg.py              Localización de ffmpeg (compartida con la CLI)
├── utils.py               Utilidades varias (sin dependencias de Flask)
├── db.py                  Persistencia en SQLite (cola, historial, configuración)
├── sse.py                 Difusión de eventos en tiempo real (Server-Sent Events)
├── servicios/             Lógica de negocio
│   ├── youtube.py         Búsqueda, información y expansión de playlists (yt-dlp)
│   ├── descargas.py       Worker de descarga a MP3 + cola con progreso
│   └── biblioteca.py      Escaneo de la música descargada + tags (mutagen)
├── api/                   Blueprints HTTP (rutas de la API)
│   ├── vistas.py          /
│   ├── busqueda.py        /api/buscar, /api/info, /api/playlist
│   ├── cola.py            /api/cola*, /api/historial
│   ├── eventos.py         /api/eventos (SSE)
│   ├── biblioteca.py      /api/biblioteca, /audio, /descargas, /api/abrir-carpeta
│   ├── carpetas.py        /api/carpetas*
│   └── config.py          /api/config
├── templates/index.html   Interfaz (HTML)
└── static/css, static/js  Estilos y lógica de frontend

desktop.py                 Punto de entrada de la app de escritorio (pywebview)
descargar_musica.py        CLI independiente (importa la localización de ffmpeg)
mi_musica.spec             Configuración de PyInstaller para empaquetar
construir_exe.bat          Genera el .exe con PyInstaller
iniciar.bat                Atajo de desarrollo (activa .venv y lanza la app)
requirements.txt           Dependencias de Python
```

La música se descarga en `descargas/` y la base de datos es `biblioteca.db`,
ambas junto a la app (en desarrollo, en la raíz del proyecto; empaquetada, junto
al ejecutable).

---

## 📄 Aviso legal

Usa esta herramienta únicamente con contenido para el que tengas derechos o
permiso, y respeta los Términos de Servicio de YouTube y la legislación
aplicable sobre derechos de autor.
