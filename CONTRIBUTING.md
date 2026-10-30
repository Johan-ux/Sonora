# Cómo contribuir

Gracias por querer mejorar Sonora. Todo es bienvenido: avisar de un fallo,
proponer una idea, mejorar la documentación o mandar código.

Al participar aceptas el [código de conducta](CODE_OF_CONDUCT.md). Si lo que
has encontrado es un problema de seguridad, no abras un _issue_: sigue
[SECURITY.md](SECURITY.md).

## Fallos y propuestas

Abre un [_issue_](https://github.com/Johan-ux/Sonora/issues/new/choose) con la
plantilla que corresponda. Antes, mira si ya existe uno parecido.

Si una descarga falla, comprueba primero que el aviso de la barra lateral no
ofrece actualizar yt-dlp: un yt-dlp viejo es, con diferencia, la causa más
habitual (YouTube cambia a menudo).

## Preparar el entorno

Hace falta **Python 3.11 o posterior** y **ffmpeg** (ver
[docs/instalacion.md](docs/instalacion.md)).

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt   # incluye las de la app

python -m sonora                  # arranca la app
```

En desarrollo, la música y la base de datos van a `datos/` (ignorada por git),
no a la carpeta de datos de la app instalada.

## Antes de mandar cambios

```bash
python -m pytest                          # tests
python -m ruff check sonora tests scripts # linter
```

La CI ejecuta lo mismo en Windows y Ubuntu, con Python 3.11 y 3.14, y además
arranca Sonora en Ubuntu para comprobar que se abre en el navegador. Un _pull
request_ se fusiona con la CI en verde.

Si tocas el empaquetado, construye el `.exe` y ábrelo
(ver [docs/empaquetado.md](docs/empaquetado.md)):

```bash
python scripts/construir.py
```

## Estilo

- **Todo en español**: interfaz, nombres, comentarios y documentación, con sus
  tildes. Los términos técnicos sin traducción habitual van tal cual.
- Los comentarios explican el **porqué**, no repiten lo que dice el código.
- Lo que no deja pasar ruff no se sube; las reglas que se silencian a propósito
  están explicadas en [`pyproject.toml`](pyproject.toml).
- Cada cambio de comportamiento trae su test.

## Commits

Mensajes en español con el formato de
[Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/):

```text
fix: la cola no se vacía al cancelar la última descarga

Explicación en prosa de qué fallaba y por qué el cambio lo arregla.
```

Tipos habituales: `feat`, `fix`, `docs`, `refactor`, `test`, `ci` y `chore`.

## Pull requests

1. Crea una rama desde `main` (`fix/...`, `feat/...`).
2. Un _pull request_ por cambio; mejor pequeño que enorme.
3. Si cambia algo que nota quien usa la app, añádelo a la sección
   «Sin publicar» de [CHANGELOG.md](CHANGELOG.md).
4. Rellena la plantilla: qué cambia, por qué y cómo lo has probado.

## Publicar una versión

Lo hace quien mantiene el proyecto:

1. Sube la versión en `sonora/__init__.py` siguiendo
   [versionado semántico](https://semver.org/lang/es/).
2. En `CHANGELOG.md`, convierte «Sin publicar» en la sección de esa versión,
   con su fecha.
3. Crea la etiqueta `v` + versión (por ejemplo, `v1.1.0`) y súbela. El
   workflow `publicar.yml` comprueba que coincide con `sonora/__init__.py`,
   construye el zip y crea la release con las notas del changelog.

## Licencia

Lo que aportes se publica bajo la [licencia MIT](LICENSE) del proyecto.
