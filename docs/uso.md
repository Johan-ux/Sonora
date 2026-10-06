# Uso (desarrollo)

La forma más sencilla en Windows es ejecutar el atajo:

```bash
scripts\iniciar.bat
```

`iniciar.bat` activa el entorno virtual (`.venv`) y lanza la app. De forma
equivalente, desde la raíz del repositorio:

```bash
python -m sonora
```

En ambos casos se abre la **ventana propia** de Sonora (no el navegador). Por
dentro, la app arranca un pequeño servidor Flask en `127.0.0.1` sobre un puerto
libre y abre esa ventana con `pywebview`. Al cerrar la ventana, la app termina
por completo.

## De un vistazo

- **Buscar**: escribe y pulsa Enter (o pega una URL). Pulsa **＋** en cualquier
  resultado para añadirlo a la cola; con playlists puedes añadir **todo** o por
  **lotes de 100**.
- **Descargas**: elige carpeta de destino y calidad (se recuerdan) y pulsa
  **Descargar todo**. Puedes cancelar la descarga en curso, quitar pendientes
  y reintentar las fallidas.
- **Biblioteca**: pulsa play en cualquier pista; usa aleatorio/repetir y las
  teclas multimedia del sistema. Los vídeos se abren en su propia ventana
  dentro de la app (ver [Ver vídeos](#ver-vídeos)).
- **Historial**: consulta lo descargado anteriormente.

## Escuchar antes de descargar

Cada resultado de búsqueda tiene un botón de reproducción sobre su miniatura:
abre el reproductor de YouTube para decidir si la canción es la que buscabas
antes de gastar la descarga. Desde su pie se añade a la cola directamente.

Se abre en la misma **ventana flotante** que los vídeos de la biblioteca (ver
[Ver vídeos](#ver-vídeos)): se mueve, se redimensiona y pasa a modo teatro o a
pantalla completa igual, y recuerda el mismo sitio y tamaño. Como no bloquea el
resto de la app, puedes seguir mirando resultados o añadir otros a la cola
mientras suena. Se cierra con su botón ✕ o con `Esc`.

Solo suena una cosa a la vez: abrir la vista previa pone en pausa lo que
estuviera sonando de la biblioteca, y reproducir algo de la biblioteca cierra
la vista previa.

Se usa el reproductor incrustado de YouTube (dominio `youtube-nocookie.com`,
que no planta cookies de seguimiento) en lugar de traer el audio por nuestra
cuenta: las URLs de stream van firmadas y caducan, así que un reproductor
propio se rompería solo. Requiere conexión, y los vídeos cuyo autor prohíbe
incrustarlos mostrarán en su lugar un aviso de YouTube.

## Ver vídeos

Al reproducir un vídeo de la biblioteca se abre una **ventana flotante** sobre
la app, que se coloca y se dimensiona a mano:

- **Mover**: arrastra su barra de título.
- **Cambiar el tamaño**: tira de cualquier borde o esquina. La ventana conserva
  la proporción del vídeo (también en los verticales).
- **Con teclado**: lleva el foco al botón de agarre (los seis puntos de la
  barra) y usa las flechas para mover, `Mayús` + flechas para el tamaño e
  `Inicio` para devolverla a su esquina.

La ventana nunca tapa la barra de reproducción, y la app **recuerda** dónde la
dejaste, su tamaño y el volumen para la próxima vez.

Además de la ventana flotante hay otros dos modos, en los botones de la barra:

- **Modo teatro**: el vídeo ocupa toda la zona de contenido. También con doble
  clic en la barra de título.
- **Pantalla completa**: también con doble clic sobre el vídeo.

Sobre el vídeo aparecen sus controles (posición, play/pausa, silencio, volumen
y velocidad de 0.5× a 2×); se esconden solos mientras se reproduce y vuelven al
mover el ratón. Un clic en el vídeo alterna play/pausa.

El botón de la flecha **oculta** el vídeo sin detenerlo, para seguir solo con
el sonido; el icono de la cámara en la barra de reproducción lo vuelve a
mostrar.

## Descargas en paralelo

Por defecto se descargan **tres canciones a la vez**; se ajusta en
**Descargas → A la vez** (de 1 a 5). Con una playlist grande la diferencia es
notable, porque mientras una pista se convierte a MP3 las otras siguen
bajando. Subirlo mucho no siempre es mejor: YouTube estrangula la conexión
cuando se le piden demasiadas cosas a la vez.

El cambio se aplica a la siguiente tanda; las descargas ya en marcha terminan
lo suyo.

## Reintentos automáticos

Si una descarga falla por algo pasajero —un corte de red, un error del
servidor— se reintenta sola hasta tres veces, esperando un poco más en cada
intento. Los fallos definitivos (vídeo privado, borrado o bloqueado en tu
país) no se reintentan: se marcan como error directamente, para no hacer
esperar al resto de la cola.

Al cancelar una descarga (o cuando falla del todo) se borran los ficheros a
medias que deja yt-dlp, en lugar de quedarse ocupando sitio en la carpeta de
música para siempre.

## Aviso de actualización

Al abrir Sonora se comprueba el entorno y, si algo merece tu atención, aparece
un aviso abajo en la barra lateral:

- **Hay una versión nueva de yt-dlp.** Es lo que conviene vigilar: YouTube
  cambia a menudo y un yt-dlp viejo deja de descargar (`HTTP Error 403`). El
  botón **Actualizar ahora** lanza `pip install --upgrade yt-dlp` desde la
  propia app; al terminar hay que **reiniciar Sonora** para que surta efecto.
- **Tu yt-dlp pasa de 90 días** y no se pudo consultar si hay uno más nuevo
  (sin conexión, por ejemplo).
- **Falta un runtime de JavaScript**, con la orden para instalarlo.

Si no hay nada que decir, el aviso no se muestra. La comprobación consulta
PyPI con un tiempo de espera corto y cachea el resultado seis horas, así que no
retrasa el arranque; sin conexión, la app abre igual y no avisa de nada.

> En la app **empaquetada** (`.exe`), yt-dlp va dentro del ejecutable y pip no
> puede actualizarlo: el aviso lo dice y hay que reconstruirla
> (ver [empaquetado.md](empaquetado.md)).

## Atajos de teclado

| Tecla             | Acción                                         |
| ----------------- | ---------------------------------------------- |
| `Espacio`         | Play / pausa                                   |
| `←` / `→`         | Retroceder / avanzar 5 segundos                |
| `M`               | Silenciar o devolver el sonido                 |
| `/`               | Ir al buscador                                 |
| Teclas multimedia | Play, anterior, siguiente                      |
| `F`               | Vídeo: pantalla completa                       |
| `T`               | Vídeo: modo teatro (`Esc` vuelve a la ventana) |
| `↑` / `↓`         | Vídeo: subir / bajar el volumen                |

`↑` y `↓` solo mueven el volumen cuando el vídeo tiene el protagonismo (en
teatro, a pantalla completa o con el foco en su ventana); en el resto de la app
desplazan las listas, como siempre.

La interfaz es navegable por completo con teclado, con foco visible, *live
regions* para lectores de pantalla, contraste AA y respeto de
`prefers-reduced-motion`.

---

Siguiente: [CLI](cli.md) · [Empaquetado](empaquetado.md) · [Arquitectura](arquitectura.md)
