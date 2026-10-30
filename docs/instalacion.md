# Instalación

> **¿Solo quieres usar Sonora en Windows?** No hace falta instalar nada:
> descarga `Sonora-windows-x64.zip` de la página de *Releases* del repositorio,
> descomprímelo y abre `Sonora\Sonora.exe`. Esta guía es para ejecutarla desde
> el código fuente.

## Requisitos

- **Python 3.11 o posterior**: es la mínima que admiten yt-dlp y pythonnet. La
  CI prueba la 3.11 y la 3.14 (la que lleva el `.exe`).
- **ffmpeg** instalado (dependencia de **sistema**, no se instala con pip).
- **Un runtime de JavaScript** (opcional pero recomendado): ver más abajo.

## La forma rápida

Con Python instalado, el script de tu sistema hace todo lo demás la primera vez
y después arranca la app:

| Sistema | Script                                              |
| ------- | --------------------------------------------------- |
| Windows | `scripts\iniciar.bat` (doble clic o desde la terminal) |
| macOS   | `scripts/iniciar.command` (doble clic) o `scripts/iniciar.sh` |
| Linux   | `scripts/iniciar.sh`                                |

Lo que hace:

1. Busca un Python 3.11 o posterior; si no lo hay, dice cómo instalarlo.
2. Crea el entorno virtual `.venv` (o lo rehace si el que hay no funciona, como
   uno copiado de otro equipo) e instala las dependencias.
3. Solo en Linux y macOS: si falta ffmpeg, ofrece instalarlo con el gestor de
   paquetes (`brew`, `apt`, `dnf`, `pacman` o `zypper`) y recomienda Deno si no
   hay ningún runtime de JavaScript.
4. Arranca Sonora. Los argumentos pasan a la app: `scripts/iniciar.sh --navegador`.

> **Debian y Ubuntu** traen Python sin el módulo `venv`. Si falta, el script da
> la orden exacta (`sudo apt install python3.X-venv`).
>
> Si la carpeta tiene un `.venv` de **Windows** (por ejemplo, abierta desde
> WSL), `iniciar.sh` no lo toca y usa `.venv-unix`.

## Cada sistema

- **Windows**: Sonora abre su propia ventana, con el WebView2 que trae el
  sistema. Es donde se desarrolla y se prueba todo.
- **Linux**: se abre en el navegador predeterminado. pywebview no trae en Linux
  con qué dibujar la ventana, y Sonora lo detecta y usa el navegador sin que
  haya que hacer nada. Mejor así: los navegadores reproducen MP3 y MP4, y el
  motor Qt que se instala con pip no trae esos códecs. La CI comprueba en cada
  cambio que `iniciar.sh` la deja funcionando en Ubuntu.
- **macOS**: `pip install -r requirements.txt` instala lo que pywebview
  necesita para abrir la ventana con el WebKit del sistema. La CI pasa los
  tests en macOS y comprueba que arranca en el navegador, pero la ventana no la
  ha probado nadie todavía; si no se abriera, Sonora pasaría sola al navegador.

Sin ventana, Sonora deja la dirección en la terminal y se cierra sola unos
segundos después de cerrar su pestaña (o con `Ctrl+C`). Para usar el navegador
en cualquier sistema:

```bash
python -m sonora --navegador
```

Si prefieres prepararlo todo a mano, sigue leyendo.

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

# macOS (Homebrew)
brew install deno

# Linux
curl -fsSL https://deno.land/install.sh | sh

# o, si ya tienes Node.js 22 o posterior, no hace falta instalar nada
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

> Si usas el `.exe` empaquetado no hace falta nada de esto: ffmpeg y el runtime
> de JavaScript van dentro, y yt-dlp se actualiza desde la propia app (botón
> **Actualizar ahora**). Ver [empaquetado.md](empaquetado.md).

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
python -m ruff check sonora tests scripts   # linter
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
