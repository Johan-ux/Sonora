# Empaquetado para Windows

El objetivo es que cualquiera use Sonora **sin instalar nada**: ni Python, ni
ffmpeg, ni un runtime de JavaScript. Se reparte una carpeta con `Sonora.exe` y
todo lo que necesita, comprimida en un zip.

## Construir

```bash
scripts\construir_exe.bat        # o: python scripts/construir.py
```

`construir_exe.bat` se sitúa en la raíz del repositorio, instala PyInstaller si
falta y ejecuta [`scripts/construir.py`](../scripts/construir.py), que:

1. **Descarga ffmpeg, ffprobe y deno** en versiones fijas y comprueba su huella
   SHA-256 antes de usarlos. Lo descargado se guarda en `build/descargas/` y no
   se vuelve a bajar; los ejecutables quedan en `build/herramientas/`.
2. **Ejecuta PyInstaller** con [`scripts/sonora.spec`](../scripts/sonora.spec).
3. **Añade las licencias** de todo lo que va dentro en `dist/Sonora/licencias/`
   (ver más abajo).
4. **Comprime** la carpeta en `dist/Sonora-windows-x64.zip`.

| Resultado                    | Qué es                                       |
| ---------------------------- | -------------------------------------------- |
| `dist/Sonora/Sonora.exe`     | La app, lista para abrir                     |
| `dist/Sonora-windows-x64.zip` | Lo que se reparte (unos 145 MB; 330 MB al descomprimir) |

Las carpetas `build/` y `dist/` son regenerables y están ignoradas por git.

### Versiones incluidas

| Programa         | Versión | Origen                                                       |
| ---------------- | ------- | ------------------------------------------------------------ |
| ffmpeg + ffprobe | 9.0.2   | Compilación *essentials* de gyan.dev (GitHub `GyanD/codexffmpeg`) |
| deno             | 2.9.8   | GitHub `denoland/deno`                                       |

Para cambiar de versión se tocan la URL y la huella en `DESCARGAS`
(`scripts/construir.py`); GitHub publica la huella junto a cada fichero.

## Publicar una versión

[`.github/workflows/publicar.yml`](../.github/workflows/publicar.yml) construye
el zip en Windows y lo sube a **Releases** al empujar una etiqueta `v…`:

```bash
git tag v1.0.0
git push origin v1.0.0
```

También se puede lanzar a mano desde la pestaña *Actions* (*Run workflow*): en
ese caso el zip queda como artefacto de la ejecución, sin crear release.

## Cómo está configurado el spec

- **Punto de entrada**: `sonora/__main__.py`, el mismo de `python -m sonora`.
- **Rutas**: se calculan desde `SPECPATH` hacia la raíz del repositorio, así que
  PyInstaller funciona se invoque desde donde se invoque.
- **`datas`**: incrusta `sonora/templates` y `sonora/static` en la raíz de
  `_MEIPASS`, que es donde los busca `RUTA_RECURSOS` de `sonora/paths.py`, y
  los metadatos de yt-dlp (para saber qué versión lleva dentro).
- **`binaries`**: ffmpeg, ffprobe y deno van a `_internal/bin/`
  (`DIR_HERRAMIENTAS` en `sonora/paths.py`). Si faltan, el spec se niega a
  construir: un `.exe` sin ellos solo funcionaría donde ya estén instalados.
- **`hiddenimports`**: submódulos de `sonora`, `yt_dlp`, `mutagen` y `webview`
  (más los backends de pywebview en Windows), que PyInstaller no detecta
  estáticamente.
- **`console=False`**: es una app de ventana; no queremos consola detrás.
- **`upx=False`**: los antivirus desconfían de los binarios comprimidos con UPX.
- **`icon`**: el `.exe` lleva el mismo icono que la ventana,
  `sonora/static/img/sonora.ico` (lo genera `scripts/generar_icono.py`).

## yt-dlp dentro del ejecutable

yt-dlp va congelado dentro del `.exe`, y YouTube cambia tan a menudo que en
unas semanas deja de descargar. Por eso la app empaquetada también se
actualiza: el botón **Actualizar ahora** baja de PyPI el *wheel* de la última
versión, comprueba su huella SHA-256 y lo guarda en
`%LOCALAPPDATA%\Sonora\yt-dlp\`. Al reiniciar, `sonora/actualizacion.py` lo pone
delante en `sys.path` antes de que nada importe yt-dlp. Si más adelante se
instala un Sonora que trae una versión igual o más nueva, el wheel descargado
se borra solo.

## Requisitos del equipo

Windows 10 u 11 de 64 bits. La ventana usa **WebView2**, que viene con Windows
11 y con las versiones al día de Windows 10.

El `.exe` no está firmado, así que la primera vez Windows puede enseñar
«Windows protegió su PC»: **Más información → Ejecutar de todas formas**.

## Licencias

Repartir el ejecutable es repartir también lo que lleva dentro, y dos de esas
piezas son GPL: **FFmpeg** (GPL v3 en la compilación *essentials*) y
**mutagen** (GPL v2 o posterior). La GPL obliga a acompañarlas de su licencia
y a decir dónde conseguir su código, así que `construir.py` crea
`dist/Sonora/licencias/` con:

- `LEEME.txt`: qué lleva el programa, con qué licencia y dónde está el código.
- La licencia de Sonora (MIT), la de Python y las de ffmpeg y deno.
- `python/`: los textos de licencia de cada paquete de Python incluido.

## Datos de usuario

Empaquetada, la música y la base de datos se guardan en `%LOCALAPPDATA%\Sonora`
(carpeta `descargas/` y fichero `biblioteca.db`), de modo que la app funciona
aunque el `.exe` viva en una ruta sin permisos de escritura (p. ej.
`Program Files`). Si vienes de una versión antigua que guardaba los datos junto
al `.exe`, se migran automáticamente al primer arranque.

---

Siguiente: [Arquitectura](arquitectura.md)
