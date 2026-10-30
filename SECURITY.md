# Política de seguridad

## Versiones con soporte

Solo la última versión publicada en
[Releases](https://github.com/Johan-ux/Sonora/releases/latest) recibe arreglos
de seguridad. Si usas una anterior, actualiza antes de informar.

## Cómo avisar de una vulnerabilidad

**No abras un _issue_ público.** Usa el aviso privado de GitHub: pestaña
**Security → Report a vulnerability**, o directamente
[este enlace](https://github.com/Johan-ux/Sonora/security/advisories/new). Solo
lo ven los administradores del repositorio.

Cuenta, si puedes:

- qué parte de Sonora está afectada (la app, el `.exe`, la CLI) y qué versión;
- cómo reproducirlo, paso a paso;
- qué podría hacer quien lo aprovechara.

Sonora la mantiene una sola persona en su tiempo libre: el acuse de recibo
suele llegar en una semana. Una vez arreglado, el aviso se publica con el
crédito para quien lo encontró, salvo que prefieras quedar en el anonimato.

## Qué cuenta como vulnerabilidad

Sonora abre un servidor local (en `127.0.0.1`) que la ventana usa para todo, y
descarga y ejecuta programas de terceros. Interesa especialmente:

- que una página web cualquiera, abierta en el navegador, pueda llamar a la API
  local de Sonora (falsificación de peticiones, *DNS rebinding*…);
- leer, escribir o borrar ficheros fuera de la carpeta de descargas;
- conseguir que una URL, un título o un nombre de fichero se ejecute como orden;
- que la actualización de yt-dlp dentro del `.exe` acepte un paquete que no sea
  el publicado en PyPI.

**No** son vulnerabilidades, sino fallos normales (ábrelos como *issue*): que
una descarga falle porque YouTube ha cambiado, o un aviso de una dependencia que
ya está corregido en su última versión.
