# CLI (modo terminal)

Además de la app de escritorio, Sonora incluye una **CLI** para descargar por
lotes desde la terminal: el módulo `sonora.cli`. Comparte con la app la
configuración de yt-dlp (formato, plantilla de nombres anticolisión y
postprocesadores) a través de `sonora/ydl_opts.py`, y por defecto guarda en la
**misma carpeta de descargas** que la app, así que lo descargado aparece en tu
biblioteca.

Necesita el mismo entorno que la app desde el código (ver
[instalación](instalacion.md)) y funciona igual en Windows, Linux y macOS. El
`.exe` no la incluye.

## Uso

1. Crea tu fichero de URLs a partir del ejemplo:

   ```bash
   cp ejemplos/urls.example.txt urls.txt     # Windows: copy ejemplos\urls.example.txt urls.txt
   ```

   Edita `urls.txt` con tus enlaces (separados por comas y/o saltos de línea).
   Las líneas que empiezan por `#` se ignoran. `urls.txt` está en `.gitignore`.

2. Ejecuta la CLI desde la raíz del repositorio, con el entorno virtual activado:

   ```bash
   # Carpeta de salida por defecto: la de descargas de Sonora
   python -m sonora.cli urls.txt

   # Especificando carpeta de salida
   python -m sonora.cli urls.txt -o ./mi_carpeta
   ```

## Opciones

| Opción                    | Descripción                                                       | Por defecto                       |
| ------------------------- | ----------------------------------------------------------------- | --------------------------------- |
| `fichero_entrada`         | Fichero de texto con las URLs (separadas por comas).              | —                                 |
| `-o`, `--salida`          | Carpeta de salida donde se guardan los MP3.                       | carpeta de descargas de Sonora    |
| `-b`, `--bitrate`         | Bitrate fijo del MP3 en kbps (CBR).                               | `320`                             |
| `--cookies FICHERO`       | Fichero de cookies en formato Netscape.                           | —                                 |
| `--cookies-navegador NAV` | Extrae cookies de un navegador: `chrome`, `firefox:default`, etc. | —                                 |
| `--log-fallidos FICHERO`  | Fichero donde registrar las descargas fallidas.                   | `<salida>/descargas_fallidas.log` |
| `--ffmpeg RUTA`           | Ruta al binario de ffmpeg o su carpeta (si no está en el PATH).   | autodetección                     |

Consulta la ayuda completa con:

```bash
python -m sonora.cli --help
```

Códigos de salida: `0` todo correcto, `1` alguna descarga falló (ver el log de
fallidos), `2` error de configuración (fichero inexistente, sin URLs, etc.).

## Cookies (evitar bloqueos de YouTube)

Cuando se descarga desde la IP de un servidor, YouTube puede pedir verificación
(«Sign in to confirm you're not a bot»). Las cookies de una sesión autenticada
suelen resolverlo. Hay dos formas de pasarlas:

- **Fichero de cookies (Netscape):** expórtalas con una extensión del navegador
  (p. ej. *Get cookies.txt*) y pásalo con:

  ```bash
  python -m sonora.cli urls.txt --cookies cookies.txt
  ```

- **Directamente desde el navegador** (en la misma máquina donde está instalado):

  ```bash
  python -m sonora.cli urls.txt --cookies-navegador chrome
  python -m sonora.cli urls.txt --cookies-navegador firefox:default
  ```

> ⚠️ El fichero de cookies contiene credenciales de sesión: trátalo como
> información sensible y **no lo subas al repositorio** (ya está en
> `.gitignore`).

---

Siguiente: [Empaquetado](empaquetado.md) · [Arquitectura](arquitectura.md)
