# Instalación

## Requisitos

- **Python 3.9+** (probado con Python 3.14 en Windows 11).
- **ffmpeg** instalado (dependencia de **sistema**, no se instala con pip).
- **Un runtime de JavaScript** (opcional pero recomendado): ver más abajo.

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

## Runtime de JavaScript (recomendado)

YouTube protege las URLs de sus formatos con desafíos que solo se resuelven
ejecutando el JavaScript de su reproductor. Sin un runtime instalado, yt-dlp
recurre a clientes alternativos: hoy funcionan, pero es la vía que yt-dlp marca
como **deprecada** y por la que pueden faltar formatos.

Basta con tener **uno** de estos en el PATH (`deno`, `node`, `bun` o `quickjs`);
la app detecta el primero disponible y lo usa sola:

```bash
# Windows (winget)
winget install DenoLand.Deno
# o, si ya tienes Node.js, no hace falta instalar nada
```

La primera descarga baja además el script que resuelve el desafío
(`ejs`, del repositorio de yt-dlp) y lo deja cacheado.

> Si no hay ningún runtime, la app **sigue funcionando** por la vía
> alternativa: no falla, solo pierde robustez.

## Mantener yt-dlp al día

YouTube cambia con frecuencia y **una versión vieja de yt-dlp es la causa más
habitual de que las descargas fallen** (típicamente con `HTTP Error 403:
Forbidden`). Si algo deja de descargar, lo primero es actualizar:

```bash
pip install --upgrade yt-dlp
```

> Si usas el `.exe` empaquetado, yt-dlp va **congelado dentro**: actualizarlo
> exige reconstruirlo (ver [empaquetado.md](empaquetado.md)).

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

Para ejecutar los tests y el linter hacen falta además `pytest` y `ruff`:

```bash
pip install -r requirements-dev.txt

python -m pytest              # tests
python -m ruff check sonora tests   # linter
```

Ambos se ejecutan también en CI, sobre Ubuntu y Windows. Las reglas de ruff
están en [`pyproject.toml`](../pyproject.toml): se silencian a propósito las
que chocan con decisiones tomadas a conciencia en este proyecto (los `except`
amplios del worker, por ejemplo, que llevan su `# noqa` explicando el porqué).

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
