# Instalación

## Requisitos

- **Python 3.9+** (probado con Python 3.14 en Windows 11).
- **ffmpeg** instalado (dependencia de **sistema**, no se instala con pip).

## Instalar ffmpeg

```bash
# Windows (winget o Chocolatey)
winget install Gyan.FFmpeg
# choco install ffmpeg

# Debian / Ubuntu
sudo apt install ffmpeg

# macOS (Homebrew)
brew install ffmpeg
```

> **Windows (winget):** tras instalar ffmpeg no hace falta ni reiniciar la
> terminal: la app **autodetecta** ffmpeg (incluida la ubicación de winget) y
> reintenta la detección sola si lo instalas con la app abierta.

## Dependencias de Python

```bash
# 1) (Recomendado) crear un entorno virtual
python -m venv .venv
.venv\Scripts\activate        # Linux/macOS: source .venv/bin/activate

# 2) Instalar las dependencias
pip install -r requirements.txt
```

Dependencias principales (ver [`requirements.txt`](../requirements.txt)):
`yt-dlp`, `flask`, `mutagen` y `pywebview`.

Para ejecutar los tests hace falta además `pytest`:

```bash
pip install -r requirements-dev.txt
```

## Dónde se guardan tus datos

| Modo                | Carpeta de datos                                   |
| ------------------- | -------------------------------------------------- |
| Desarrollo          | `datos/` en la raíz del repositorio (fuera de git) |
| Ejecutable (`.exe`) | `%LOCALAPPDATA%\Sonora` en Windows                 |

En ambos casos contiene `descargas/` (los MP3) y `biblioteca.db` (cola,
historial y preferencias). Si vienes de una versión que guardaba los datos en
otro sitio (la raíz del repo, o junto al `.exe`), se migran solos en el primer
arranque.

---

Siguiente: [Uso](uso.md) · [CLI](cli.md) · [Empaquetado](empaquetado.md)
