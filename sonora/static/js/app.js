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

// Aviso no bloqueante (toast) en la región viva #avisos (aria-live="polite").
function avisar(mensaje, tipo) {
  const cont = $("#avisos");
  if (!cont) return;
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

// Pinta el relleno ámbar de un input[type=range] (la pista usa var(--pct)).
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
  dialogo: {
    ruta: "",                   // carpeta que muestra el explorador
  },
};

// Elemento multimedia ÚNICO: es un <video> pero reproduce también el audio
// (MP3). Cuando suena audio, el escenario de vídeo permanece oculto y se
// muestra la carátula/estado en la barra. Un solo elemento evita duplicar la
// lógica de transporte y re-parentar un medio en reproducción.
const audio = $("#media");

// ---------------------------------------------------------------------------
// Navegación entre vistas
// ---------------------------------------------------------------------------

function cambiarVista(nombre) {
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
}

async function buscar(q) {
  const cont = $("#resultados");
  const token = ++estado.busqueda.token;
  cont.innerHTML = '<p class="cargando">Buscando…</p>';
  let datos;
  try {
    datos = await pedirJSON("/api/buscar", { method: "POST", body: JSON.stringify({ q: q, n: 24 }) });
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

function tarjetaResultado(r) {
  const conThumb = r.thumbnail
    ? '<img src="' + esc(r.thumbnail) + '" alt="" loading="lazy">'
    : "";
  const duracion = r.duracion
    ? '<span class="tarjeta-duracion">' + esc(r.duracion) + "</span>"
    : "";
  // Los atributos data-* se comparten entre el botón ＋ (añade con el formato
  // global) y el ▾ (abre el menú para elegir audio o vídeo explícitamente).
  const datosItem =
    'data-url="' + esc(r.url) + '" data-titulo="' + esc(r.titulo) + '" ' +
    'data-thumbnail="' + esc(r.thumbnail) + '" data-duracion="' + esc(r.duracion) + '" ' +
    'data-canal="' + esc(r.canal) + '"';
  // El botón de escucha va antes del grupo ＋/▾ en el DOM: cubre la portada
  // entera y el CSS lo deja por debajo de ellos.
  const preview = r.id
    ? '<button type="button" class="tarjeta-preview" data-preview-id="' + esc(r.id) + '" ' +
        datosItem + ' aria-label="Escuchar antes de descargar: ' + esc(r.titulo) + '">' +
        '<svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="rgba(0,0,0,.45)"/>' +
        '<path d="M10 8.5v7l6-3.5-6-3.5z" fill="currentColor"/></svg></button>'
    : "";
  return (
    '<article class="tarjeta">' +
      '<div class="tarjeta-cover">' + conThumb + duracion + preview +
        '<div class="tarjeta-add-grupo">' +
          '<button type="button" class="tarjeta-add" ' + datosItem + ' ' +
            'aria-label="Añadir a la cola: ' + esc(r.titulo) + '">＋</button>' +
          '<button type="button" class="tarjeta-add-mas" ' + datosItem + ' ' +
            'aria-label="Elegir formato para: ' + esc(r.titulo) + '" aria-haspopup="menu">▾</button>' +
        "</div>" +
      "</div>" +
      '<h3 class="tarjeta-titulo">' + esc(r.titulo) + "</h3>" +
      '<p class="tarjeta-canal">' + esc(r.canal) + "</p>" +
    "</article>"
  );
}

function renderResultados(datos) {
  const cont = $("#resultados");
  const resultados = datos.resultados || [];
  if (!resultados.length) {
    cont.innerHTML =
      '<div class="estado-vacio"><h2>Sin resultados</h2>' +
      "<p>Prueba con otro término o revisa la URL.</p></div>";
    return;
  }

  let html = "";

  if (datos.es_playlist) {
    const titulo = datos.titulo_playlist || (datos.es_canal ? "Canal" : "Playlist");
    const total = datos.total_playlist || resultados.length;
    const obtenidas = datos.obtenidas || resultados.length;
    html += '<header class="playlist-cabecera">';
    html += "<h2>" + esc(titulo) + "</h2>";
    html += '<span class="chip chip-ambar">' + (datos.es_canal ? "Canal" : datos.es_mix ? "Mix" : "Playlist") + "</span>";
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
      '<button type="button" class="btn btn-ambar" id="btn-agregar-todo" data-titulo="' +
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
    btn.textContent = enCola ? "✓" : "＋";
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
    btn.textContent = "✓";
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
  // Posición: bajo el botón ▾, sin salirse por la derecha de la ventana.
  menu.classList.add("abierto");
  const r = btnMas.getBoundingClientRect();
  const ancho = menu.offsetWidth;
  const izq = Math.max(8, Math.min(r.right - ancho, window.innerWidth - ancho - 8));
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
  estado.urlsActivas = new Set(
    estado.cola
      .filter((i) => i.estado === "en_cola" || i.estado === "descargando")
      .map((i) => i.url)
  );
  actualizarBadgeCola();
  actualizarBotonesAgregar();
  if (estado.vista === "cola") renderCola();
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
    return '<span class="chip chip-ambar ci-estado" data-chip-id="' + esc(item.id) + '">' + pct + " %</span>";
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

function renderCola() {
  const lista = $("#cola-lista");
  const items = estado.cola;

  // Controles globales y resumen.
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

  // Listeners del render.
  $$("#cola-lista .lote-grupo").forEach((det) => {
    det.addEventListener("toggle", () => {
      if (det.open) {
        estado.lotesCerrados.delete(det.dataset.lote);
      } else {
        estado.lotesCerrados.add(det.dataset.lote);
      }
    });
  });
  $$("#cola-lista .ci-quitar").forEach((b) =>
    b.addEventListener("click", () => quitarDeCola(b.dataset.id))
  );
  $$("#cola-lista .ci-cancelar").forEach((b) =>
    b.addEventListener("click", () => cancelarDescarga(b.dataset.id, b))
  );
  $$("#cola-lista .ci-reintentar").forEach((b) =>
    b.addEventListener("click", () => reintentar(b.dataset.id))
  );
  $$("#cola-lista .lote-quitar").forEach((b) =>
    b.addEventListener("click", (e) => {
      e.preventDefault(); // que el clic no pliegue/despliegue el details
      quitarLote(b.dataset.lote);
    })
  );
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
          chip.textContent = datos.mensaje
            ? "Convirtiendo…"
            : Math.round(Number(datos.progreso) || 0) + " %";
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

function renderCarpetasBiblioteca() {
  const cont = $("#carpetas-biblioteca");
  const carpetas = estado.biblioteca.carpetas;
  if (!carpetas.length && !estado.biblioteca.carpeta) {
    cont.innerHTML = "";
    return;
  }
  let html =
    '<button type="button" class="chip-carpeta" data-carpeta="" aria-pressed="' +
    (estado.biblioteca.carpeta === "" ? "true" : "false") + '">Toda la música</button>';
  for (const c of carpetas) {
    html +=
      '<button type="button" class="chip-carpeta" data-carpeta="' + esc(c) +
      '" aria-pressed="' + (estado.biblioteca.carpeta === c ? "true" : "false") + '">' +
      ICONO.carpeta + " " + esc(c.split("/").pop()) + "</button>";
  }
  cont.innerHTML = html;
  $$("#carpetas-biblioteca .chip-carpeta").forEach((chip) => {
    chip.addEventListener("click", () => {
      estado.biblioteca.carpeta = chip.dataset.carpeta;
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
  try {
    await pedirJSON("/api/biblioteca/eliminar", {
      method: "POST",
      body: JSON.stringify({ archivo: archivo }),
    });
    // Si se borra la pista que suena, paramos y limpiamos la barra.
    if (archivo === estado.rep.archivo) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      estado.rep.archivo = "";
      estado.rep.indice = -1;
      ocultarEscenarioVideo(false);
      actualizarBarraReproductor(null);
    } else {
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
  estado.rep.archivo = pista.archivo;
  estado.rep.tipo = pista.tipo === "video" ? "video" : "audio";
  audio.src = urlAudio(pista.archivo);
  const promesa = audio.play();
  if (promesa && promesa.catch) {
    promesa.catch((e) => {
      // Cambiar de pista rápido aborta el play() anterior: no es un error real.
      if (e && e.name === "AbortError") return;
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

function mostrarEscenarioVideo(pista) {
  estado.rep.videoVisible = true;
  $("#escenario-video").hidden = false;
  $("#ev-titulo").textContent = pista ? pista.titulo : "";
  $("#btn-mostrar-video").hidden = true;
}

// Oculta el escenario. La reproducción (audio del vídeo) sigue salvo que
// ``pausar`` sea true.
function ocultarEscenarioVideo(pausar) {
  estado.rep.videoVisible = false;
  $("#escenario-video").hidden = true;
  if (pausar) audio.pause();
  // Si lo que suena es un vídeo, ofrecemos volver a mostrarlo.
  $("#btn-mostrar-video").hidden = !(estado.rep.tipo === "video" && estado.rep.archivo);
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

function iniciarEscenarioVideo() {
  const marco = $("#ev-marco");
  const video = audio; // el <video id="media">

  $("#btn-mostrar-video").addEventListener("click", () => {
    mostrarEscenarioVideo(estado.rep.lista[estado.rep.indice]);
  });
  $("#btn-video-ocultar").addEventListener("click", () => ocultarEscenarioVideo(false));

  $("#btn-video-pantalla").addEventListener("click", () => {
    // Pantalla completa sobre el <video>: en fullscreen el navegador muestra
    // sus controles nativos (nuestra barra inferior no es visible ahí).
    const destino = video;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else if (destino.requestFullscreen) {
      destino.requestFullscreen().catch(() => {});
    }
  });

  // Clic en el marco = play/pausa (gesto habitual en reproductores de vídeo).
  marco.addEventListener("click", (e) => {
    if (e.target === video || e.target === marco) alternarPlay();
  });

  // Controles nativos solo en pantalla completa (fuera, manda nuestra barra).
  document.addEventListener("fullscreenchange", () => {
    video.controls = document.fullscreenElement === video;
  });
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

  // Estado visual play/pausa + ecualizador.
  function reflejarEstado() {
    const sonando = !audio.paused && estado.rep.archivo;
    // toggleAttribute, no la propiedad .hidden: los <svg> no son HTMLElement
    // y la propiedad no les pone el atributo (y por tanto no los oculta).
    btnPlay.querySelector(".icono-play").toggleAttribute("hidden", Boolean(sonando));
    btnPlay.querySelector(".icono-pausa").toggleAttribute("hidden", !sonando);
    btnPlay.setAttribute("aria-label", sonando ? "Pausar" : "Reproducir");
    $("#eq").classList.toggle("activo", Boolean(sonando));
    marcarPistaActiva();
  }
  audio.addEventListener("play", reflejarEstado);
  audio.addEventListener("pause", reflejarEstado);

  audio.addEventListener("ended", () => siguiente(true));

  audio.addEventListener("error", () => {
    if (!estado.rep.archivo) return;
    avisar("No se pudo cargar el audio de esta pista.", "error");
  });

  // Seek: mientras se arrastra, el timeupdate no debe pisar el valor.
  audio.addEventListener("loadedmetadata", () => {
    $("#tiempo-total").textContent = formatearTiempo(audio.duration);
  });
  audio.addEventListener("timeupdate", () => {
    if (estado.rep.arrastrandoSeek || !audio.duration) return;
    const pct = (audio.currentTime / audio.duration) * 100;
    seek.value = String(pct);
    pintarRango(seek, pct);
    $("#tiempo-actual").textContent = formatearTiempo(audio.currentTime);
  });
  seek.addEventListener("pointerdown", () => {
    estado.rep.arrastrandoSeek = true;
  });
  // El flag debe soltarse SIEMPRE al levantar el puntero: si el usuario suelta
  // sin cambiar el valor, 'change' no dispara y la barra quedaría congelada.
  seek.addEventListener("pointerup", () => {
    estado.rep.arrastrandoSeek = false;
  });
  seek.addEventListener("pointercancel", () => {
    estado.rep.arrastrandoSeek = false;
  });
  seek.addEventListener("input", () => {
    pintarRango(seek, Number(seek.value));
    if (audio.duration) {
      $("#tiempo-actual").textContent =
        formatearTiempo((Number(seek.value) / 100) * audio.duration);
    }
  });
  seek.addEventListener("change", () => {
    estado.rep.arrastrandoSeek = false;
    if (audio.duration) {
      audio.currentTime = (Number(seek.value) / 100) * audio.duration;
    }
  });

  // Volumen (persistido en localStorage).
  const volGuardado = parseFloat(localStorage.getItem("sonora-volumen"));
  audio.volume = isFinite(volGuardado) ? Math.min(1, Math.max(0, volGuardado)) : 1;
  volumen.value = String(audio.volume);
  pintarRango(volumen, audio.volume * 100);
  volumen.addEventListener("input", () => {
    audio.volume = Number(volumen.value);
    pintarRango(volumen, audio.volume * 100);
    localStorage.setItem("sonora-volumen", String(audio.volume));
  });

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
    } catch (e) {
      /* algún handler no soportado: seguimos sin él */
    }
  }

  // Atajos de teclado: espacio = play/pausa, "/" = ir al buscador.
  document.addEventListener("keydown", (e) => {
    const tag = (e.target && e.target.tagName) || "";
    const escribiendo = tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA";
    const dialogoAbierto = Boolean(document.querySelector("dialog[open]"));
    // Espacio solo actúa como play/pausa si el foco NO está en un control que
    // ya use Espacio para activarse (botones, summary de los lotes, enlaces).
    const enControl = e.target && e.target.closest &&
      e.target.closest("button, summary, a, input, select, textarea");
    if (e.key === " " && !enControl && !dialogoAbierto) {
      e.preventDefault();
      alternarPlay();
    }
    if (e.key === "/" && !escribiendo && !dialogoAbierto) {
      e.preventDefault();
      cambiarVista("buscar");
      $("#campo-buscar").focus();
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
    // Rojo para acciones destructivas, ámbar para el resto.
    btnOk.classList.toggle("btn-peligro", opts.peligro !== false);
    btnOk.classList.toggle("btn-ambar", opts.peligro === false);
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
// ---------------------------------------------------------------------------

// Campos que la tarjeta lleva en sus data-* y que necesita agregarUno().
const CAMPOS_ITEM = ["url", "titulo", "thumbnail", "duracion", "canal"];

function abrirPreview(btn) {
  const id = btn.dataset.previewId;
  if (!id) return;

  $("#preview-titulo").textContent = btn.dataset.titulo || "Vista previa";
  $("#preview-canal").textContent = btn.dataset.canal || "";

  const iframe = document.createElement("iframe");
  iframe.src = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(id) +
    "?autoplay=1&rel=0";
  iframe.title = "Reproductor de " + (btn.dataset.titulo || "YouTube");
  iframe.allow = "autoplay; encrypted-media; picture-in-picture";
  iframe.allowFullscreen = true;
  const marco = $("#preview-marco");
  marco.innerHTML = "";
  marco.appendChild(iframe);

  // El botón del diálogo se prepara como si fuera el ＋ de la tarjeta, así
  // añadir desde aquí pasa por el mismo agregarUno() y hereda su manejo de
  // duplicados, formato y avisos.
  const btnAnadir = $("#btn-preview-descargar");
  for (const campo of CAMPOS_ITEM) btnAnadir.dataset[campo] = btn.dataset[campo] || "";
  const yaEsta = estado.urlsActivas.has(btn.dataset.url);
  btnAnadir.disabled = yaEsta;
  btnAnadir.textContent = yaEsta ? "✓ Ya está en la cola" : "＋ Añadir a la cola";

  $("#dialogo-preview").showModal();
}

function cerrarPreview() {
  const dlg = $("#dialogo-preview");
  if (dlg.open) dlg.close();  // el resto lo hace el manejador de 'close'
}

function iniciarPreview() {
  const dlg = $("#dialogo-preview");
  $("#btn-preview-cerrar").addEventListener("click", cerrarPreview);
  // 'close' cubre todas las vías de cierre, incluido el Escape que el propio
  // <dialog> gestiona: vaciar el marco destruye el iframe y corta el sonido.
  dlg.addEventListener("close", () => {
    $("#preview-marco").innerHTML = "";
  });
  // Clic en el fondo: el backdrop pertenece al <dialog>, de modo que el
  // objetivo del evento es el diálogo mismo y no su contenido.
  dlg.addEventListener("click", (e) => {
    if (e.target === dlg) cerrarPreview();
  });
  $("#btn-preview-descargar").addEventListener("click", async (e) => {
    const boton = e.currentTarget;
    if (!boton.dataset.url) return;
    await agregarUno(boton);
    cerrarPreview();
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

  if (!yt.instalada) {
    return { nivel: "error", html: "No se encontró " + YTDLP + ": las descargas no funcionarán.", accion: false };
  }
  if (yt.hay_actualizacion) {
    const texto = "Hay una versión nueva de " + YTDLP + " (" + esc(yt.instalada) +
      " → " + esc(yt.ultima) + "). Actualiza para evitar fallos de descarga.";
    // Empaquetada: yt-dlp va dentro del .exe y pip no puede tocarlo.
    if (!yt.actualizable) {
      return { nivel: "aviso", html: texto + " Al ir empaquetada, hay que reconstruir la app.", accion: false };
    }
    return { nivel: "aviso", html: texto, accion: true };
  }
  if (yt.caducada) {
    return {
      nivel: "aviso",
      html: "Tu " + YTDLP + " tiene " + esc(String(yt.dias)) + " días. No se pudo comprobar" +
        " si hay una versión nueva; si las descargas fallan, actualiza.",
      accion: Boolean(yt.actualizable),
    };
  }
  if (!runtime.disponible) {
    return {
      nivel: "aviso",
      html: "Sin runtime de JavaScript, YouTube puede negar algunos formatos." +
        " Instala uno con <code>winget install DenoLand.Deno</code>.",
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
    // Ya no hay nada que ofrecer: la actualización entra al reiniciar.
    pintarSalud({
      nivel: "aviso",
      html: "yt-dlp actualizado a " + esc(resultado.version || "la última versión") +
        ". Reinicia Sonora para usarlo.",
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
// Arranque
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
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
  cargarConfig();
  comprobarSalud();
  refrescarCola();
  iniciarSSE();
});
