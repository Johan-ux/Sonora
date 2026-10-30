// app.js — Lógica de frontend de "Sonora" (vanilla JS, sin frameworks).
// Todo el texto visible va en español. Se escapa SIEMPRE el texto dinámico
// inyectado en innerHTML mediante esc() para prevenir inyección (XSS): los
// títulos y nombres de canal vienen de YouTube y son controlables por terceros.

"use strict";

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------

// Escapa los caracteres peligrosos para HTML: & < > " '
// Úsala para TODO texto dinámico (títulos, canales, nombres) antes de innerHTML.
function esc(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function $(sel) {
  return document.querySelector(sel);
}
function $$(sel) {
  return Array.from(document.querySelectorAll(sel));
}

// Formatea segundos (número) a "M:SS". Devuelve "0:00" si no es válido.
function formatearTiempo(segundos) {
  if (segundos === null || segundos === undefined || isNaN(segundos) || segundos < 0) {
    return "0:00";
  }
  const total = Math.floor(segundos);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m + ":" + String(s).padStart(2, "0");
}

// Fecha ISO-8601 → "2 jul 2026, 14:03" (o la cadena original si no parsea).
function formatearFecha(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("es", { day: "numeric", month: "short", year: "numeric" }) +
    ", " + d.toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
}

// Construye la URL de audio (inline) para un archivo relativo bajo descargas/.
// Codifica cada segmento para soportar espacios y caracteres especiales.
function urlAudio(archivo) {
  const partes = String(archivo).split("/").map(encodeURIComponent);
  return "/audio/" + partes.join("/");
}

// Petición JSON robusta. Lanza Error con el mensaje del backend si lo hay.
async function pedirJSON(url, opciones) {
  const opts = opciones || {};
  if (opts.body && !(opts.headers && opts.headers["Content-Type"])) {
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  }
  const resp = await fetch(url, opts);
  let datos = null;
  try {
    datos = await resp.json();
  } catch (e) {
    datos = null;
  }
  if (!resp.ok) {
    const msg = (datos && datos.error) ? datos.error : "Error " + resp.status;
    throw new Error(msg);
  }
  return datos;
}

// Devuelve una versión "debounced" de fn (para el filtro de la biblioteca).
function debounce(fn, ms) {
  let temporizador = null;
  return function (...args) {
    clearTimeout(temporizador);
    temporizador = setTimeout(() => fn.apply(this, args), ms);
  };
}

// Acota v al intervalo [min, max].
function limitar(v, min, max) {
  return Math.min(max, Math.max(min, v));
}

// Aviso no bloqueante (toast) en la región viva #avisos (aria-live="polite").
function avisar(mensaje, tipo) {
  const cont = $("#avisos");
  if (!cont) return;
  // El contenedor es un popover manual, abierto desde el arranque. Si después
  // ha entrado algo más en la capa superior (un diálogo, la pantalla completa)
  // lo taparía: se cierra y se vuelve a abrir para quedar encima.
  if (cont.hasAttribute("popover")) {
    const tapado = document.fullscreenElement || document.querySelector("dialog[open]");
    if (tapado && cont.matches(":popover-open")) cont.hidePopover();
    if (!cont.matches(":popover-open")) cont.showPopover();
  }
  const el = document.createElement("div");
  el.className = "aviso" + (tipo ? " aviso-" + tipo : " aviso-info");
  const icono = document.createElement("span");
  icono.className = "aviso-icono";
  icono.setAttribute("aria-hidden", "true");
  icono.textContent = tipo === "ok" ? "✓" : tipo === "error" ? "!" : "·";
  const texto = document.createElement("span");
  texto.textContent = mensaje; // textContent: seguro, no necesita esc()
  el.append(icono, texto);
  cont.appendChild(el);
  setTimeout(() => {
    el.classList.add("saliendo");
    setTimeout(() => el.remove(), 400);
  }, 4200);
}

// Pinta el tramo recorrido de un input[type=range] (la pista usa var(--pct)).
function pintarRango(input, pct) {
  input.style.setProperty("--pct", (isFinite(pct) ? pct : 0) + "%");
}

// Iconos SVG reutilizados en el render dinámico (aria-hidden: decorativos).
const ICONO = {
  play: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M8 5.5v13l11-6.5-11-6.5z" fill="currentColor"/></svg>',
  pausa: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor"/></svg>',
  quitar: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  cancelar: '<svg aria-hidden="true" viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor"/></svg>',
  reintentar: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 1 2.3 5.6M4 12V7m0 5h5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  papelera: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M5 7h14M10 7V5h4v2m-7 0 1 12h8l1-12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  carpeta: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
  nota: '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M9 18V6l10-2v12" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><circle cx="6.5" cy="18" r="2.5" fill="currentColor"/><circle cx="16.5" cy="16" r="2.5" fill="currentColor"/></svg>',
};

// ---------------------------------------------------------------------------
// Estado global
// ---------------------------------------------------------------------------

const estado = {
  vista: "buscar",
  carpetaDestino: "",           // ruta relativa bajo descargas/ ('' = raíz)
  bitrate: "320",
  formato: "audio",             // formato por defecto: 'audio' | 'video'
  resolucion: "1080",           // resolución por defecto para vídeo
  simultaneas: 3,               // descargas en paralelo
  ffmpegDisponible: true,
  salud: null,                  // último chequeo del entorno (/api/salud)
  cola: [],                     // ítems de la cola (espejo de la BD, vía SSE)
  urlsActivas: new Set(),       // urls 'en_cola' | 'descargando'
  lotesCerrados: new Set(),     // lotes plegados por el usuario (persistencia UI)
  busqueda: {
    token: 0,                   // anti-carrera: solo pinta la respuesta más reciente
    datos: null,                // última respuesta renderizada
    consulta: "",               // lo último que se buscó (texto o URL)
    volverA: "",                // búsqueda desde la que se abrió una lista o un canal
    filtros: {                  // filtros de la búsqueda por texto (ver iniciarFiltros)
      orden: "relevancia",
      fecha: "",
      duracion: "",
      tipo: "video",
      caracteristicas: [],
    },
  },
  biblioteca: {
    items: [],
    carpetas: [],
    carpeta: "",
    filtro: "",
    token: 0,                   // anti-carrera del filtro (como en la búsqueda)
  },
  rep: {
    lista: [],                  // instantánea de pistas al pulsar play
    indice: -1,
    archivo: "",                // archivo en reproducción (clave estable)
    tipo: "audio",              // tipo de la pista actual: 'audio' | 'video'
    videoVisible: false,        // si el escenario de vídeo está desplegado
    aleatorio: false,
    repetir: "off",             // off | all | one
    historialAleatorio: [],     // índices ya sonados en modo aleatorio (para "anterior")
    arrastrandoSeek: false,
  },
  video: {
    modo: "flotante",           // 'flotante' | 'teatro' (persistido en el backend)
    geometria: null,            // {x, y, lado} elegidos a mano; null = esquina por defecto
    proporcion: 16 / 9,         // ancho/alto del vídeo actual (fija el alto de la ventana)
    velocidad: 1,               // velocidad elegida para los vídeos (no se persiste)
    previa: null,               // resultado del buscador en vista previa ({id, origen}) o null
  },
  dialogo: {
    ruta: "",                   // carpeta que muestra el explorador
  },
};

// Elemento multimedia ÚNICO: es un <video> pero reproduce también el audio
// (MP3). Cuando suena audio, el escenario de vídeo permanece oculto y se
// muestra la carátula/estado en la barra. Un solo elemento evita duplicar la
// lógica de transporte y re-parentar un medio en reproducción.
const audio = $("#media");
const escenario = $("#escenario-video");

// ---------------------------------------------------------------------------
// Navegación entre vistas
// ---------------------------------------------------------------------------

function cambiarVista(nombre) {
  // En modo teatro el vídeo tapa las vistas: al navegar vuelve a la ventana
  // flotante para que se vea adónde se ha ido.
  if (!escenario.hidden && estado.video.modo === "teatro") {
    fijarModoVideo("flotante");
  }
  estado.vista = nombre;
  $$(".nav-item").forEach((btn) => {
    if (btn.dataset.vista === nombre) {
      btn.setAttribute("aria-current", "page");
    } else {
      btn.removeAttribute("aria-current");
    }
  });
  $$(".vista").forEach((v) => {
    v.hidden = v.id !== "vista-" + nombre;
  });
  if (nombre === "biblioteca") cargarBiblioteca();
  if (nombre === "historial") cargarHistorial();
  if (nombre === "cola") renderCola();
}

function iniciarNavegacion() {
  $$(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => cambiarVista(btn.dataset.vista));
  });
}

// ---------------------------------------------------------------------------
// Configuración (carpeta y bitrate por defecto, persistidos en el backend)
// ---------------------------------------------------------------------------

function etiquetaCarpeta(rel) {
  return rel ? "descargas/" + rel : "descargas/";
}

async function cargarConfig() {
  try {
    const cfg = await pedirJSON("/api/config");
    estado.carpetaDestino = cfg.carpeta_por_defecto || "";
    estado.bitrate = cfg.bitrate_por_defecto || "320";
    estado.formato = cfg.formato_por_defecto || "audio";
    estado.resolucion = cfg.resolucion_por_defecto || "1080";
    estado.simultaneas = cfg.descargas_simultaneas || 3;
    estado.ffmpegDisponible = Boolean(cfg.ffmpeg_disponible);
    // Preferencias del reproductor (el evento 'volumechange' pinta los deslizadores).
    audio.volume = typeof cfg.volumen === "number" ? limitar(cfg.volumen, 0, 1) : 1;
    estado.video.modo = cfg.video_modo === "teatro" ? "teatro" : "flotante";
    estado.video.geometria = cfg.video_geometria || null;
    reflejarEscenario();
    // El orden de búsqueda es lo único de los filtros que se recuerda.
    $("#filtro-orden").value = cfg.busqueda_orden || "relevancia";
    estado.busqueda.filtros = leerFiltros();
    $("#select-bitrate").value = estado.bitrate;
    $("#select-resolucion").value = estado.resolucion;
    $("#select-simultaneas").value = String(estado.simultaneas);
    $("#carpeta-actual").textContent = etiquetaCarpeta(estado.carpetaDestino);
    $("#aviso-ffmpeg").hidden = estado.ffmpegDisponible;
    reflejarFormato();
    if (!estado.ffmpegDisponible) {
      avisar("No se encontró ffmpeg: la conversión a MP3 y la de vídeo fallarán.", "error");
    }
  } catch (e) {
    avisar("No se pudo cargar la configuración: " + e.message, "error");
  }
}

async function guardarConfig(cambios) {
  try {
    await pedirJSON("/api/config", { method: "POST", body: JSON.stringify(cambios) });
  } catch (e) {
    avisar("No se pudo guardar la configuración: " + e.message, "error");
  }
}

// Refleja el formato activo en el segmentado y muestra el selector de calidad
// que corresponde (bitrate para audio, resolución para vídeo).
function reflejarFormato() {
  const esVideo = estado.formato === "video";
  $("#seg-audio").setAttribute("aria-pressed", String(!esVideo));
  $("#seg-video").setAttribute("aria-pressed", String(esVideo));
  $("#ajuste-bitrate").hidden = esVideo;
  $("#ajuste-resolucion").hidden = !esVideo;
}

function iniciarConfig() {
  $("#select-bitrate").addEventListener("change", (e) => {
    estado.bitrate = e.target.value;
    guardarConfig({ bitrate_por_defecto: estado.bitrate });
  });
  $("#select-resolucion").addEventListener("change", (e) => {
    estado.resolucion = e.target.value;
    guardarConfig({ resolucion_por_defecto: estado.resolucion });
  });
  $("#select-simultaneas").addEventListener("change", (e) => {
    estado.simultaneas = Number(e.target.value) || 3;
    // Se aplica a la siguiente tanda: los workers ya en marcha terminan lo suyo.
    guardarConfig({ descargas_simultaneas: estado.simultaneas });
  });
  $("#seg-audio").addEventListener("click", () => cambiarFormato("audio"));
  $("#seg-video").addEventListener("click", () => cambiarFormato("video"));
  $("#btn-carpeta").addEventListener("click", () => abrirDialogoCarpetas());
}

function cambiarFormato(formato) {
  estado.formato = formato;
  reflejarFormato();
  guardarConfig({ formato_por_defecto: formato });
}

// ---------------------------------------------------------------------------
// Buscar
// ---------------------------------------------------------------------------

function iniciarBuscador() {
  $("#form-buscar").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("#campo-buscar").value.trim();
    if (!q) return;
    cambiarVista("buscar");
    buscar(q);
  });
  iniciarFiltros();
}

// --------------------------- Filtros de búsqueda --------------------------- //
//
// Orden, fecha de subida, duración, tipo y características, como en YouTube.
// Solo afectan a la búsqueda por texto: una URL pegada ya dice qué se quiere.
// El orden se recuerda entre sesiones; lo demás dura lo que la app abierta.

function esUrl(texto) {
  return /^https?:\/\//i.test(texto);
}

// Lee los filtros tal y como están en el formulario.
function leerFiltros() {
  const datos = new FormData($("#filtros-busqueda"));
  return {
    orden: datos.get("orden") || "relevancia",
    fecha: datos.get("fecha") || "",
    duracion: datos.get("duracion") || "",
    tipo: datos.get("tipo") || "video",
    caracteristicas: datos.getAll("caracteristicas"),
  };
}

// Indica si algo acota los resultados (el orden no cuenta: solo los recoloca).
function hayFiltrosActivos() {
  const f = estado.busqueda.filtros;
  return Boolean(f.fecha || f.duracion || f.tipo !== "video" || f.caracteristicas.length);
}

function reflejarFiltros() {
  const marcadas = estado.busqueda.filtros.caracteristicas.length;
  const contador = $("#filtro-caracteristicas-n");
  contador.textContent = String(marcadas);
  contador.hidden = marcadas === 0;
  $("#filtros-quitar").hidden = !hayFiltrosActivos();
}

// Vuelve a lanzar la última búsqueda por texto con los filtros de ahora.
function repetirBusqueda() {
  const q = estado.busqueda.consulta;
  if (q && !esUrl(q)) buscar(q);
}

function iniciarFiltros() {
  const form = $("#filtros-busqueda");
  form.addEventListener("submit", (e) => e.preventDefault());
  form.addEventListener("change", (e) => {
    estado.busqueda.filtros = leerFiltros();
    reflejarFiltros();
    if (e.target.name === "orden") {
      guardarConfig({ busqueda_orden: estado.busqueda.filtros.orden });
    }
    repetirBusqueda();
  });
  $("#filtros-quitar").addEventListener("click", () => {
    // Quita lo que acota; el orden elegido se queda como está.
    const orden = estado.busqueda.filtros.orden;
    form.reset();
    $("#filtro-orden").value = orden;
    estado.busqueda.filtros = leerFiltros();
    reflejarFiltros();
    repetirBusqueda();
  });
  reflejarFiltros();
}

// Abre una lista o un canal encontrados en la búsqueda: se expanden buscando
// por su URL (el camino de siempre), recordando de dónde se venía.
function abrirColeccion(url) {
  if (!esUrl(estado.busqueda.consulta)) estado.busqueda.volverA = estado.busqueda.consulta;
  $("#campo-buscar").value = url;
  buscar(url);
}

async function buscar(q) {
  const cont = $("#resultados");
  const token = ++estado.busqueda.token;
  estado.busqueda.consulta = q;
  // Tras una búsqueda por texto ya no hay adónde «volver»: los resultados son estos.
  if (!esUrl(q)) estado.busqueda.volverA = "";
  cont.innerHTML = '<p class="cargando">Buscando…</p>';
  let datos;
  try {
    datos = await pedirJSON("/api/buscar", {
      method: "POST",
      body: JSON.stringify({ q: q, n: 24, filtros: estado.busqueda.filtros }),
    });
  } catch (e) {
    if (token !== estado.busqueda.token) return; // llegó tarde: la descartamos
    cont.innerHTML = "";
    const p = document.createElement("p");
    p.className = "mensaje-error";
    p.textContent = "No se pudo buscar: " + e.message;
    cont.appendChild(p);
    return;
  }
  // Anti-carrera: si el usuario lanzó otra búsqueda mientras tanto, esta
  // respuesta es vieja y NO debe pisar los resultados más recientes.
  if (token !== estado.busqueda.token) return;
  estado.busqueda.datos = datos;
  renderResultados(datos);
}

const _tiempoRelativo = new Intl.RelativeTimeFormat("es", { numeric: "auto" });

// Fecha de subida en palabras («hace 3 meses») a partir de la marca de tiempo
// del resultado, que en las búsquedas es aproximada; '' si no se conoce.
function haceCuanto(timestamp) {
  if (!timestamp) return "";
  const segundos = Date.now() / 1000 - timestamp;
  const tramos = [["year", 31557600], ["month", 2629800], ["week", 604800], ["day", 86400]];
  for (const [unidad, dura] of tramos) {
    // Se redondea en vez de truncar: YouTube dice «hace 4 meses» y la cuenta
    // de vuelta, con meses de 28 a 31 días, puede quedarse en 3,9.
    if (segundos >= dura * 0.95) {
      return _tiempoRelativo.format(-Math.round(segundos / dura), unidad);
    }
  }
  return "hoy";
}

function tarjetaResultado(r) {
  if (r.tipo === "lista" || r.tipo === "canal") return tarjetaColeccion(r);
  const conThumb = r.thumbnail
    ? '<img src="' + esc(r.thumbnail) + '" alt="" loading="lazy">'
    : "";
  // Los atributos data-* se comparten entre el botón de añadir (usa el formato
  // global) y el ▾ (abre el menú para elegir audio o vídeo explícitamente).
  const datosItem =
    'data-url="' + esc(r.url) + '" data-titulo="' + esc(r.titulo) + '" ' +
    'data-thumbnail="' + esc(r.thumbnail) + '" data-duracion="' + esc(r.duracion) + '" ' +
    'data-canal="' + esc(r.canal) + '"';
  // Un directo en curso (o por empezar) se puede ver, pero no descargar: la
  // tarjeta solo ofrece abrirlo en la ventana de vídeo.
  if (r.directo === "en_vivo" || r.directo === "programado") {
    const rotulo = r.directo === "en_vivo" ? "Ver en directo" : "Ver la sala de espera";
    const boton = r.id
      ? '<button type="button" class="tarjeta-abrir tarjeta-preview" data-preview-id="' +
          esc(r.id) + '" data-directo="' + esc(r.directo) + '" ' + datosItem +
          ' aria-label="' + rotulo + ": " + esc(r.titulo) + '">' + rotulo + "</button>"
      : "";
    return (
      '<article class="tarjeta">' +
        '<div class="tarjeta-cover' + (r.id ? " con-preview" : "") + '">' + conThumb + "</div>" +
        '<h3 class="tarjeta-titulo">' + esc(r.titulo) + "</h3>" +
        '<p class="tarjeta-canal">' + esc(r.canal) + "</p>" +
        '<p class="tarjeta-meta">' +
          (r.directo === "en_vivo"
            ? '<span class="tarjeta-directo">En directo</span>'
            : "<span>Programado</span>") +
        "</p>" +
        '<div class="tarjeta-acciones">' + boton + "</div>" +
      "</article>"
    );
  }
  // La portada va limpia, sin nada encima: las acciones están en el pie.
  const preview = r.id
    ? '<button type="button" class="btn-icono tarjeta-preview" data-preview-id="' + esc(r.id) + '" ' +
        datosItem + ' aria-label="Escuchar antes de descargar: ' + esc(r.titulo) + '"' +
        ' title="Escuchar antes de descargar">' + ICONO.play + "</button>"
    : "";
  // Un directo ya terminado es un vídeo más; solo se avisa de que lo fue.
  const fecha = haceCuanto(r.timestamp);
  const cuando = r.directo === "terminado" ? "emitido " + (fecha || "en directo") : fecha;
  return (
    '<article class="tarjeta">' +
      '<div class="tarjeta-cover' + (r.id ? " con-preview" : "") + '">' + conThumb + "</div>" +
      '<h3 class="tarjeta-titulo">' + esc(r.titulo) + "</h3>" +
      '<p class="tarjeta-canal">' + esc(r.canal) + "</p>" +
      '<p class="tarjeta-meta">' +
        '<span class="tarjeta-duracion">' + esc(r.duracion) + "</span>" +
        "<span>" + esc(cuando) + "</span>" +
      "</p>" +
      '<div class="tarjeta-acciones">' + preview +
        '<div class="tarjeta-add-grupo">' +
          '<button type="button" class="tarjeta-add" ' + datosItem + ' ' +
            'aria-label="Añadir a la cola: ' + esc(r.titulo) + '">＋ Añadir</button>' +
          '<button type="button" class="tarjeta-add-mas" ' + datosItem + ' ' +
            'aria-label="Elegir formato para: ' + esc(r.titulo) + '" aria-haspopup="menu">▾</button>' +
        "</div>" +
      "</div>" +
    "</article>"
  );
}

// Tarjeta de una lista o un canal: no se añaden a la cola tal cual, se abren.
function tarjetaColeccion(r) {
  const esCanal = r.tipo === "canal";
  const conThumb = r.thumbnail
    ? '<img src="' + esc(r.thumbnail) + '" alt="" loading="lazy">'
    : "";
  return (
    '<article class="tarjeta tarjeta-coleccion' + (esCanal ? " es-canal" : "") + '">' +
      '<div class="tarjeta-cover">' + conThumb + "</div>" +
      '<h3 class="tarjeta-titulo">' + esc(r.titulo) + "</h3>" +
      '<p class="tarjeta-canal">' + esc(r.canal) + "</p>" +
      '<p class="tarjeta-meta"><span class="chip">' + (esCanal ? "Canal" : "Lista") + "</span></p>" +
      '<div class="tarjeta-acciones">' +
        '<button type="button" class="tarjeta-abrir" data-url="' + esc(r.url) + '">' +
          (esCanal ? "Ver sus vídeos" : "Ver la lista") + "</button>" +
      "</div>" +
    "</article>"
  );
}

function renderResultados(datos) {
  const cont = $("#resultados");
  const resultados = datos.resultados || [];
  if (!resultados.length) {
    const porFiltros = hayFiltrosActivos() && !esUrl(estado.busqueda.consulta);
    cont.innerHTML =
      '<div class="estado-vacio"><h2>Sin resultados</h2><p>' +
      (porFiltros
        ? "Nada coincide con estos filtros. Prueba a quitar alguno."
        : "Prueba con otro término o revisa la URL.") +
      "</p></div>";
    return;
  }

  let html = "";

  if (datos.es_playlist) {
    const titulo = datos.titulo_playlist || (datos.es_canal ? "Canal" : "Playlist");
    const total = datos.total_playlist || resultados.length;
    const obtenidas = datos.obtenidas || resultados.length;
    if (estado.busqueda.volverA) {
      html += '<p class="playlist-volver"><button type="button" class="btn btn-fantasma" ' +
        'id="btn-volver-resultados">Volver a los resultados</button></p>';
    }
    html += '<header class="playlist-cabecera">';
    html += "<h2>" + esc(titulo) + "</h2>";
    html += '<span class="chip chip-acento">' + (datos.es_canal ? "Canal" : datos.es_mix ? "Mix" : "Playlist") + "</span>";
    html += '<span class="chip">' + obtenidas + " canciones</span>";
    html += "</header>";

    if (obtenidas < total) {
      html +=
        '<p class="aviso-parcial">YouTube solo permitió extraer <strong>' +
        obtenidas + " de " + total + "</strong> canciones sin iniciar sesión. " +
        "Puedes descargar estas y volver a intentarlo más tarde.</p>";
    }
    if (datos.tope) {
      html +=
        '<p class="aviso-parcial">Se alcanzó el tope de extracción (' +
        obtenidas + " canciones): la lista puede estar incompleta.</p>";
    }

    html += '<div class="playlist-acciones">';
    html +=
      '<button type="button" class="btn btn-acento" id="btn-agregar-todo" data-titulo="' +
      esc(titulo) + '">＋ Añadir todo (' + resultados.length + ")</button>";
    html += "</div>";

    // Lotes de 100 para playlists grandes: cada chip añade solo ese tramo.
    if (resultados.length > 100) {
      html += '<div class="lotes-lista">';
      const nLotes = Math.ceil(resultados.length / 100);
      for (let i = 0; i < nLotes; i++) {
        const ini = i * 100;
        const fin = Math.min(ini + 100, resultados.length);
        html +=
          '<button type="button" class="lote-chip" data-ini="' + ini +
          '" data-fin="' + fin + '" data-titulo="' + esc(titulo) + '">' +
          "Lote " + (i + 1) + " · " + (ini + 1) + "–" + fin + "</button>";
      }
      html += "</div>";
    }
  }

  html += '<div class="resultados-grid">';
  for (const r of resultados) {
    html += tarjetaResultado(r);
  }
  html += "</div>";

  cont.innerHTML = html;

  // Listeners de la vista recién pintada.
  $$("#resultados .tarjeta-add").forEach((btn) => {
    btn.addEventListener("click", () => agregarUno(btn));
  });
  $$("#resultados .tarjeta-preview").forEach((btn) => {
    btn.addEventListener("click", () => abrirPreview(btn));
  });
  // La portada también abre la vista previa, pero solo como atajo de ratón:
  // el control de verdad (con foco y nombre) es el botón ▶ del pie.
  $$("#resultados .tarjeta-cover.con-preview").forEach((portada) => {
    portada.addEventListener("click", () => {
      const btn = portada.closest(".tarjeta").querySelector(".tarjeta-preview");
      if (btn) abrirPreview(btn);
    });
  });
  $$("#resultados .tarjeta-coleccion .tarjeta-abrir").forEach((btn) => {
    btn.addEventListener("click", () => abrirColeccion(btn.dataset.url));
  });
  const btnVolver = $("#btn-volver-resultados");
  if (btnVolver) {
    btnVolver.addEventListener("click", () => {
      const q = estado.busqueda.volverA;
      $("#campo-buscar").value = q;
      buscar(q);
    });
  }
  $$("#resultados .tarjeta-add-mas").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      abrirMenuFormato(btn);
    });
  });
  const btnTodo = $("#btn-agregar-todo");
  if (btnTodo) {
    btnTodo.addEventListener("click", () => agregarPlaylist(btnTodo, null, null));
  }
  $$("#resultados .lote-chip").forEach((chip) => {
    chip.addEventListener("click", () =>
      agregarPlaylist(chip, Number(chip.dataset.ini), Number(chip.dataset.fin))
    );
  });

  actualizarBotonesAgregar();
}

// Deshabilita los botones ＋ de resultados cuya URL ya está en la cola.
function actualizarBotonesAgregar() {
  $$("#resultados .tarjeta-add").forEach((btn) => {
    const enCola = estado.urlsActivas.has(btn.dataset.url);
    btn.disabled = enCola;
    btn.textContent = enCola ? "✓ En la cola" : "＋ Añadir";
    // La etiqueta accesible debe reflejar el estado en AMBOS sentidos: al
    // re-habilitarse (descarga terminada) recupera su etiqueta original.
    btn.setAttribute(
      "aria-label",
      enCola ? "Ya está en la cola" : "Añadir a la cola: " + (btn.dataset.titulo || "")
    );
  });
}

// Añade un resultado. 'formato' opcional (override del menú ▾): si se omite,
// usa el formato/resolución global. La resolución solo aplica a vídeo.
async function agregarUno(btn, formato) {
  const fmt = formato || estado.formato;
  btn.disabled = true;
  try {
    const r = await pedirJSON("/api/cola/agregar", {
      method: "POST",
      body: JSON.stringify({
        url: btn.dataset.url,
        titulo: btn.dataset.titulo,
        thumbnail: btn.dataset.thumbnail,
        duracion: btn.dataset.duracion,
        canal: btn.dataset.canal,
        carpeta: estado.carpetaDestino,
        formato: fmt,
        bitrate: estado.bitrate,
        resolucion: estado.resolucion,
      }),
    });
    if (r.duplicado) {
      avisar("Esa canción ya está en la cola.", "info");
    } else {
      avisar(fmt === "video" ? "Vídeo añadido a la cola." : "Añadida a la cola.", "ok");
    }
    btn.textContent = "✓ En la cola";
  } catch (e) {
    btn.disabled = false;
    avisar("No se pudo añadir: " + e.message, "error");
  }
}

// ---------------------------------------------------------------------------
// Menú de formato por resultado (override del ▾)
// ---------------------------------------------------------------------------

let _menuFormato = null;

function menuFormato() {
  if (_menuFormato) return _menuFormato;
  const menu = document.createElement("div");
  menu.className = "menu-formato";
  menu.setAttribute("role", "menu");
  document.body.appendChild(menu);
  _menuFormato = menu;
  // Se cierra al hacer clic fuera o con Escape.
  document.addEventListener("click", (e) => {
    if (menu.classList.contains("abierto") && !menu.contains(e.target)) cerrarMenuFormato();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") cerrarMenuFormato();
  });
  window.addEventListener("resize", cerrarMenuFormato);
  return menu;
}

function cerrarMenuFormato() {
  if (_menuFormato) _menuFormato.classList.remove("abierto");
}

// Abre el menú compartido junto al botón ▾ del resultado. El botón ＋ hermano
// es el que realmente añade (lleva los data-* y el estado disabled).
function abrirMenuFormato(btnMas) {
  const grupo = btnMas.closest(".tarjeta-add-grupo");
  const btnAdd = grupo ? grupo.querySelector(".tarjeta-add") : null;
  if (!btnAdd) return;
  const menu = menuFormato();
  const iconoAudio =
    '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M9 18V6l10-2v12" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><circle cx="6.5" cy="18" r="2.5" fill="currentColor"/><circle cx="16.5" cy="16" r="2.5" fill="currentColor"/></svg>';
  const iconoVideo =
    '<svg aria-hidden="true" viewBox="0 0 24 24"><rect x="3" y="6" width="13" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="m16 10 5-3v10l-5-3z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>';
  menu.innerHTML =
    '<p class="mf-cabecera">Añadir como…</p>' +
    '<button type="button" role="menuitem" data-formato="audio">' + iconoAudio +
      "Audio (MP3 " + esc(estado.bitrate) + " kbps)</button>" +
    '<button type="button" role="menuitem" data-formato="video">' + iconoVideo +
      "Vídeo (MP4 " + (estado.resolucion === "best" ? "mejor" : esc(estado.resolucion) + "p") + ")</button>";
  menu.querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => {
      cerrarMenuFormato();
      agregarUno(btnAdd, b.dataset.formato);
    });
  });
  // Posición: bajo el botón ▾ y alineado con su borde derecho, pero sin salirse
  // de la tarjeta por la izquierda (en la primera columna pisaría la barra
  // lateral) ni de la ventana por la derecha.
  menu.classList.add("abierto");
  const r = btnMas.getBoundingClientRect();
  const ancho = menu.offsetWidth;
  const tarjeta = btnMas.closest(".tarjeta");
  const tope = tarjeta ? tarjeta.getBoundingClientRect().left : 8;
  const izq = limitar(Math.max(r.right - ancho, tope), 8, window.innerWidth - ancho - 8);
  menu.style.left = izq + "px";
  menu.style.top = (r.bottom + 6) + "px";
}

// Añade toda la playlist (ini/fin null) o solo un tramo [ini, fin).
async function agregarPlaylist(btn, ini, fin) {
  const datos = estado.busqueda.datos;
  if (!datos || !datos.resultados || !datos.resultados.length) return;
  const todos = datos.resultados;
  const tramo = ini === null ? todos : todos.slice(ini, fin);
  const titulo = btn.dataset.titulo || datos.titulo_playlist || "Playlist";
  const cuerpo = {
    items: tramo.map((r) => ({
      url: r.url,
      titulo: r.titulo,
      thumbnail: r.thumbnail,
      duracion: r.duracion,
      canal: r.canal,
    })),
    titulo: titulo,
    carpeta: estado.carpetaDestino,
    bitrate: estado.bitrate,
  };
  if (ini !== null) {
    cuerpo.nombre_lote = titulo + " · Lote " + (Math.floor(ini / 100) + 1) +
      " (canciones " + (ini + 1) + "–" + fin + ")";
  }
  const textoOriginal = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Añadiendo…";
  try {
    const r = await pedirJSON("/api/cola/agregar_playlist", {
      method: "POST",
      body: JSON.stringify(cuerpo),
    });
    let msg = "Añadidas " + r.total + " canciones a la cola";
    msg += r.lotes > 1 ? " en " + r.lotes + " lotes." : ".";
    if (r.omitidas) {
      msg += " Se omitieron " + r.omitidas + " que ya estaban.";
    }
    avisar(msg, r.total ? "ok" : "info");
    btn.textContent = "✓ Añadido";
  } catch (e) {
    btn.disabled = false;
    btn.textContent = textoOriginal;
    avisar("No se pudo añadir la playlist: " + e.message, "error");
  }
}

// ---------------------------------------------------------------------------
// Cola de descargas
// ---------------------------------------------------------------------------

function actualizarCola(items) {
  estado.cola = items || [];
  reflejarColaFueraDeSuVista();
  if (estado.vista === "cola") renderCola();
}

// Lo que depende de la cola fuera de su vista: qué URLs están ya en ella
// (para los botones de añadir del buscador) y el contador del menú.
function reflejarColaFueraDeSuVista() {
  estado.urlsActivas = new Set(
    estado.cola
      .filter((i) => i.estado === "en_cola" || i.estado === "descargando")
      .map((i) => i.url)
  );
  actualizarBadgeCola();
  actualizarBotonesAgregar();
}

// Cambio de UNA fila (una descarga empieza, termina o falla). Se sustituye
// solo esa: repintar la lista entera en cada uno de esos cambios hace que una
// playlist de mil canciones se dibuje dos mil veces.
function actualizarItemCola(item) {
  const indice = item ? estado.cola.findIndex((i) => i.id === item.id) : -1;
  if (indice === -1) {
    refrescarCola(); // no la conocemos: nos hemos perdido algo
    return;
  }
  estado.cola[indice] = item;
  reflejarColaFueraDeSuVista();
  if (estado.vista !== "cola") return;
  const fila = document.querySelector(
    '#cola-lista .cola-item[data-id="' + CSS.escape(item.id) + '"]'
  );
  if (!fila) {
    renderCola();
    return;
  }
  pintarControlesCola();
  fila.outerHTML = filaCola(item);
  if (item.lote) pintarCabeceraLote(item.lote);
}

// Contador «hechas/total» de un lote y su botón de quitar las pendientes.
function pintarCabeceraLote(lote) {
  const det = document.querySelector(
    '#cola-lista .lote-grupo[data-lote="' + CSS.escape(lote) + '"]'
  );
  if (!det) return;
  const grupo = estado.cola.filter((i) => i.lote === lote);
  det.querySelector(".lote-contador").textContent =
    grupo.filter((g) => g.estado === "completado").length + "/" + grupo.length;
  const quitar = det.querySelector(".lote-quitar");
  if (quitar && !grupo.some((g) => g.estado === "en_cola")) quitar.remove();
}

function actualizarBadgeCola() {
  const badge = $("#badge-cola");
  const pendientes = estado.cola.filter(
    (i) => i.estado === "en_cola" || i.estado === "descargando"
  ).length;
  badge.hidden = pendientes === 0;
  badge.textContent = pendientes ? String(pendientes) : "";
}

function chipEstado(item) {
  if (item.estado === "descargando") {
    const pct = Math.round(Number(item.progreso) || 0);
    return '<span class="chip chip-acento ci-estado" data-chip-id="' + esc(item.id) + '">' + pct + " %</span>";
  }
  if (item.estado === "completado") {
    return '<span class="chip chip-ok ci-estado">Completada</span>';
  }
  if (item.estado === "error") {
    const cancelada = (item.error || "").startsWith("Cancelada");
    return '<span class="chip chip-error ci-estado">' + (cancelada ? "Cancelada" : "Error") + "</span>";
  }
  return '<span class="chip ci-estado">En cola</span>';
}

function accionesItem(item) {
  if (item.estado === "en_cola") {
    return (
      '<button type="button" class="btn-icono ci-quitar" data-id="' + esc(item.id) +
      '" aria-label="Quitar de la cola: ' + esc(item.titulo || item.url) + '">' + ICONO.quitar + "</button>"
    );
  }
  if (item.estado === "descargando") {
    return (
      '<button type="button" class="btn-icono ci-cancelar" data-id="' + esc(item.id) +
      '" aria-label="Cancelar la descarga: ' + esc(item.titulo || item.url) + '">' + ICONO.cancelar + "</button>"
    );
  }
  if (item.estado === "error") {
    return (
      '<button type="button" class="btn-icono ci-reintentar" data-id="' + esc(item.id) +
      '" aria-label="Reintentar la descarga: ' + esc(item.titulo || item.url) + '">' + ICONO.reintentar + "</button>"
    );
  }
  return "";
}

function filaCola(item) {
  const thumb = item.thumbnail
    ? '<img class="ci-thumb" src="' + esc(item.thumbnail) + '" alt="" loading="lazy">'
    : '<span class="ci-thumb-icono">' + ICONO.nota + "</span>";
  const sub = item.estado === "error" && item.error
    ? '<p class="ci-sub ci-error-msg">' + esc(item.error) + "</p>"
    : '<p class="ci-sub">' + esc(item.canal || "") +
      (item.carpeta ? " · descargas/" + esc(item.carpeta) : "") + "</p>";
  const progreso = item.estado === "descargando"
    ? '<div class="ci-progreso"><div class="ci-progreso-relleno" data-progreso-id="' +
      esc(item.id) + '" style="width:' + (Number(item.progreso) || 0) + '%"></div></div>'
    : "";
  const badge = item.formato === "video"
    ? '<span class="pista-badge">Vídeo ' +
      (item.resolucion === "best" ? "" : esc(item.resolucion || "") + "p") + "</span>"
    : "";
  return (
    '<div class="cola-item" data-id="' + esc(item.id) + '">' +
      thumb +
      '<div class="ci-info">' +
        '<p class="ci-titulo">' + badge + esc(item.titulo || item.url) + "</p>" + sub +
      "</div>" +
      chipEstado(item) +
      '<div class="ci-acciones">' + accionesItem(item) + "</div>" +
      progreso +
    "</div>"
  );
}

// Botones globales y resumen de la cola (sin tocar la lista).
function pintarControlesCola() {
  const items = estado.cola;
  const enCola = items.filter((i) => i.estado === "en_cola").length;
  const descargando = items.filter((i) => i.estado === "descargando").length;
  const errores = items.filter((i) => i.estado === "error").length;
  const completadas = items.filter((i) => i.estado === "completado").length;

  $("#cola-acciones").hidden = items.length === 0;
  const btnDescargar = $("#btn-descargar");
  btnDescargar.disabled = enCola === 0 || descargando > 0;
  $("#btn-descargar-texto").textContent = descargando > 0 ? "Descargando…" : "Descargar todo";
  $("#btn-reintentar-todos").hidden = errores === 0;
  $("#btn-limpiar").hidden = errores + completadas === 0;

  const resumen = [];
  if (enCola) resumen.push(enCola + " en cola");
  if (descargando) resumen.push(descargando + " descargando");
  if (completadas) resumen.push(completadas + " completadas");
  if (errores) resumen.push(errores + " con error");
  $("#cola-resumen").textContent = resumen.join(" · ");
}

function renderCola() {
  const lista = $("#cola-lista");
  const items = estado.cola;
  pintarControlesCola();

  if (!items.length) {
    lista.innerHTML =
      '<div class="estado-vacio">' + ICONO.nota +
      "<h2>La cola está vacía</h2>" +
      "<p>Busca canciones o pega una playlist y añádelas: aparecerán aquí " +
      "listas para descargarse.</p></div>";
    return;
  }

  // Agrupa por id de lote en orden de primera aparición (un Map, no
  // contigüidad: dos peticiones concurrentes pueden intercalar posiciones y
  // exigir ítems consecutivos duplicaría el <details> del mismo lote).
  const bloques = [];
  const porLote = new Map();
  for (const item of items) {
    if (!item.lote) {
      bloques.push({ suelto: item });
      continue;
    }
    let grupo = porLote.get(item.lote);
    if (!grupo) {
      grupo = { lote: item.lote, nombre: item.lote_nombre || "Lote", items: [] };
      porLote.set(item.lote, grupo);
      bloques.push(grupo);
    }
    grupo.items.push(item);
  }

  let html = "";
  for (const bloque of bloques) {
    if (bloque.suelto) {
      html += filaCola(bloque.suelto);
      continue;
    }
    const grupo = bloque.items;
    const hechas = grupo.filter((g) => g.estado === "completado").length;
    const pendientesLote = grupo.filter((g) => g.estado === "en_cola").length;
    const abierto = estado.lotesCerrados.has(bloque.lote) ? "" : " open";
    html +=
      '<details class="lote-grupo" data-lote="' + esc(bloque.lote) + '"' + abierto + ">" +
      "<summary>" +
        "<span>" + esc(bloque.nombre) + "</span>" +
        '<span class="lote-contador">' + hechas + "/" + grupo.length + "</span>" +
        (pendientesLote
          ? '<button type="button" class="btn-icono lote-quitar" data-lote="' + esc(bloque.lote) +
            '" aria-label="Quitar las pendientes del lote ' + esc(bloque.nombre) + '">' +
            ICONO.quitar + "</button>"
          : "") +
      "</summary>" +
      grupo.map(filaCola).join("") +
      "</details>";
  }
  lista.innerHTML = html;
  // Los clics de las filas se atienden desde la propia lista (iniciarCola).
}

async function quitarDeCola(id) {
  try {
    await pedirJSON("/api/cola/eliminar", { method: "POST", body: JSON.stringify({ id: id }) });
  } catch (e) {
    avisar("No se pudo quitar: " + e.message, "error");
  }
}

async function quitarLote(lote) {
  try {
    const r = await pedirJSON("/api/cola/eliminar_lote", {
      method: "POST",
      body: JSON.stringify({ lote: lote }),
    });
    avisar("Quitadas " + r.eliminados + " canciones pendientes del lote.", "ok");
  } catch (e) {
    avisar("No se pudo quitar el lote: " + e.message, "error");
  }
}

async function cancelarDescarga(id, btn) {
  if (btn) btn.disabled = true;
  try {
    await pedirJSON("/api/cola/cancelar", { method: "POST", body: JSON.stringify({ id: id }) });
    avisar("Cancelando la descarga…", "info");
  } catch (e) {
    if (btn) btn.disabled = false;
    avisar("No se pudo cancelar: " + e.message, "error");
  }
}

async function reintentar(id) {
  try {
    await pedirJSON("/api/cola/reintentar", { method: "POST", body: JSON.stringify({ id: id }) });
    avisar("Reintentando la descarga.", "ok");
  } catch (e) {
    avisar("No se pudo reintentar: " + e.message, "error");
  }
}

function iniciarCola() {
  // Un oyente para toda la lista en lugar de tres por fila: las filas se
  // sustituyen sueltas o todas a la vez, y así no hay que volver a engancharlas.
  const lista = $("#cola-lista");
  lista.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn || !lista.contains(btn)) return;
    if (btn.classList.contains("ci-quitar")) {
      quitarDeCola(btn.dataset.id);
    } else if (btn.classList.contains("ci-cancelar")) {
      cancelarDescarga(btn.dataset.id, btn);
    } else if (btn.classList.contains("ci-reintentar")) {
      reintentar(btn.dataset.id);
    } else if (btn.classList.contains("lote-quitar")) {
      e.preventDefault(); // que el clic no pliegue/despliegue el details
      quitarLote(btn.dataset.lote);
    }
  });
  // 'toggle' no burbujea: se escucha en la fase de captura.
  lista.addEventListener("toggle", (e) => {
    const det = e.target;
    if (!(det instanceof HTMLDetailsElement) || !det.dataset.lote) return;
    if (det.open) {
      estado.lotesCerrados.delete(det.dataset.lote);
    } else {
      estado.lotesCerrados.add(det.dataset.lote);
    }
  }, true);

  $("#btn-descargar").addEventListener("click", async () => {
    try {
      await pedirJSON("/api/cola/descargar", { method: "POST" });
      avisar("Descarga iniciada.", "ok");
    } catch (e) {
      avisar("No se pudo iniciar la descarga: " + e.message, "error");
    }
  });
  $("#btn-reintentar-todos").addEventListener("click", async () => {
    try {
      const r = await pedirJSON("/api/cola/reintentar", {
        method: "POST",
        body: JSON.stringify({ todos: true }),
      });
      avisar("Reintentando " + r.reintentados + " descargas.", "ok");
    } catch (e) {
      avisar("No se pudo reintentar: " + e.message, "error");
    }
  });
  $("#btn-limpiar").addEventListener("click", async () => {
    try {
      await pedirJSON("/api/cola/limpiar", { method: "POST" });
    } catch (e) {
      avisar("No se pudo limpiar: " + e.message, "error");
    }
  });
}

// Refresco puntual de la cola por HTTP (arranque y resincronización del SSE).
async function refrescarCola() {
  try {
    const r = await pedirJSON("/api/cola");
    actualizarCola(r.items || []);
  } catch (e) {
    // El SSE reintentará; no molestamos con un toast en cada reconexión.
  }
}

// ---------------------------------------------------------------------------
// Eventos en tiempo real (SSE)
// ---------------------------------------------------------------------------

function iniciarSSE() {
  let huboError = false;
  const fuente = new EventSource("/api/eventos");

  fuente.onopen = () => {
    if (huboError) {
      // Tras una reconexión pudimos perder eventos: resincronizamos la cola.
      huboError = false;
      refrescarCola();
    }
  };

  fuente.onerror = () => {
    huboError = true; // EventSource reintenta solo; al reabrir, resync.
  };

  fuente.onmessage = (ev) => {
    let datos;
    try {
      datos = JSON.parse(ev.data);
    } catch (e) {
      return;
    }
    switch (datos.tipo) {
      case "cola_actualizada":
        actualizarCola(datos.items || []);
        break;
      case "item_actualizado":
        actualizarItemCola(datos.item);
        break;
      case "progreso": {
        // Actualización ligera: solo la barra y el chip del ítem en curso.
        const relleno = document.querySelector(
          '[data-progreso-id="' + CSS.escape(datos.id) + '"]'
        );
        if (relleno) relleno.style.width = (Number(datos.progreso) || 0) + "%";
        const chip = document.querySelector(
          '[data-chip-id="' + CSS.escape(datos.id) + '"]'
        );
        if (chip) {
          // El backend dice qué está haciendo cuando no hay porcentaje que
          // dar: «Convirtiendo…», «Procesando…», «Reintentando (2/3)…».
          chip.textContent = datos.mensaje || Math.round(Number(datos.progreso) || 0) + " %";
        }
        break;
      }
      case "completado":
        avisar("Descargada: " + (datos.titulo || ""), "ok");
        if (estado.vista === "biblioteca") cargarBiblioteca();
        break;
      case "cancelado":
        avisar("Descarga cancelada: " + (datos.titulo || ""), "info");
        break;
      case "error":
        avisar("Error al descargar: " + (datos.error || "desconocido"), "error");
        break;
      default:
        break; // 'descargando' llega seguido de cola_actualizada; nada que hacer
    }
  };
}

// ---------------------------------------------------------------------------
// Biblioteca
// ---------------------------------------------------------------------------

async function cargarBiblioteca() {
  const lista = $("#biblioteca-lista");
  // Anti-carrera (mismo patrón que la búsqueda): al teclear rápido en el
  // filtro, una respuesta lenta y vieja no debe pisar a la más reciente.
  const token = ++estado.biblioteca.token;
  if (!estado.biblioteca.items.length) {
    lista.innerHTML = '<p class="cargando">Cargando biblioteca…</p>';
  }
  let datos;
  try {
    const params = new URLSearchParams();
    if (estado.biblioteca.filtro) params.set("q", estado.biblioteca.filtro);
    if (estado.biblioteca.carpeta) params.set("carpeta", estado.biblioteca.carpeta);
    datos = await pedirJSON("/api/biblioteca?" + params.toString());
  } catch (e) {
    if (token !== estado.biblioteca.token) return;
    lista.innerHTML = "";
    const p = document.createElement("p");
    p.className = "mensaje-error";
    p.textContent = "No se pudo cargar la biblioteca: " + e.message;
    lista.appendChild(p);
    return;
  }
  if (token !== estado.biblioteca.token) return;
  estado.biblioteca.items = datos.items || [];
  estado.biblioteca.carpetas = datos.carpetas || [];
  renderCarpetasBiblioteca();
  renderBiblioteca();
}

// Chips de carpeta: primero el camino hasta la carpeta abierta (para saber
// dónde se está y poder subir), con la actual marcada; después, sus subcarpetas.
function renderCarpetasBiblioteca() {
  const cont = $("#carpetas-biblioteca");
  const carpetas = estado.biblioteca.carpetas;
  const actual = estado.biblioteca.carpeta;
  if (!carpetas.length && !actual) {
    cont.innerHTML = "";
    return;
  }
  const chip = (ruta, nombre, marcada, icono) =>
    '<button type="button" class="chip-carpeta" data-carpeta="' + esc(ruta) +
    '" aria-pressed="' + (marcada ? "true" : "false") + '">' +
    (icono ? ICONO.carpeta + " " : "") + esc(nombre) + "</button>";

  let html = chip("", "Toda la música", actual === "", false);
  const tramos = actual ? actual.split("/") : [];
  tramos.forEach((nombre, i) => {
    html += '<span class="carpeta-separador" aria-hidden="true">›</span>' +
      chip(tramos.slice(0, i + 1).join("/"), nombre, i === tramos.length - 1, true);
  });
  if (tramos.length && carpetas.length) {
    html += '<span class="carpeta-divisor" aria-hidden="true"></span>';
  }
  for (const c of carpetas) {
    html += chip(c, c.split("/").pop(), false, true);
  }
  cont.innerHTML = html;
  $$("#carpetas-biblioteca .chip-carpeta").forEach((boton) => {
    boton.addEventListener("click", () => {
      estado.biblioteca.carpeta = boton.dataset.carpeta;
      cargarBiblioteca();
    });
  });
}

function renderBiblioteca() {
  const lista = $("#biblioteca-lista");
  const items = estado.biblioteca.items;
  if (!items.length) {
    lista.innerHTML =
      '<div class="estado-vacio">' + ICONO.nota +
      "<h2>" + (estado.biblioteca.filtro ? "Nada coincide con el filtro" : "Aún no hay música") + "</h2>" +
      "<p>" + (estado.biblioteca.filtro
        ? "Prueba con otro texto."
        : "Descarga algo desde Buscar y aparecerá aquí.") + "</p></div>";
    return;
  }
  let html = "";
  items.forEach((t, i) => {
    const activa = t.archivo === estado.rep.archivo;
    html +=
      '<div class="pista' + (activa ? " activa" : "") + '" data-archivo="' + esc(t.archivo) + '">' +
        '<span class="pista-num">' + (i + 1) + "</span>" +
        '<button type="button" class="pista-play" data-indice="' + i +
          '" aria-label="Reproducir: ' + esc(t.titulo) + '">' +
          (activa && !audio.paused ? ICONO.pausa : ICONO.play) +
        "</button>" +
        '<div class="pista-info">' +
          '<p class="pista-titulo">' +
            (t.tipo === "video" ? '<span class="pista-badge">Vídeo</span>' : "") +
            esc(t.titulo) + "</p>" +
          '<p class="pista-artista">' + esc(t.artista || "") + "</p>" +
        "</div>" +
        '<span class="pista-album">' + esc(t.album || "") + "</span>" +
        '<span class="pista-duracion">' + esc(t.duracion || "") + "</span>" +
        '<div class="pista-acciones">' +
          '<button type="button" class="btn-icono pista-carpeta" data-archivo="' + esc(t.archivo) +
            '" aria-label="Mostrar en la carpeta: ' + esc(t.titulo) + '">' + ICONO.carpeta + "</button>" +
          '<button type="button" class="btn-icono pista-eliminar" data-archivo="' + esc(t.archivo) +
            '" data-titulo="' + esc(t.titulo) + '" aria-label="Eliminar del disco: ' + esc(t.titulo) + '">' +
            ICONO.papelera + "</button>" +
        "</div>" +
      "</div>";
  });
  lista.innerHTML = html;

  $$("#biblioteca-lista .pista-play").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.indice);
      const pista = estado.biblioteca.items[idx];
      if (pista && pista.archivo === estado.rep.archivo) {
        alternarPlay(); // la pista activa alterna play/pausa
      } else {
        reproducirLista(estado.biblioteca.items, idx);
      }
    });
  });
  $$("#biblioteca-lista .pista-carpeta").forEach((btn) => {
    btn.addEventListener("click", () => abrirCarpetaDe(btn.dataset.archivo));
  });
  $$("#biblioteca-lista .pista-eliminar").forEach((btn) => {
    btn.addEventListener("click", () => eliminarDeBiblioteca(btn.dataset.archivo, btn.dataset.titulo));
  });
}

async function eliminarDeBiblioteca(archivo, titulo) {
  const ok = await confirmar({
    titulo: "Eliminar del disco",
    mensaje: "«" + (titulo || archivo) + "»\n\n" +
      "Se borrará el archivo del disco de forma permanente.",
    textoOk: "Eliminar",
  });
  if (!ok) return;
  // Si es la pista que suena, se suelta ANTES de pedir el borrado: mientras el
  // reproductor la tenga abierta, Windows no deja eliminar el fichero.
  const sonaba = archivo === estado.rep.archivo;
  if (sonaba) {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    estado.rep.archivo = "";
    estado.rep.indice = -1;
    ocultarEscenarioVideo(false);
    actualizarBarraReproductor(null);
  }
  try {
    await pedirJSON("/api/biblioteca/eliminar", {
      method: "POST",
      body: JSON.stringify({ archivo: archivo }),
    });
    if (!sonaba) {
      // Si sonaba otra pista, la quitamos de la cola de reproducción y
      // remapeamos el índice para que "siguiente/anterior" no salten a un hueco.
      const actual = estado.rep.archivo;
      estado.rep.lista = estado.rep.lista.filter((t) => t.archivo !== archivo);
      const idx = estado.rep.lista.findIndex((t) => t.archivo === actual);
      if (idx !== -1) estado.rep.indice = idx;
    }
    avisar("Eliminado del disco.", "ok");
    cargarBiblioteca();
  } catch (e) {
    avisar("No se pudo eliminar: " + e.message, "error");
  }
}

function iniciarBiblioteca() {
  const alFiltrar = debounce(() => {
    estado.biblioteca.filtro = $("#filtro-biblioteca").value.trim();
    cargarBiblioteca();
  }, 250);
  $("#filtro-biblioteca").addEventListener("input", alFiltrar);
}

async function abrirCarpetaDe(archivo) {
  try {
    await pedirJSON("/api/abrir-carpeta", {
      method: "POST",
      body: JSON.stringify({ archivo: archivo || "" }),
    });
  } catch (e) {
    avisar("No se pudo abrir la carpeta: " + e.message, "error");
  }
}

// ---------------------------------------------------------------------------
// Historial
// ---------------------------------------------------------------------------

async function cargarHistorial() {
  const lista = $("#historial-lista");
  lista.innerHTML = '<p class="cargando">Cargando historial…</p>';
  let datos;
  try {
    datos = await pedirJSON("/api/historial");
  } catch (e) {
    lista.innerHTML = "";
    const p = document.createElement("p");
    p.className = "mensaje-error";
    p.textContent = "No se pudo cargar el historial: " + e.message;
    lista.appendChild(p);
    return;
  }
  const items = datos.items || [];
  $("#btn-limpiar-historial").hidden = items.length === 0;
  if (!items.length) {
    lista.innerHTML =
      '<div class="estado-vacio">' + ICONO.nota +
      "<h2>Sin descargas todavía</h2>" +
      "<p>Cuando completes descargas, quedarán registradas aquí.</p></div>";
    return;
  }
  let html = "";
  for (const h of items) {
    html +=
      '<div class="hist-item">' +
        "<div>" +
          '<p class="hist-titulo">' + esc(h.titulo || h.url) + "</p>" +
          '<p class="hist-sub">' + esc(h.canal || "") +
          (h.carpeta ? " · descargas/" + esc(h.carpeta) : "") + "</p>" +
        "</div>" +
        '<span class="hist-fecha">' + esc(formatearFecha(h.completado)) + "</span>" +
        '<button type="button" class="btn-icono hist-quitar" data-id="' + esc(h.id) +
          '" aria-label="Quitar del historial: ' + esc(h.titulo || h.url) + '">' + ICONO.quitar + "</button>" +
      "</div>";
  }
  lista.innerHTML = html;

  $$("#historial-lista .hist-quitar").forEach((b) =>
    b.addEventListener("click", () => eliminarHistorial(b.dataset.id))
  );
}

async function eliminarHistorial(id) {
  try {
    await pedirJSON("/api/historial/eliminar", { method: "POST", body: JSON.stringify({ id: id }) });
    cargarHistorial();
  } catch (e) {
    avisar("No se pudo quitar del historial: " + e.message, "error");
  }
}

async function limpiarHistorial() {
  const ok = await confirmar({
    titulo: "Vaciar el historial",
    mensaje: "Se borrará todo el registro de descargas.\nLos archivos descargados no se tocan.",
    textoOk: "Vaciar historial",
  });
  if (!ok) return;
  try {
    const r = await pedirJSON("/api/historial/limpiar", { method: "POST" });
    avisar("Historial vaciado (" + (r.eliminados || 0) + " entradas).", "ok");
    cargarHistorial();
  } catch (e) {
    avisar("No se pudo limpiar el historial: " + e.message, "error");
  }
}

function iniciarHistorial() {
  $("#btn-limpiar-historial").addEventListener("click", limpiarHistorial);
}

// ---------------------------------------------------------------------------
// Reproductor
// ---------------------------------------------------------------------------

function reproducirLista(items, indice) {
  // Instantánea: la lista de reproducción es la biblioteca tal y como se ve
  // en este momento. Filtrar o recargar la biblioteca después NO cambia la
  // cola de reproducción (evita saltos a pistas arbitrarias).
  estado.rep.lista = items.slice();
  estado.rep.indice = indice;
  estado.rep.historialAleatorio = [indice];
  reproducirActual();
}

function reproducirActual() {
  const pista = estado.rep.lista[estado.rep.indice];
  if (!pista) return;
  cerrarPreview(); // la biblioteca recupera el sonido y la ventana de vídeo
  estado.rep.archivo = pista.archivo;
  estado.rep.tipo = pista.tipo === "video" ? "video" : "audio";
  audio.src = urlAudio(pista.archivo);
  // La velocidad elegida solo vale para los vídeos (su selector vive en el
  // escenario); la música suena siempre a velocidad normal.
  const velocidad = estado.rep.tipo === "video" ? estado.video.velocidad : 1;
  audio.defaultPlaybackRate = velocidad;
  audio.playbackRate = velocidad;
  const promesa = audio.play();
  if (promesa && promesa.catch) {
    promesa.catch((e) => {
      // Cambiar de pista rápido aborta el play() anterior: no es un error real.
      if (e && e.name === "AbortError") return;
      // Un medio que no carga ya lo cuenta el evento 'error', y en español.
      if (e && e.name === "NotSupportedError") return;
      avisar("No se pudo reproducir: " + (e && e.message ? e.message : e), "error");
    });
  }
  // Un vídeo abre el escenario automáticamente; una pista de audio lo cierra.
  if (estado.rep.tipo === "video") {
    mostrarEscenarioVideo(pista);
  } else {
    ocultarEscenarioVideo(false);
  }
  actualizarBarraReproductor(pista);
  actualizarMediaSession(pista);
  marcarPistaActiva();
}

function actualizarBarraReproductor(pista) {
  const esVideo = pista && estado.rep.tipo === "video";
  $("#rep-titulo").textContent = pista ? pista.titulo : "Nada en reproducción";
  $("#rep-artista").textContent = pista
    ? (pista.artista || pista.carpeta || "—")
    : "Elige una pista en la biblioteca";
  $("#btn-abrir-carpeta").hidden = !pista;
  // El botón "mostrar vídeo" solo tiene sentido con un vídeo oculto.
  $("#btn-mostrar-video").hidden = !(esVideo && !estado.rep.videoVisible);
  $("#eq").classList.toggle("visible", Boolean(pista));
  $("#seek").disabled = !pista;
}

// --------------------------- Escenario de vídeo --------------------------- //
//
// El vídeo se ve de tres maneras: en una ventana flotante que se coloca y se
// dimensiona a mano (arrastrando su barra o sus bordes), en modo teatro (toda
// la zona de contenido) o a pantalla completa. La posición, el tamaño y el
// modo se guardan en la configuración del backend, igual que el volumen: la
// ventana de la app usa un perfil privado y un puerto distinto en cada
// arranque, así que localStorage no sobrevive al cierre.
//
// La misma ventana sirve a los vídeos de la biblioteca y a la vista previa de
// los resultados del buscador (el reproductor incrustado de YouTube): solo se
// ve una de las dos cosas a la vez y comparten posición, tamaño y modo.

const VIDEO_LADO_POR_DEFECTO = 480;   // px (o el 44 % de la ventana si es menos)
const VIDEO_ANCHO_MINIMO = 280;       // px: por debajo no caben los controles
const VIDEO_PASO_TECLADO = 24;        // px por pulsación al mover o redimensionar
const VIDEO_ESPERA_CONTROLES = 2600;  // ms sin actividad antes de esconderlos

function enPantallaCompleta() {
  return document.fullscreenElement === escenario;
}

// Zona en la que puede vivir la ventana flotante: toda la ventana de la app
// salvo la barra de reproducción, que debe quedar siempre a mano.
function zonaVideo() {
  return {
    ancho: window.innerWidth,
    alto: window.innerHeight - $("#reproductor").offsetHeight,
  };
}

// Alto de lo que rodea a la imagen: la barra de título y, en la vista previa,
// el pie con el botón de añadir a la cola.
function altoCromoVideo() {
  return $("#ev-barra").offsetHeight + $("#ev-pie").offsetHeight;
}

// La ventana toma la forma de lo que enseña (vertical, 4:3, panorámico…).
function fijarProporcionVideo(proporcion) {
  estado.video.proporcion = limitar(proporcion, 0.4, 3);
  escenario.style.setProperty("--ev-proporcion", String(estado.video.proporcion));
  aplicarGeometriaVideo();
}

// Tamaño que el usuario quiere para la ventana, medido en el LADO LARGO de la
// imagen: así un vídeo vertical ocupa más o menos lo mismo que uno apaisado
// en lugar de dispararse en altura. Lo que se pinta puede ser menor.
function ladoVideoDeseado() {
  return estado.video.geometria
    ? estado.video.geometria.lado
    : Math.min(VIDEO_LADO_POR_DEFECTO, zonaVideo().ancho * 0.44);
}

// Parte del lado largo que corresponde al ancho (1 salvo en vídeos verticales).
function factorAnchoVideo() {
  return Math.min(1, estado.video.proporcion);
}

// Encaja la geometría deseada en la zona disponible respetando la proporción
// del vídeo. Devuelve lo que se pinta SIN tocar la preferencia: una ventana
// pequeña o un vídeo vertical la estrechan solo mientras duren.
function encajarGeometriaVideo() {
  const deseada = estado.video.geometria;
  const zona = zonaVideo();
  const altoCromo = altoCromoVideo();
  const prop = estado.video.proporcion;
  const maximo = Math.max(1, Math.min(zona.ancho, (zona.alto - altoCromo) * prop));
  const ancho = limitar(
    ladoVideoDeseado() * factorAnchoVideo(),
    Math.min(VIDEO_ANCHO_MINIMO, maximo),
    maximo
  );
  const alto = altoCromo + ancho / prop;
  // Sin posición elegida: esquina inferior derecha, sobre la barra de reproducción.
  const x = deseada ? deseada.x : zona.ancho - ancho - 18;
  const y = deseada ? deseada.y : zona.alto - alto - 14;
  return {
    x: limitar(x, 0, Math.max(0, zona.ancho - ancho)),
    y: limitar(y, 0, Math.max(0, zona.alto - alto)),
    ancho: ancho,
  };
}

function aplicarGeometriaVideo() {
  if (escenario.hidden) return;
  if (estado.video.modo !== "flotante" || enPantallaCompleta()) {
    // Teatro y pantalla completa se colocan solos desde el CSS.
    escenario.style.left = "";
    escenario.style.top = "";
    escenario.style.width = "";
    return;
  }
  const g = encajarGeometriaVideo();
  escenario.style.left = g.x + "px";
  escenario.style.top = g.y + "px";
  escenario.style.width = g.ancho + "px";
}

const guardarGeometriaVideo = debounce(() => {
  guardarConfig({ video_geometria: estado.video.geometria });
}, 400);

// Da por buena la geometría tras un gesto: se guarda lo que quedó en pantalla,
// no hasta dónde llegó el puntero. Al mover se conserva el tamaño deseado (una
// ventana de la app pequeña no debe encoger el vídeo para siempre).
function asentarGeometriaVideo(conservarLado) {
  const g = encajarGeometriaVideo();
  estado.video.geometria = {
    x: g.x,
    y: g.y,
    lado: conservarLado ? ladoVideoDeseado() : g.ancho / factorAnchoVideo(),
  };
  aplicarGeometriaVideo();
  guardarGeometriaVideo();
}

// Devuelve la ventana a su esquina y tamaño por defecto.
function restablecerGeometriaVideo() {
  estado.video.geometria = null;
  aplicarGeometriaVideo();
  guardarGeometriaVideo();
}

function fijarModoVideo(modo) {
  if (estado.video.modo === modo) return;
  estado.video.modo = modo;
  guardarConfig({ video_modo: modo });
  reflejarEscenario();
}

function alternarTeatro() {
  if (enPantallaCompleta()) return;
  fijarModoVideo(estado.video.modo === "teatro" ? "flotante" : "teatro");
}

// Pantalla completa sobre el escenario entero (no sobre el <video>), para que
// sigan a la vista nuestros controles en lugar de los nativos del navegador.
function alternarPantallaCompleta() {
  if (document.fullscreenElement) {
    document.exitFullscreen();
  } else if (escenario.requestFullscreen) {
    escenario.requestFullscreen().catch(() => {});
  }
}

// Pone el escenario acorde con su modo: clases, botones, foco y geometría.
function reflejarEscenario() {
  const completa = enPantallaCompleta();
  const teatro = estado.video.modo === "teatro";
  escenario.classList.toggle("modo-teatro", teatro);
  const btnTeatro = $("#btn-video-teatro");
  btnTeatro.setAttribute("aria-pressed", String(teatro));
  btnTeatro.hidden = completa; // a pantalla completa no hay teatro que alternar
  const btnPantalla = $("#btn-video-pantalla");
  btnPantalla.setAttribute("aria-pressed", String(completa));
  btnPantalla.querySelector(".icono-entrar").toggleAttribute("hidden", completa);
  btnPantalla.querySelector(".icono-salir").toggleAttribute("hidden", !completa);
  // Vista previa: el reproductor de YouTube ocupa el marco, con su pie y su
  // botón de cerrar en lugar del de ocultar.
  const previa = Boolean(estado.video.previa);
  escenario.classList.toggle("es-previa", previa);
  $("#ev-previa").hidden = !previa;
  $("#ev-pie").hidden = !previa;
  $("#btn-video-ocultar").hidden = previa;
  $("#btn-preview-cerrar").hidden = !previa;
  // Lo que el vídeo tapa no debe recibir el foco ni clics a ciegas.
  $(".principal").inert = !escenario.hidden && (teatro || completa);
  $(".sidebar").inert = completa;
  $("#reproductor").inert = completa;
  aplicarGeometriaVideo();
}

function mostrarEscenarioVideo(pista) {
  cerrarPreview(); // la ventana es una sola: la vista previa la cede
  estado.rep.videoVisible = true;
  escenario.hidden = false;
  $("#ev-titulo").textContent = pista ? pista.titulo : "";
  $("#btn-mostrar-video").hidden = true;
  // La vista previa pudo dejar la ventana apaisada: recupera la forma del vídeo.
  if (audio.videoWidth && audio.videoHeight) {
    fijarProporcionVideo(audio.videoWidth / audio.videoHeight);
  }
  reflejarEscenario();
  despertarControlesVideo();
}

// Oculta el escenario. La reproducción (audio del vídeo) sigue salvo que
// ``pausar`` sea true.
function ocultarEscenarioVideo(pausar) {
  estado.rep.videoVisible = false;
  // Si la ventana la ocupa la vista previa, este vídeo ya no estaba a la vista.
  if (!estado.video.previa) {
    if (enPantallaCompleta()) document.exitFullscreen();
    escenario.hidden = true;
    reflejarEscenario();
  }
  if (pausar) audio.pause();
  // Si lo que suena es un vídeo, ofrecemos volver a mostrarlo.
  $("#btn-mostrar-video").hidden = !(estado.rep.tipo === "video" && estado.rep.archivo);
}

let temporizadorControlesVideo = null;

// Enseña los controles del vídeo y programa su ocultación. En pausa se quedan
// a la vista, y también mientras se usan: con el foco del teclado dentro, con
// el puntero encima o arrastrando la posición.
function despertarControlesVideo() {
  escenario.classList.remove("inactivo");
  clearTimeout(temporizadorControlesVideo);
  // La vista previa no tiene controles nuestros que esconder.
  if (audio.paused || estado.video.previa) return;
  temporizadorControlesVideo = setTimeout(() => {
    const enUso = estado.rep.arrastrandoSeek ||
      escenario.querySelector(
        ":focus-visible, select:open, .ev-controles:hover, .ev-barra:hover"
      );
    if (enUso) {
      despertarControlesVideo();
    } else {
      escenario.classList.add("inactivo");
    }
  }, VIDEO_ESPERA_CONTROLES);
}

// Mensaje sobre el vídeo (no se puede reproducir, no trae imagen…); '' lo quita.
function avisoVideo(mensaje) {
  const caja = $("#ev-aviso");
  caja.textContent = mensaje;
  caja.hidden = !mensaje;
}

// Mover (arrastrando la barra) y redimensionar (tirando de los bordes) la
// ventana flotante, con alternativa de teclado en el botón de agarre.
function iniciarVentanaVideo() {
  const barra = $("#ev-barra");
  const asas = $$("#escenario-video .ev-asa");
  let gesto = null; // gesto de puntero en curso

  function empezar(e, dir) {
    if (e.button !== 0 || estado.video.modo !== "flotante" || enPantallaCompleta()) return;
    const r = escenario.getBoundingClientRect();
    gesto = {
      dir: dir, // asa de la que se tira; '' si se mueve la ventana entera
      x0: e.clientX,
      y0: e.clientY,
      caja: { x: r.left, y: r.top, ancho: r.width, alto: r.height },
      ladoDeseado: ladoVideoDeseado(),
      movido: false,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
    e.preventDefault(); // sin selección de texto ni arrastre nativo
  }

  // Geometría resultante de tirar de un asa. La proporción manda (el alto
  // sigue al ancho) y el borde opuesto al asa se queda donde estaba.
  function redimensionar(g, dx, dy) {
    const zona = zonaVideo();
    const altoCromo = altoCromoVideo();
    const prop = estado.video.proporcion;
    const derecha = g.caja.x + g.caja.ancho;
    const abajo = g.caja.y + g.caja.alto;
    const haciaOeste = g.dir.includes("o");
    const haciaNorte = g.dir.includes("n");
    // Ancho que pide cada eje del gesto; en las esquinas gana el mayor.
    let ancho = 0;
    if (haciaOeste || g.dir.includes("e")) {
      ancho = g.caja.ancho + (haciaOeste ? -dx : dx);
    }
    if (haciaNorte || g.dir.includes("s")) {
      const altoMarco = g.caja.alto - altoCromo + (haciaNorte ? -dy : dy);
      ancho = Math.max(ancho, altoMarco * prop);
    }
    // Sin crecer más allá del hueco que queda desde el borde anclado.
    const huecoAncho = haciaOeste ? derecha : zona.ancho - g.caja.x;
    const huecoAlto = haciaNorte ? abajo : zona.alto - g.caja.y;
    const maximo = Math.max(1, Math.min(huecoAncho, (huecoAlto - altoCromo) * prop));
    ancho = limitar(ancho, Math.min(VIDEO_ANCHO_MINIMO, maximo), maximo);
    const alto = altoCromo + ancho / prop;
    return {
      x: haciaOeste ? derecha - ancho : g.caja.x,
      y: haciaNorte ? abajo - alto : g.caja.y,
      lado: ancho / factorAnchoVideo(),
    };
  }

  function seguir(e) {
    if (!gesto) return;
    const dx = e.clientX - gesto.x0;
    const dy = e.clientY - gesto.y0;
    if (!gesto.movido) {
      // Un clic sin desplazamiento no cuenta: no debe fijar la posición.
      if (Math.abs(dx) < 3 && Math.abs(dy) < 3) return;
      gesto.movido = true;
      escenario.classList.add("arrastrando");
    }
    estado.video.geometria = gesto.dir
      ? redimensionar(gesto, dx, dy)
      : { x: gesto.caja.x + dx, y: gesto.caja.y + dy, lado: gesto.ladoDeseado };
    aplicarGeometriaVideo();
  }

  function terminar() {
    if (!gesto) return;
    const g = gesto;
    gesto = null;
    escenario.classList.remove("arrastrando");
    if (g.movido) asentarGeometriaVideo(!g.dir);
  }

  barra.addEventListener("pointerdown", (e) => {
    // Los botones de la barra no arrastran (salvo el de agarre, que es para eso).
    if (e.target.closest("button:not(.ev-agarre)")) return;
    empezar(e, "");
  });
  asas.forEach((asa) => {
    asa.addEventListener("pointerdown", (e) => empezar(e, asa.dataset.dir));
  });
  [barra].concat(asas).forEach((el) => {
    el.addEventListener("pointermove", seguir);
    el.addEventListener("pointerup", terminar);
    el.addEventListener("pointercancel", terminar);
  });

  // Doble clic en la barra: alterna el modo teatro (como maximizar una ventana).
  barra.addEventListener("dblclick", (e) => {
    if (!e.target.closest("button")) alternarTeatro();
  });

  // Alternativa de teclado al arrastre, en el botón de agarre.
  $("#btn-video-mover").addEventListener("keydown", (e) => {
    const flechas = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    if (e.key === "Home") {
      e.preventDefault();
      restablecerGeometriaVideo();
      return;
    }
    const d = flechas[e.key];
    if (!d) return;
    e.preventDefault(); // que la flecha no llegue a los atajos globales
    const g = encajarGeometriaVideo();
    if (e.shiftKey) {
      // Mayús + flecha cambia el tamaño: → y ↑ agrandan, ← y ↓ encogen.
      const signo = e.key === "ArrowRight" || e.key === "ArrowUp" ? 1 : -1;
      estado.video.geometria = {
        x: g.x,
        y: g.y,
        lado: (g.ancho + signo * VIDEO_PASO_TECLADO) / factorAnchoVideo(),
      };
      asentarGeometriaVideo(false);
    } else {
      estado.video.geometria = {
        x: g.x + d[0] * VIDEO_PASO_TECLADO,
        y: g.y + d[1] * VIDEO_PASO_TECLADO,
        lado: ladoVideoDeseado(),
      };
      asentarGeometriaVideo(true);
    }
  });

  // Al cambiar el tamaño de la app, la ventana de vídeo se recoloca dentro.
  window.addEventListener("resize", aplicarGeometriaVideo);
}

// Marca la fila activa en la biblioteca sin re-renderizarla entera.
function marcarPistaActiva() {
  $$("#biblioteca-lista .pista").forEach((fila) => {
    const activa = fila.dataset.archivo === estado.rep.archivo;
    fila.classList.toggle("activa", activa);
    const btn = fila.querySelector(".pista-play");
    if (btn) {
      btn.innerHTML = activa && !audio.paused ? ICONO.pausa : ICONO.play;
    }
  });
}

function alternarPlay() {
  if (!estado.rep.archivo) {
    // Nada sonando: reproduce la biblioteca desde el principio si hay pistas.
    if (estado.biblioteca.items.length) reproducirLista(estado.biblioteca.items, 0);
    return;
  }
  if (audio.paused) {
    cerrarPreview(); // la pista y la vista previa no deben sonar a la vez
    const p = audio.play();
    if (p && p.catch) p.catch(() => {});
  } else {
    audio.pause();
  }
}

function indiceSiguiente() {
  const n = estado.rep.lista.length;
  if (!n) return -1;
  if (estado.rep.aleatorio) {
    // Con una sola pista no hay "otra" a la que saltar: se trata como fin de
    // lista para que decida el modo repetir (off = parar, all/one = repetir).
    if (n === 1) return -1;
    let idx;
    do {
      idx = Math.floor(Math.random() * n);
    } while (idx === estado.rep.indice);
    return idx;
  }
  return estado.rep.indice + 1 < n ? estado.rep.indice + 1 : -1;
}

function siguiente(automatico) {
  if (!estado.rep.lista.length) return;
  if (automatico && estado.rep.repetir === "one") {
    audio.currentTime = 0;
    const p = audio.play();
    if (p && p.catch) p.catch(() => {});
    return;
  }
  let idx = indiceSiguiente();
  if (idx === -1) {
    if (estado.rep.repetir === "all" || !automatico) {
      idx = 0; // vuelve al principio
    } else {
      audio.pause();
      return; // fin de la lista sin repetición
    }
  }
  estado.rep.indice = idx;
  estado.rep.historialAleatorio.push(idx);
  if (estado.rep.historialAleatorio.length > 200) estado.rep.historialAleatorio.shift();
  reproducirActual();
}

function anterior() {
  if (!estado.rep.lista.length) return;
  // Si llevamos más de 3 s de pista, "anterior" reinicia la pista (como Spotify).
  if (audio.currentTime > 3) {
    audio.currentTime = 0;
    return;
  }
  if (estado.rep.aleatorio && estado.rep.historialAleatorio.length > 1) {
    estado.rep.historialAleatorio.pop();
    estado.rep.indice =
      estado.rep.historialAleatorio[estado.rep.historialAleatorio.length - 1];
  } else {
    estado.rep.indice =
      estado.rep.indice > 0 ? estado.rep.indice - 1 : estado.rep.lista.length - 1;
    // Mantener el historial coherente también en el camino no aleatorio: si
    // luego se activa aleatorio, "anterior" debe volver a esta pista.
    estado.rep.historialAleatorio.push(estado.rep.indice);
  }
  reproducirActual();
}

function actualizarMediaSession(pista) {
  if (!("mediaSession" in navigator)) return;
  try {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: pista.titulo || "",
      artist: pista.artista || "",
      album: pista.album || "Sonora",
    });
  } catch (e) {
    /* MediaMetadata no disponible: sin integración con el SO, sin más */
  }
}

// Salta ``segundos`` adelante (o atrás, si es negativo) en la pista actual.
function saltar(segundos) {
  if (!estado.rep.archivo || !audio.duration) return;
  audio.currentTime = limitar(audio.currentTime + segundos, 0, audio.duration);
}

const guardarVolumen = debounce(() => {
  guardarConfig({ volumen: audio.volume });
}, 400);

// Cambia el volumen por orden del usuario y lo recuerda para la próxima vez.
function fijarVolumen(v) {
  audio.muted = false;
  audio.volume = limitar(v, 0, 1);
  guardarVolumen();
}

function alternarSilencio() {
  if (audio.muted || audio.volume === 0) {
    audio.muted = false;
    // Quitar el silencio con el volumen a cero no devolvería el sonido.
    if (audio.volume === 0) fijarVolumen(0.5);
  } else {
    audio.muted = true;
  }
}

function iniciarEscenarioVideo() {
  const marco = $("#ev-marco");
  const video = audio; // el <video id="media">

  $("#btn-mostrar-video").addEventListener("click", () => {
    mostrarEscenarioVideo(estado.rep.lista[estado.rep.indice]);
  });
  $("#btn-video-ocultar").addEventListener("click", () => {
    ocultarEscenarioVideo(false);
    // El foco pasa al botón que deshace la acción, en vez de perderse.
    const mostrar = $("#btn-mostrar-video");
    if (!mostrar.hidden) mostrar.focus();
  });
  $("#btn-video-teatro").addEventListener("click", alternarTeatro);
  $("#btn-video-pantalla").addEventListener("click", alternarPantallaCompleta);
  $("#btn-video-play").addEventListener("click", alternarPlay);
  $("#btn-video-silencio").addEventListener("click", alternarSilencio);

  $("#ev-velocidad").addEventListener("change", (e) => {
    estado.video.velocidad = Number(e.currentTarget.value) || 1;
    video.defaultPlaybackRate = estado.video.velocidad;
    video.playbackRate = estado.video.velocidad;
  });

  // Clic en el vídeo = play/pausa; doble clic = pantalla completa (los dos
  // clics del doble se anulan entre sí, así que la reproducción no cambia).
  marco.addEventListener("click", (e) => {
    if (e.target === video || e.target === marco) alternarPlay();
  });
  marco.addEventListener("dblclick", (e) => {
    if (e.target === video || e.target === marco) alternarPantallaCompleta();
  });

  // El reproductor de YouTube de la vista previa trae su propio botón de
  // pantalla completa. Pulsado con la de la app ya puesta, el navegador apila
  // una sobre otra y de la de YouTube ya no se sale con su botón. Quien lo
  // pulsa ahí lo que quiere es alternar, así que se deshacen las dos.
  let completoAntes = null;
  let saliendoDelTodo = false;

  // Al entrar o salir de pantalla completa (también la del reproductor de la
  // vista previa) la ventana de la app tiene que acompañar: WebView2 solo
  // agranda el elemento hasta el borde de la ventana (ver escritorio.py).
  document.addEventListener("fullscreenchange", () => {
    const ahora = document.fullscreenElement;
    if (completoAntes === escenario && ahora && ahora !== escenario) saliendoDelTodo = true;
    completoAntes = ahora;
    if (saliendoDelTodo) {
      if (ahora) {
        // Cada llamada deshace un nivel; el siguiente aviso trae el de debajo.
        document.exitFullscreen().catch(() => {
          saliendoDelTodo = false;
          reflejarEscenario();
        });
        return;
      }
      saliendoDelTodo = false;
    }
    const api = window.pywebview && window.pywebview.api;
    if (api && typeof api.pantalla_completa === "function") {
      const aviso = api.pantalla_completa(Boolean(ahora));
      if (aviso && aviso.catch) aviso.catch(() => {});
    }
    reflejarEscenario();
    despertarControlesVideo();
  });

  // Cualquier actividad sobre el escenario enseña los controles.
  for (const tipo of ["pointermove", "pointerdown", "keydown", "focusin"]) {
    escenario.addEventListener(tipo, despertarControlesVideo);
  }
  video.addEventListener("play", despertarControlesVideo);
  video.addEventListener("pause", despertarControlesVideo);

  // Rueda de espera mientras falta señal.
  const espera = $("#ev-espera");
  video.addEventListener("waiting", () => {
    espera.hidden = false;
  });
  for (const tipo of ["playing", "canplay", "error", "emptied"]) {
    video.addEventListener(tipo, () => {
      espera.hidden = true;
    });
  }

  video.addEventListener("loadstart", () => avisoVideo(""));
  video.addEventListener("loadedmetadata", () => {
    if (estado.rep.tipo !== "video") return;
    if (video.videoWidth && video.videoHeight) {
      fijarProporcionVideo(video.videoWidth / video.videoHeight);
    } else {
      avisoVideo("Este vídeo no trae una imagen que la app sepa mostrar: solo se oye el audio.");
    }
  });

  iniciarVentanaVideo();
}

function iniciarReproductor() {
  const btnPlay = $("#btn-play");
  const seek = $("#seek");
  const volumen = $("#volumen");

  iniciarEscenarioVideo();

  btnPlay.addEventListener("click", alternarPlay);
  $("#btn-siguiente").addEventListener("click", () => siguiente(false));
  $("#btn-anterior").addEventListener("click", anterior);

  $("#btn-aleatorio").addEventListener("click", (e) => {
    estado.rep.aleatorio = !estado.rep.aleatorio;
    e.currentTarget.setAttribute("aria-pressed", String(estado.rep.aleatorio));
  });

  $("#btn-repetir").addEventListener("click", (e) => {
    const orden = { off: "all", all: "one", one: "off" };
    estado.rep.repetir = orden[estado.rep.repetir];
    const activo = estado.rep.repetir !== "off";
    e.currentTarget.setAttribute("aria-pressed", String(activo));
    e.currentTarget.querySelector(".repetir-uno").hidden = estado.rep.repetir !== "one";
    e.currentTarget.setAttribute(
      "aria-label",
      estado.rep.repetir === "one" ? "Repetir: una pista" :
      estado.rep.repetir === "all" ? "Repetir: toda la lista" : "Repetir"
    );
  });

  // Estado visual play/pausa + ecualizador. El botón de la barra y el de los
  // controles del vídeo van a la par.
  function reflejarEstado() {
    const sonando = !audio.paused && estado.rep.archivo;
    for (const btn of [btnPlay, $("#btn-video-play")]) {
      // toggleAttribute, no la propiedad .hidden: los <svg> no son HTMLElement
      // y la propiedad no les pone el atributo (y por tanto no los oculta).
      btn.querySelector(".icono-play").toggleAttribute("hidden", Boolean(sonando));
      btn.querySelector(".icono-pausa").toggleAttribute("hidden", !sonando);
      btn.setAttribute("aria-label", sonando ? "Pausar" : "Reproducir");
    }
    escenario.classList.toggle("en-pausa", !sonando);
    $("#eq").classList.toggle("activo", Boolean(sonando));
    marcarPistaActiva();
  }
  audio.addEventListener("play", reflejarEstado);
  audio.addEventListener("pause", reflejarEstado);
  reflejarEstado();

  audio.addEventListener("ended", () => siguiente(true));

  audio.addEventListener("error", () => {
    if (!estado.rep.archivo) return;
    if (estado.rep.tipo === "video") {
      // El aviso va sobre el propio vídeo (role="alert"): sin toast duplicado.
      avisoVideo("No se puede reproducir este vídeo: falta el archivo o la app no admite " +
        "su formato. Puedes abrirlo desde su carpeta con otro reproductor.");
    } else {
      avisar("No se pudo cargar el audio de esta pista.", "error");
    }
  });

  // Posición: dos deslizadores (el de la barra y el de los controles del
  // vídeo) sobre el mismo medio.
  const seeks = [seek, $("#ev-seek")];

  function pintarPosicion(segundos) {
    const duracion = audio.duration || 0;
    const pct = duracion ? (segundos / duracion) * 100 : 0;
    for (const s of seeks) {
      s.value = String(pct);
      pintarRango(s, pct);
    }
    $("#tiempo-actual").textContent = formatearTiempo(segundos);
    $("#ev-tiempo").textContent = formatearTiempo(segundos) + " / " + formatearTiempo(duracion);
  }

  // Tramo ya cargado a partir de la posición actual (lo enseña el deslizador
  // del vídeo, más claro que el resto de la pista).
  function pintarCargado() {
    let fin = 0;
    for (let i = 0; i < audio.buffered.length; i++) {
      if (audio.buffered.start(i) <= audio.currentTime && audio.currentTime <= audio.buffered.end(i)) {
        fin = audio.buffered.end(i);
      }
    }
    const pct = audio.duration ? (fin / audio.duration) * 100 : 0;
    $("#ev-seek").style.setProperty("--buf", pct + "%");
  }

  audio.addEventListener("loadedmetadata", () => {
    $("#tiempo-total").textContent = formatearTiempo(audio.duration);
    pintarPosicion(audio.currentTime);
  });
  // Seek: mientras se arrastra, el timeupdate no debe pisar el valor.
  audio.addEventListener("timeupdate", () => {
    pintarCargado();
    if (estado.rep.arrastrandoSeek || !audio.duration) return;
    pintarPosicion(audio.currentTime);
  });
  audio.addEventListener("progress", pintarCargado);
  // Al cambiar de pista no debe quedar a la vista el tiempo de la anterior.
  audio.addEventListener("emptied", () => {
    $("#tiempo-total").textContent = formatearTiempo(0);
    pintarPosicion(0);
    pintarCargado();
  });

  for (const s of seeks) {
    s.addEventListener("pointerdown", () => {
      estado.rep.arrastrandoSeek = true;
    });
    // El flag debe soltarse SIEMPRE al levantar el puntero: si el usuario suelta
    // sin cambiar el valor, 'change' no dispara y la barra quedaría congelada.
    s.addEventListener("pointerup", () => {
      estado.rep.arrastrandoSeek = false;
    });
    s.addEventListener("pointercancel", () => {
      estado.rep.arrastrandoSeek = false;
    });
    s.addEventListener("input", () => {
      if (audio.duration) {
        pintarPosicion((Number(s.value) / 100) * audio.duration);
      } else {
        pintarRango(s, Number(s.value));
      }
    });
    s.addEventListener("change", () => {
      estado.rep.arrastrandoSeek = false;
      if (audio.duration) {
        audio.currentTime = (Number(s.value) / 100) * audio.duration;
      }
    });
  }

  // Volumen: dos deslizadores y el botón de silencio, todos reflejo del propio
  // medio. El valor inicial llega con la configuración (cargarConfig).
  const volumenes = [volumen, $("#ev-volumen")];

  function reflejarVolumen() {
    const v = audio.muted ? 0 : audio.volume;
    for (const s of volumenes) {
      s.value = String(v);
      pintarRango(s, v * 100);
    }
    const btnSilencio = $("#btn-video-silencio");
    btnSilencio.setAttribute("aria-pressed", String(audio.muted));
    btnSilencio.querySelector(".icono-sonido").toggleAttribute("hidden", v === 0);
    btnSilencio.querySelector(".icono-silencio").toggleAttribute("hidden", v !== 0);
  }
  audio.addEventListener("volumechange", reflejarVolumen);
  for (const s of volumenes) {
    s.addEventListener("input", () => fijarVolumen(Number(s.value)));
  }
  reflejarVolumen();

  $("#btn-abrir-carpeta").addEventListener("click", () => {
    if (estado.rep.archivo) abrirCarpetaDe(estado.rep.archivo);
  });

  // Integración con las teclas multimedia del sistema.
  if ("mediaSession" in navigator) {
    try {
      navigator.mediaSession.setActionHandler("play", alternarPlay);
      navigator.mediaSession.setActionHandler("pause", alternarPlay);
      navigator.mediaSession.setActionHandler("previoustrack", anterior);
      navigator.mediaSession.setActionHandler("nexttrack", () => siguiente(false));
      navigator.mediaSession.setActionHandler("seekbackward", () => saltar(-10));
      navigator.mediaSession.setActionHandler("seekforward", () => saltar(10));
    } catch (e) {
      /* algún handler no soportado: seguimos sin él */
    }
  }

  // Atajos del reproductor. Devuelve true si la tecla se ha usado.
  function atajoReproductor(e) {
    const hayVideo = !escenario.hidden;
    const completa = enPantallaCompleta();
    const teatro = estado.video.modo === "teatro";
    // Los de la ventana de vídeo valen también para la vista previa.
    if (hayVideo) {
      switch (e.key) {
        case "f": case "F": alternarPantallaCompleta(); return true;
        case "t": case "T":
          if (completa) return false;
          alternarTeatro();
          return true;
        case "Escape":
          // Escape deshace un paso: de teatro a ventana y, ya en ventana,
          // cierra la vista previa (de pantalla completa saca el navegador).
          if (completa) return false;
          if (teatro) {
            fijarModoVideo("flotante");
            return true;
          }
          if (estado.video.previa) {
            cerrarPreview();
            return true;
          }
          return false;
        default: break;
      }
    }
    // Los de la pista. Con la vista previa abierta lo que suena es YouTube,
    // que tiene sus propios atajos dentro de su reproductor.
    if (!estado.rep.archivo || estado.video.previa) return false;
    // ↑/↓ mueven el volumen solo cuando el vídeo tiene el protagonismo; en el
    // resto de la app esas teclas desplazan las listas.
    const videoAlFrente = hayVideo &&
      (teatro || completa || escenario.contains(document.activeElement));
    switch (e.key) {
      case "ArrowLeft": saltar(-5); return true;
      case "ArrowRight": saltar(5); return true;
      case "ArrowUp":
        if (!videoAlFrente) return false;
        fijarVolumen(audio.volume + 0.05);
        return true;
      case "ArrowDown":
        if (!videoAlFrente) return false;
        fijarVolumen(audio.volume - 0.05);
        return true;
      case "m": case "M": alternarSilencio(); return true;
      default: return false;
    }
  }

  // Atajos de teclado: espacio = play/pausa, "/" = ir al buscador, y los del
  // reproductor (saltos, volumen, silencio, teatro y pantalla completa).
  document.addEventListener("keydown", (e) => {
    // Quien ya ha usado la tecla (p. ej. el botón de agarre del vídeo) manda.
    if (e.defaultPrevented) return;
    const tag = (e.target && e.target.tagName) || "";
    const escribiendo = tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA";
    const dialogoAbierto = Boolean(document.querySelector("dialog[open]"));
    // Espacio solo actúa como play/pausa si el foco NO está en un control que
    // ya use Espacio para activarse (botones, summary de los lotes, enlaces).
    const enControl = e.target && e.target.closest &&
      e.target.closest("button, summary, a, input, select, textarea");
    if (e.key === " " && !enControl && !dialogoAbierto && !estado.video.previa) {
      e.preventDefault();
      alternarPlay();
    }
    if (e.key === "/" && !escribiendo && !dialogoAbierto && !enPantallaCompleta()) {
      e.preventDefault();
      cambiarVista("buscar");
      $("#campo-buscar").focus();
    }
    if (escribiendo || dialogoAbierto || e.ctrlKey || e.altKey || e.metaKey) return;
    if (atajoReproductor(e)) {
      e.preventDefault();
      despertarControlesVideo();
    }
  });
}

// ---------------------------------------------------------------------------
// Diálogo de confirmación propio (en vez de window.confirm, que muestra el
// "127.0.0.1 dice…" del navegador y desentona en una app de escritorio)
// ---------------------------------------------------------------------------

// Devuelve una promesa que resuelve true si el usuario confirma.
// opciones: { titulo, mensaje, textoOk, peligro }
function confirmar(opciones) {
  const opts = opciones || {};
  return new Promise((resolve) => {
    const dlg = $("#dialogo-confirmar");
    $("#conf-titulo").textContent = opts.titulo || "¿Confirmar?";
    $("#conf-mensaje").textContent = opts.mensaje || "";
    const btnOk = $("#conf-ok");
    btnOk.textContent = opts.textoOk || "Aceptar";
    // Rojo para acciones destructivas, el acento para el resto.
    btnOk.classList.toggle("btn-peligro", opts.peligro !== false);
    btnOk.classList.toggle("btn-acento", opts.peligro === false);
    function alCerrar() {
      dlg.removeEventListener("close", alCerrar);
      // <form method="dialog">: el botón pulsado fija returnValue con su value.
      // Escape o "Cancelar" dejan un valor distinto de "ok" → false.
      resolve(dlg.returnValue === "ok");
    }
    dlg.addEventListener("close", alCerrar);
    dlg.returnValue = "";
    dlg.showModal();
  });
}

// ---------------------------------------------------------------------------
// Diálogo: explorador de carpetas de destino
// ---------------------------------------------------------------------------

async function cargarDialogoCarpetas(ruta) {
  const lista = $("#dlg-lista");
  lista.innerHTML = '<li class="dlg-vacio">Cargando…</li>';
  let datos;
  try {
    datos = await pedirJSON("/api/carpetas?ruta=" + encodeURIComponent(ruta || ""));
  } catch (e) {
    lista.innerHTML = "";
    const li = document.createElement("li");
    li.className = "dlg-vacio";
    li.textContent = "No se pudo listar: " + e.message;
    lista.appendChild(li);
    return;
  }
  estado.dialogo.ruta = datos.ruta || "";
  $("#dlg-ruta").textContent = etiquetaCarpeta(estado.dialogo.ruta);
  $("#btn-dlg-subir").hidden = !datos.puede_subir;

  const carpetas = (datos.items || []).filter((i) => i.es_carpeta);
  if (!carpetas.length) {
    lista.innerHTML =
      '<li class="dlg-vacio">No hay subcarpetas. Puedes crear una abajo o guardar aquí.</li>';
  } else {
    lista.innerHTML = carpetas
      .map(
        (c) =>
          '<li><button type="button" class="dlg-item" data-ruta="' + esc(c.ruta) + '">' +
          ICONO.carpeta + "<span>" + esc(c.nombre) + "</span></button></li>"
      )
      .join("");
    $$("#dlg-lista .dlg-item").forEach((b) =>
      b.addEventListener("click", () => cargarDialogoCarpetas(b.dataset.ruta))
    );
  }
}

function abrirDialogoCarpetas() {
  const dlg = $("#dialogo-carpetas");
  cargarDialogoCarpetas(estado.carpetaDestino);
  dlg.showModal();
}

function iniciarDialogoCarpetas() {
  $("#btn-dlg-subir").addEventListener("click", () => {
    const ruta = estado.dialogo.ruta;
    const arriba = ruta.includes("/") ? ruta.slice(0, ruta.lastIndexOf("/")) : "";
    cargarDialogoCarpetas(arriba);
  });

  $("#btn-dlg-crear").addEventListener("click", async () => {
    const nombre = $("#dlg-nueva-nombre").value.trim();
    if (!nombre) return;
    try {
      await pedirJSON("/api/carpetas/crear", {
        method: "POST",
        body: JSON.stringify({ ruta_padre: estado.dialogo.ruta, nombre: nombre }),
      });
      $("#dlg-nueva-nombre").value = "";
      cargarDialogoCarpetas(estado.dialogo.ruta);
    } catch (e) {
      avisar("No se pudo crear la carpeta: " + e.message, "error");
    }
  });

  $("#dlg-nueva-nombre").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      $("#btn-dlg-crear").click();
    }
  });

  $("#btn-dlg-seleccionar").addEventListener("click", () => {
    estado.carpetaDestino = estado.dialogo.ruta;
    $("#carpeta-actual").textContent = etiquetaCarpeta(estado.carpetaDestino);
    guardarConfig({ carpeta_por_defecto: estado.carpetaDestino });
    $("#dialogo-carpetas").close();
    avisar("Las descargas se guardarán en " + etiquetaCarpeta(estado.carpetaDestino), "ok");
  });
}

// ---------------------------------------------------------------------------
// Vista previa: escuchar (o ver) antes de decidir la descarga
//
// Se usa el reproductor incrustado de YouTube en lugar de traer el audio por
// nuestra cuenta: las URLs de stream van firmadas y caducan, así que un
// <audio> apuntando a ellas se rompería solo. El dominio -nocookie evita que
// YouTube plante cookies de seguimiento por el hecho de abrir la ventana.
//
// Se ve en la misma ventana flotante que los vídeos de la biblioteca (el
// escenario): se mueve, se redimensiona y pasa a teatro o a pantalla completa
// igual, y como no es modal se puede seguir buscando mientras suena.
// ---------------------------------------------------------------------------

// Campos que la tarjeta lleva en sus data-* y que necesita agregarUno().
const CAMPOS_ITEM = ["url", "titulo", "thumbnail", "duracion", "canal"];

const ORIGEN_YOUTUBE = "https://www.youtube-nocookie.com";

// Pide al reproductor incrustado que cuente lo que le pasa. Es el protocolo de
// la API de iframes de YouTube: hasta que no se le saluda no manda nada, y como
// al cargar el iframe puede no estar listo aún, se insiste unos segundos.
function escucharAYoutube(iframe) {
  const saludo = JSON.stringify({ event: "listening", id: "sonora", channel: "widget" });
  let intentos = 0;
  const insistir = setInterval(() => {
    intentos += 1;
    if (!iframe.isConnected || intentos > 20) {
      clearInterval(insistir);
      return;
    }
    if (iframe.contentWindow) iframe.contentWindow.postMessage(saludo, ORIGEN_YOUTUBE);
  }, 400);
}

// YouTube se niega a reproducir el vídeo en su reproductor incrustado. Pasa
// con vídeos públicos y descargables («Este vídeo no está disponible / Ver en
// YouTube») y no depende de la app. Se pasa entonces a un <video> propio que
// el backend alimenta uniendo audio y vídeo al vuelo (servicios/previa.py).
async function alFallarYoutube() {
  const previa = estado.video.previa;
  if (!previa || previa.propia) return;
  previa.propia = { base: 0, duracion: 0, control: new AbortController() };
  if (previa.directo) {
    // Un directo en curso no se puede servir desde aquí.
    previaNoDisponible("YouTube no deja ver este directo fuera de su web.");
    return;
  }
  $("#ev-previa").innerHTML = '<div class="ev-espera"></div>';
  let info;
  try {
    info = await pedirJSON("/api/previa/" + encodeURIComponent(previa.id));
  } catch (e) {
    if (estado.video.previa === previa) {
      previaNoDisponible("YouTube no deja ver este vídeo fuera de su web, " +
        "y tampoco se ha podido reproducir desde Sonora.");
    }
    return;
  }
  // Mientras se preparaba, la vista previa pudo cerrarse o cambiar de vídeo.
  if (estado.video.previa !== previa) return;
  previa.propia.duracion = info.duracion || 0;
  montarPreviaPropia(previa);
  avisar("YouTube no deja incrustar este vídeo: se reproduce con el reproductor de Sonora.", "info");
}

// Reproductor propio de la vista previa: lo justo (pausa, posición y tiempo).
// El volumen es el de la barra de reproducción de la app.
function montarPreviaPropia(previa) {
  const propia = previa.propia;
  const marco = $("#ev-previa");
  marco.innerHTML =
    '<video class="previa-video" playsinline></video>' +
    '<div class="ev-espera"></div>' +
    '<div class="previa-controles">' +
      '<button type="button" class="btn-icono" id="previa-play" aria-label="Pausar">' +
        ICONO.pausa + "</button>" +
      '<input type="range" id="previa-seek" min="0" step="1" value="0" ' +
        'max="' + Math.max(1, Math.floor(propia.duracion)) + '" aria-label="Posición del vídeo">' +
      '<span class="ev-tiempo" id="previa-tiempo"></span>' +
    "</div>";
  const video = marco.querySelector("video");
  const espera = marco.querySelector(".ev-espera");
  const seek = $("#previa-seek");
  const btnPlay = $("#previa-play");
  let arrastrando = false;

  function pintar(segundos) {
    seek.value = String(segundos);
    pintarRango(seek, propia.duracion ? (segundos / propia.duracion) * 100 : 0);
    $("#previa-tiempo").textContent =
      formatearTiempo(segundos) + " / " + formatearTiempo(propia.duracion);
  }

  // El flujo se escribe sobre la marcha y no admite saltos: para ir a otro
  // punto se pide uno nuevo desde ese segundo. La posición real es, por tanto,
  // ese arranque más lo que lleve reproducido el <video>.
  function irA(segundos) {
    propia.base = limitar(segundos, 0, Math.max(0, propia.duracion - 1));
    espera.hidden = false;
    video.src = "/previa/" + encodeURIComponent(previa.id) + ".mp4?t=" + propia.base;
    const p = video.play();
    if (p && p.catch) p.catch(() => {});
    pintar(propia.base);
  }

  function alternar() {
    if (video.paused) {
      const p = video.play();
      if (p && p.catch) p.catch(() => {});
    } else {
      video.pause();
    }
  }

  const igualarVolumen = () => {
    video.volume = audio.volume;
    video.muted = audio.muted;
  };
  igualarVolumen();
  // La señal quita este oyente al cerrar la vista previa (ver cerrarPreview).
  audio.addEventListener("volumechange", igualarVolumen, { signal: propia.control.signal });
  // Y al cerrarla hay que soltar el flujo a propósito: quitar el <video> de la
  // página no corta la conexión, y ffmpeg seguiría bajando el vídeo para nadie.
  propia.control.signal.addEventListener("abort", () => {
    video.pause();
    video.removeAttribute("src");
    video.load();
  });

  video.addEventListener("timeupdate", () => {
    if (!arrastrando) pintar(propia.base + video.currentTime);
  });
  video.addEventListener("waiting", () => {
    espera.hidden = false;
  });
  for (const tipo of ["playing", "canplay"]) {
    video.addEventListener(tipo, () => {
      espera.hidden = true;
    });
  }
  for (const tipo of ["play", "pause"]) {
    video.addEventListener(tipo, () => {
      btnPlay.innerHTML = video.paused ? ICONO.play : ICONO.pausa;
      btnPlay.setAttribute("aria-label", video.paused ? "Reproducir" : "Pausar");
    });
  }
  video.addEventListener("loadedmetadata", () => {
    if (video.videoWidth && video.videoHeight) {
      fijarProporcionVideo(video.videoWidth / video.videoHeight);
    }
  });
  video.addEventListener("error", () => {
    if (estado.video.previa === previa) {
      previaNoDisponible("No se ha podido reproducir este vídeo desde Sonora.");
    }
  });
  video.addEventListener("click", alternar);
  btnPlay.addEventListener("click", alternar);

  seek.addEventListener("pointerdown", () => {
    arrastrando = true;
  });
  for (const tipo of ["pointerup", "pointercancel"]) {
    seek.addEventListener(tipo, () => {
      arrastrando = false;
    });
  }
  seek.addEventListener("input", () => {
    pintar(Number(seek.value));
  });
  seek.addEventListener("change", () => {
    arrastrando = false;
    irA(Number(seek.value));
  });

  irA(0);
}

// Ni YouTube ni Sonora pueden con el vídeo: se dice, y se ofrece abrirlo fuera.
function previaNoDisponible(mensaje) {
  const previa = estado.video.previa;
  const marco = $("#ev-previa");
  marco.innerHTML =
    '<div class="previa-aviso"><p></p>' +
    '<button type="button" class="btn btn-fantasma">Abrir en YouTube</button></div>';
  marco.querySelector("p").textContent = mensaje;
  marco.querySelector("button").addEventListener("click", async () => {
    try {
      await pedirJSON("/api/abrir-youtube", {
        method: "POST",
        body: JSON.stringify({ id: previa.id }),
      });
    } catch (e) {
      avisar("No se pudo abrir YouTube: " + e.message, "error");
    }
  });
}

function abrirPreview(btn) {
  const id = btn.dataset.previewId;
  if (!id) return;

  // La biblioteca calla mientras se escucha la vista previa y, si había un
  // vídeo a la vista, cede la ventana (queda su botón para recuperarlo).
  if (estado.rep.videoVisible) {
    ocultarEscenarioVideo(true);
  } else {
    audio.pause();
  }

  // Abrir otra vista previa encima no pasa por cerrarPreview(): hay que soltar
  // aquí el reproductor propio de la anterior, o su flujo (y el ffmpeg que lo
  // alimenta) seguiría vivo sin nadie mirando.
  if (estado.video.previa && estado.video.previa.propia) {
    estado.video.previa.propia.control.abort();
  }

  estado.video.previa = {
    id: id,
    origen: btn,
    directo: btn.dataset.directo || "",
    propia: null, // estado del reproductor propio, si YouTube no deja incrustar
  };
  $("#ev-titulo").textContent = btn.dataset.titulo || "Vista previa";
  $("#preview-canal").textContent = btn.dataset.canal || "";

  const iframe = document.createElement("iframe");
  // enablejsapi y origin: para que el reproductor avise si no puede con el
  // vídeo (ver escucharAYoutube y alFallarYoutube). La resolución no se le
  // puede pedir: ignora setPlaybackQuality y setPlaybackQualityRange, y la
  // elige él según el tamaño del marco (480p en pequeño, 1080p en teatro).
  iframe.src = ORIGEN_YOUTUBE + "/embed/" + encodeURIComponent(id) +
    "?autoplay=1&rel=0&enablejsapi=1&origin=" + encodeURIComponent(location.origin);
  iframe.title = "Reproductor de " + (btn.dataset.titulo || "YouTube");
  iframe.allow = "autoplay; encrypted-media; picture-in-picture";
  iframe.allowFullscreen = true;
  const marco = $("#ev-previa");
  marco.innerHTML = "";
  marco.appendChild(iframe);
  escucharAYoutube(iframe);

  // El botón del pie se prepara como si fuera el ＋ de la tarjeta, así añadir
  // desde aquí pasa por el mismo agregarUno() y hereda su manejo de
  // duplicados, formato y avisos.
  const btnAnadir = $("#btn-preview-descargar");
  for (const campo of CAMPOS_ITEM) btnAnadir.dataset[campo] = btn.dataset[campo] || "";
  const yaEsta = estado.urlsActivas.has(btn.dataset.url);
  btnAnadir.disabled = yaEsta;
  btnAnadir.textContent = yaEsta ? "✓ Ya está en la cola" : "＋ Añadir a la cola";
  // Un directo se ve, pero no se puede poner a descargar hasta que acabe.
  btnAnadir.hidden = Boolean(btn.dataset.directo);

  escenario.hidden = false;
  fijarProporcionVideo(16 / 9); // el reproductor de YouTube es siempre apaisado
  reflejarEscenario();
  despertarControlesVideo();
  // El foco entra en la ventana para poder manejarla (y cerrarla) con teclado.
  $("#btn-preview-cerrar").focus();
}

// Cierra la vista previa, si la hay.
function cerrarPreview() {
  const previa = estado.video.previa;
  if (!previa) return;
  if (document.fullscreenElement) document.exitFullscreen();
  const teniaElFoco = escenario.contains(document.activeElement);
  estado.video.previa = null;
  if (previa.propia) previa.propia.control.abort();
  // Vaciar el marco destruye el iframe (o el <video> propio) y corta el sonido.
  $("#ev-previa").innerHTML = "";
  escenario.hidden = true;
  reflejarEscenario();
  // El foco vuelve a la tarjeta desde la que se abrió, si sigue en pantalla.
  if (teniaElFoco && previa.origen.isConnected) previa.origen.focus();
}

function iniciarPreview() {
  $("#btn-preview-cerrar").addEventListener("click", cerrarPreview);
  // El reproductor de YouTube cuenta por postMessage si no puede con el vídeo.
  // Solo se atiende al iframe de la vista previa que está abierta.
  window.addEventListener("message", (e) => {
    const iframe = $("#ev-previa iframe");
    if (!estado.video.previa || !iframe) return;
    if (e.origin !== ORIGEN_YOUTUBE || e.source !== iframe.contentWindow) return;
    let datos;
    try {
      datos = JSON.parse(e.data);
    } catch (err) {
      return;
    }
    if (datos && datos.event === "onError") alFallarYoutube();
  });
  $("#btn-preview-descargar").addEventListener("click", async (e) => {
    const boton = e.currentTarget;
    if (!boton.dataset.url) return;
    await agregarUno(boton);
    // La ventana no es modal: se puede seguir escuchando tras añadir.
    if (boton.disabled) boton.textContent = "✓ Ya está en la cola";
  });
}

// ---------------------------------------------------------------------------
// Chequeo del entorno (versión de yt-dlp, ffmpeg y runtime de JavaScript)
//
// Se lanza al abrir la app. Un yt-dlp viejo es la causa habitual de que las
// descargas empiecen a fallar con "HTTP Error 403", así que conviene enterarse
// antes de intentar descargar, no después.
// ---------------------------------------------------------------------------

// Construye el aviso a partir del estado; devuelve null si no hay nada que
// decir. Solo se informa de UNA cosa: la más urgente, para no llenar la barra
// lateral de avisos compitiendo entre sí.
function mensajeSalud(datos) {
  const YTDLP = '<span class="paquete">yt-dlp</span>';
  const yt = datos.yt_dlp || {};
  const runtime = datos.runtime_js || {};

  if (datos.reinicio_pendiente) {
    // Mientras no se reinicie, el servidor no deja buscar ni descargar.
    return {
      nivel: "aviso",
      html: YTDLP + " se ha actualizado. Reinicia Sonora para seguir buscando y descargando.",
      accion: false,
    };
  }
  if (!yt.instalada) {
    return { nivel: "error", html: "No se encontró " + YTDLP + ": las descargas no funcionarán.", accion: false };
  }
  if (yt.hay_actualizacion) {
    const texto = "Hay una versión nueva de " + YTDLP + " (" + esc(yt.instalada) +
      " → " + esc(yt.ultima) + "). Actualiza para evitar fallos de descarga.";
    return { nivel: "aviso", html: texto, accion: true };
  }
  if (yt.caducada) {
    return {
      nivel: "aviso",
      html: "Tu " + YTDLP + " tiene " + esc(String(yt.dias)) + " días. No se pudo comprobar" +
        " si hay una versión nueva; si las descargas fallan, actualiza.",
      accion: true,
    };
  }
  if (!runtime.disponible) {
    // La orden depende del sistema (winget, brew, el instalador de Deno…).
    const orden = (datos.instalar || {}).deno;
    return {
      nivel: "aviso",
      html: "Sin runtime de JavaScript, YouTube puede negar algunos formatos." +
        (orden ? " Instala uno con <code>" + esc(orden) + "</code>." : ""),
      accion: false,
    };
  }
  return null;
}

async function comprobarSalud() {
  let datos;
  try {
    datos = await pedirJSON("/api/salud");
  } catch (e) {
    // Sin red o con PyPI caído no se avisa de nada: el chequeo es accesorio y
    // no debe estorbar a quien solo quiere usar la app.
    return;
  }
  estado.salud = datos;
  pintarSalud(mensajeSalud(datos));
}

function pintarSalud(aviso) {
  const caja = $("#aviso-salud");
  const boton = $("#boton-actualizar");
  if (!aviso) {
    caja.hidden = true;
    boton.hidden = true;
    return;
  }
  $("#aviso-salud-texto").innerHTML = aviso.html;
  caja.dataset.nivel = aviso.nivel;
  caja.hidden = false;
  boton.hidden = !aviso.accion;
}

async function actualizarYtDlp() {
  const boton = $("#boton-actualizar");
  const textoOriginal = boton.textContent;
  boton.disabled = true;
  boton.textContent = "Actualizando…";
  try {
    const resultado = await pedirJSON("/api/salud/actualizar", { method: "POST" });
    avisar(resultado.mensaje || "yt-dlp actualizado.", "ok");
    // Ya no hay nada que ofrecer: la actualización entra al reiniciar, y
    // hasta entonces el servidor no deja buscar ni descargar.
    pintarSalud({
      nivel: "aviso",
      html: "yt-dlp actualizado a " + esc(resultado.version || "la última versión") +
        ". Reinicia Sonora para seguir buscando y descargando.",
      accion: false,
    });
  } catch (e) {
    avisar("No se pudo actualizar: " + e.message, "error");
    boton.disabled = false;
    boton.textContent = textoOriginal;
  }
}

function iniciarSalud() {
  $("#boton-actualizar").addEventListener("click", actualizarYtDlp);
}

// ---------------------------------------------------------------------------
// Tema de color (el degradado de acento sobre la paleta de negros)
//
// El tema guardado llega ya aplicado desde el servidor en <html data-tema>,
// para que la ventana no abra con un color y salte a otro. Aquí solo se
// marca la muestra elegida y se atiende el cambio.
// ---------------------------------------------------------------------------

// Cambia el color de la interfaz con un fundido corto de toda la página. Los
// degradados no se pueden animar con una transición de CSS corriente; una
// transición de vista funde la imagen de antes con la de después.
function aplicarTema(tema) {
  const raiz = document.documentElement;
  const cambiar = () => {
    raiz.dataset.tema = tema;
  };
  const sinMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (document.startViewTransition && !sinMovimiento) {
    document.startViewTransition(cambiar);
  } else {
    cambiar();
  }
}

function iniciarTemas() {
  const raiz = document.documentElement;
  $$('#temas input[name="tema"]').forEach((radio) => {
    radio.checked = radio.value === raiz.dataset.tema;
    radio.addEventListener("change", () => {
      aplicarTema(radio.value);
      guardarConfig({ tema: radio.value });
    });
  });
}

// ---------------------------------------------------------------------------
// Arranque
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  // La región de avisos se abre ya y se queda abierta (ver avisar()).
  const avisos = $("#avisos");
  if (avisos.hasAttribute("popover")) avisos.showPopover();
  iniciarNavegacion();
  iniciarBuscador();
  iniciarConfig();
  iniciarCola();
  iniciarBiblioteca();
  iniciarHistorial();
  iniciarReproductor();
  iniciarDialogoCarpetas();
  iniciarPreview();
  iniciarSalud();
  iniciarTemas();
  cargarConfig();
  comprobarSalud();
  refrescarCola();
  iniciarSSE();
});
