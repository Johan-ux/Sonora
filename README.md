# 🎵 Descargador de Música Personal

Descarga el **MP3 de mejor calidad** desde URLs de YouTube usando
[`yt-dlp`](https://github.com/yt-dlp/yt-dlp). Incluye una **interfaz web
moderna** con progreso en tiempo real y también una **CLI** para uso desde
terminal. El audio se convierte a MP3 a **320 kbps (bitrate fijo)** con la
**carátula** y los **metadatos** incrustados.

> ⚠️ Proyecto de uso **personal y privado**. No es comercial.

## Características

- 🌐 **Interfaz web** moderna (dark theme) con progreso en tiempo real (SSE).
- ✅ Extracción a MP3 con **bitrate fijo de 320 kbps** (configurable).
- 🖼️ Incrustación de **carátula** (thumbnail) y **metadatos** (título, artista…).
- 🔁 **Continúa** si una URL falla; las fallidas se registran en un **log**.
- 🍪 **Soporte de cookies** (fichero Netscape o exportadas del navegador) para
  evitar bloqueos de YouTube.
- 🧩 **CLI** completa con `argparse` (modo terminal).
- 📂 **Gestión de descargas**: lista y descarga los MP3 desde el navegador.

## Requisitos

- **Python 3.9+**
- **ffmpeg** instalado y disponible en el `PATH` (dependencia de sistema, **no**
  se instala con pip).

### Instalar ffmpeg

```bash
# Debian / Ubuntu
sudo apt install ffmpeg

# macOS (Homebrew)
brew install ffmpeg

# Windows (winget o Chocolatey)
winget install Gyan.FFmpeg
# choco install ffmpeg
```

> **Windows (winget):** tras instalar ffmpeg, **reinicia la terminal / VS Code**
> para que recargue el `PATH`. Si no quieres reiniciar, no pasa nada: el script
> **autodetecta** ffmpeg en la ubicación de winget. También puedes indicar su
> ruta a mano con `--ffmpeg`.

## Instalación

```bash
# 1) (Opcional pero recomendado) crear un entorno virtual
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2) Instalar las dependencias de Python
pip install -r requirements.txt
```

## Uso

### Interfaz web (recomendado)

```bash
python app.py
```

Abre [http://localhost:5000](http://localhost:5000) en tu navegador. Desde ahí puedes:

1. **Pegar URLs** de YouTube (una por línea o separadas por comas).
2. **Elegir el bitrate** (128, 192, 256 o 320 kbps).
3. **Ver el progreso** en tiempo real con barras animadas.
4. **Descargar los MP3** directamente desde la sección «Mis Descargas».

### CLI (modo terminal)

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

## Cookies (evitar bloqueos de YouTube)

Cuando se descarga desde la IP de un servidor, YouTube puede pedir verificación
(«Sign in to confirm you're not a bot»). Las cookies de una sesión autenticada
suelen resolverlo. Hay dos formas de pasarlas:

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

## Descargas fallidas

Si alguna URL falla, el proceso continúa con el resto y registra el fallo en el
log (por defecto `<salida>/descargas_fallidas.log`). Cada línea tiene el formato:

```
<timestamp ISO-8601>	<url>	<mensaje de error>
```

El programa devuelve código de salida `1` si hubo al menos un fallo, `0` si todo
fue bien, y `2` ante errores de configuración (fichero inexistente, sin URLs…).

## Aviso legal

Usa esta herramienta únicamente con contenido para el que tengas derechos o
permiso, y respeta los Términos de Servicio de YouTube y la legislación
aplicable sobre derechos de autor.
