# Empaquetado a `.exe`

Puedes generar un ejecutable de Windows con **PyInstaller** (se instala aparte;
**no** está en `requirements.txt`):

```bash
scripts\construir_exe.bat
```

`construir_exe.bat` se sitúa en la raíz del repositorio, instala PyInstaller si
falta y ejecuta:

```bash
python -m PyInstaller scripts/sonora.spec --noconfirm
```

El resultado queda en `dist/` (por ejemplo `dist/Sonora/Sonora.exe`). Esa
carpeta es autocontenida: cópiala donde quieras y ejecuta el `.exe`. Las
carpetas `build/` y `dist/` son artefactos regenerables y están ignoradas por
git: puedes borrarlas cuando quieras.

## Cómo está configurado el spec

[`scripts/sonora.spec`](../scripts/sonora.spec):

- **Punto de entrada**: `sonora/__main__.py`, el mismo de `python -m sonora`.
- **Rutas**: se calculan desde `SPECPATH` hacia la raíz del repositorio, así que
  PyInstaller funciona se invoque desde donde se invoque.
- **`datas`**: incrusta `sonora/templates` y `sonora/static` en la raíz de
  `_MEIPASS`, que es donde los busca `RUTA_RECURSOS` de `sonora/paths.py`.
- **`hiddenimports`**: submódulos de `sonora`, `yt_dlp`, `mutagen` y `webview`
  (más los backends de pywebview en Windows), que PyInstaller no detecta
  estáticamente.
- **`console=False`**: es una app de ventana; no queremos consola detrás.

## Datos de usuario

Empaquetada, la música y la base de datos se guardan en `%LOCALAPPDATA%\Sonora`
(carpeta `descargas/` y fichero `biblioteca.db`), de modo que la app funciona
aunque el `.exe` viva en una ruta sin permisos de escritura (p. ej.
`Program Files`). Si vienes de una versión antigua que guardaba los datos junto
al `.exe`, se migran automáticamente al primer arranque.

> Recuerda que **ffmpeg sigue siendo necesario** en el sistema (o
> autodetectable) también para el ejecutable empaquetado.

---

Siguiente: [Arquitectura](arquitectura.md)
