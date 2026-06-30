// app.js — Lógica de frontend de "Mi Música" (vanilla JS, sin frameworks).
// Sigue el CONTRATO CONGELADO: rutas API, IDs del DOM y clases CSS exactas.
// Todo el texto visible va en español. Se escapa SIEMPRE el texto dinámico
// inyectado en innerHTML mediante esc() para prevenir inyección (XSS).

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

// Atajos de selección.
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

// Notificación discreta no bloqueante (toast). Crea el contenedor si falta.
function avisar(mensaje, tipo) {
  let cont = $("#avisos");
  if (!cont) {
    cont = document.createElement("div");
    cont.id = "avisos";
    cont.style.position = "fixed";
    cont.style.bottom = "96px";
    cont.style.right = "16px";
    cont.style.zIndex = "9999";
    cont.style.display = "flex";
    cont.style.flexDirection = "column";
    cont.style.gap = "8px";
    document.body.appendChild(cont);
  }
  const el = document.createElement("div");
  el.className = "aviso" + (tipo ? " aviso-" + tipo : "");
  el.textContent = mensaje; // textContent: seguro, no necesita esc()
  el.style.background = "#1c1c20";
  el.style.color = "#f5f5f5";
  el.style.padding = "10px 14px";
  el.style.borderRadius = "10px";
  el.style.boxShadow = "0 6px 20px rgba(0,0,0,.4)";
  el.style.fontSize = "14px";
  el.style.maxWidth = "320px";
  if (tipo === "error") el.style.borderLeft = "3px solid #e5484d";
  if (tipo === "ok") el.style.borderLeft = "3px solid #46c08f";
  cont.appendChild(el);
  setTimeout(() => {
    el.style.transition = "opacity .4s";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 400);
  }, 3200);
}

// Escapa un valor para usarlo dentro de un selector de atributo CSS.
function cssEscapar(valor) {
  const s = String(valor);
  if (window.CSS && typeof window.CSS.escape === "function") {
    return window.CSS.escape(s);
  }
  return s.replace(/["\\\]]/g, "\\$&");
}

// ---------------------------------------------------------------------------
// Estado global mínimo
// ---------------------------------------------------------------------------

const estado = {
  carpetaDestino: "",          // ruta relativa bajo descargas/ ('' = raíz)
  bitrate: "320",              // calidad por defecto
  biblioteca: [],              // lista cargada (cola de reproducción)
  indiceActual: -1,            // índice del track sonando dentro de biblioteca
  rutaExplorador: "",          // ruta actual en el overlay explorador
  arrastrandoSeek: false,      // true mientras el usuario arrastra la barra de seek
  colaPorId: new Map(),        // id de vídeo de YouTube -> estado en la cola
  ultimaBusqueda: null,        // últimos resultados renderizados (para redecorar)
};

// ---------------------------------------------------------------------------
// Estado de la cola por canción (para marcar "ya en la cola" en el buscador)
// ---------------------------------------------------------------------------

// Extrae el id de vídeo de YouTube de una URL (watch?v=, youtu.be/, shorts, embed).
// Devuelve "" si no se reconoce.
function idDeUrl(url) {
  if (!url) return "";
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, "");
    if (host === "youtu.be") return u.pathname.slice(1).split("/")[0];
    if (host.endsWith("youtube.com")) {
      const v = u.searchParams.get("v");
      if (v) return v;
      const m = u.pathname.match(/\/(?:shorts|embed)\/([^/?#]+)/);
      if (m) return m[1];
    }
  } catch (e) {
    /* URL no válida: lo tratamos como desconocido */
  }
  return "";
}

// Reconstruye el mapa id -> estado a partir de los ítems actuales de la cola.
function recalcularColaPorId(items) {
  estado.colaPorId = new Map();
  (items || []).forEach((it) => {
    const id = idDeUrl(it.url);
    if (id) estado.colaPorId.set(id, it.estado || "en_cola");
  });
}

// Para un resultado de búsqueda, indica si ya está en la cola y cómo:
//   "en_cola"    -> pendiente o descargando (no re-añadir)
//   "completado" -> ya descargado (no re-añadir)
//   null         -> no está (o falló): se puede añadir
function estadoEnCola(r) {
  const id = r.id || idDeUrl(r.url);
  if (!id) return null;
  const est = estado.colaPorId.get(id);
  if (est === "en_cola" || est === "descargando") return "en_cola";
  if (est === "completado") return "completado";
  return null;
}

// Si hay resultados de búsqueda visibles, los vuelve a pintar para reflejar
// el estado actual de la cola (se llama cuando la cola cambia).
function marcarResultadosEnCola() {
  const cont = $("#resultados-busqueda");
  if (estado.ultimaBusqueda && cont && cont.querySelector(".grid-resultados")) {
    renderResultados(estado.ultimaBusqueda);
  }
}

// ===========================================================================
// Navegación de vistas (.nav-btn ↔ .vista.activa)
// ===========================================================================

function cambiarVista(nombre) {
  $$(".nav-btn").forEach((btn) => {
    btn.classList.toggle("activo", btn.dataset.vista === nombre);
  });
  $$(".vista").forEach((v) => {
    v.classList.toggle("activa", v.id === "vista-" + nombre);
  });
  // Cargas perezosas al entrar en ciertas vistas.
  if (nombre === "cola") cargarCola();
  if (nombre === "biblioteca") cargarBiblioteca();
  if (nombre === "historial") cargarHistorial();
}

function initNavegacion() {
  $$(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => cambiarVista(btn.dataset.vista));
  });
}

// ===========================================================================
// Búsqueda (POST /api/buscar)
// ===========================================================================

async function buscar() {
  const input = $("#input-buscar");
  const cont = $("#resultados-busqueda");
  if (!input || !cont) return;
  const q = input.value.trim();
  if (!q) {
    cont.innerHTML = "";
    return;
  }
  cont.innerHTML = '<p class="cargando">Buscando…</p>';
  try {
    const datos = await pedirJSON("/api/buscar", {
      method: "POST",
      body: JSON.stringify({ q: q, n: 12 }),
    });
    renderResultados(datos);
  } catch (e) {
    cont.innerHTML = '<p class="vacio">No se pudo buscar: ' + esc(e.message) + "</p>";
  }
}

function renderResultados(datos) {
  const cont = $("#resultados-busqueda");
  if (!cont) return;
  estado.ultimaBusqueda = datos;     // recordamos para poder redecorar al cambiar la cola
  const resultados = (datos && datos.resultados) || [];
  let html = "";

  // Si es playlist, mostramos cabecera con título, nº de canciones y "Añadir todo".
  if (datos && datos.es_playlist) {
    const tituloPl = datos.titulo_playlist || "Playlist";
    const n = resultados.length;
    html +=
      '<div class="cabecera-playlist">' +
      '<div class="cabecera-playlist-info">' +
      "<h3>" + esc(tituloPl) + "</h3>" +
      '<span class="cabecera-playlist-sub">' + n + (n === 1 ? " canción" : " canciones") + "</span>" +
      "</div>" +
      (n > 0
        ? '<button id="btn-anadir-todo" class="btn-acento">＋ Añadir todo</button>'
        : '<span class="texto-muted">No se pudieron obtener las canciones de esta playlist.</span>') +
      "</div>";
  }

  if (resultados.length === 0) {
    html += '<p class="vacio">Sin resultados.</p>';
    cont.innerHTML = html;
    return;
  }

  html += '<div class="grid-resultados">';
  resultados.forEach((r, i) => {
    const thumb = r.thumbnail || "";
    // Control de la derecha: si ya está en la cola, mostramos una píldora
    // informativa (no se puede re-añadir); si no, el botón ＋.
    const ec = estadoEnCola(r);
    const accion =
      ec === "completado"
        ? '<span class="pill pill-descargado" title="Ya descargado">✓ Descargado</span>'
        : ec === "en_cola"
        ? '<span class="pill pill-en-cola" title="Ya está en la cola">✓ En cola</span>'
        : '<button class="btn-add-cola" data-i="' + i + '" title="Añadir a la cola" aria-label="Añadir a la cola">＋</button>';
    html +=
      '<div class="resultado' + (ec ? " ya-en-cola" : "") + '" data-i="' + i + '">' +
      (thumb
        ? '<img class="resultado-thumb" src="' + esc(thumb) + '" alt="" loading="lazy" onerror="this.style.visibility=\'hidden\'">'
        : '<div class="resultado-thumb sin-thumb"></div>') +
      '<div class="resultado-info">' +
      '<div class="resultado-titulo">' + esc(r.titulo || "Sin título") + "</div>" +
      '<div class="resultado-meta">' +
      esc(r.canal || "") +
      (r.duracion ? ' · <span class="dur">' + esc(r.duracion) + "</span>" : "") +
      "</div>" +
      "</div>" +
      accion +
      "</div>";
  });
  html += "</div>";
  cont.innerHTML = html;

  // Listeners: añadir individual.
  cont.querySelectorAll(".btn-add-cola").forEach((btn) => {
    btn.addEventListener("click", () => {
      const i = parseInt(btn.dataset.i, 10);
      const r = resultados[i];
      if (r) anadirACola(r, btn);
    });
  });

  // Listener: añadir toda la playlist.
  const btnTodo = $("#btn-anadir-todo");
  if (btnTodo) {
    btnTodo.addEventListener("click", () => anadirVarios(resultados, btnTodo));
  }
}

// Añade un único resultado a la cola enviando carpetaDestino y bitrate.
async function anadirACola(r, btn) {
  if (btn) btn.disabled = true;
  try {
    await pedirJSON("/api/cola/agregar", {
      method: "POST",
      body: JSON.stringify({
        url: r.url,
        titulo: r.titulo || "",
        thumbnail: r.thumbnail || "",
        duracion: r.duracion || "",
        canal: r.canal || "",
        carpeta: estado.carpetaDestino,
        bitrate: estado.bitrate,
      }),
    });
    avisar("Añadido a la cola", "ok");
    if (btn) {
      btn.textContent = "✓";
      setTimeout(() => {
        btn.textContent = "＋";
        btn.disabled = false;
      }, 1200);
    }
  } catch (e) {
    avisar("No se pudo añadir: " + e.message, "error");
    if (btn) btn.disabled = false;
  }
}

// Añade múltiples resultados (playlist / "añadir todo") en un solo POST.
async function anadirVarios(resultados, btn) {
  if (!resultados || resultados.length === 0) return;
  const textoOriginal = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Añadiendo…";
  }
  const items = resultados.map((r) => ({
    url: r.url,
    titulo: r.titulo || "",
    thumbnail: r.thumbnail || "",
    duracion: r.duracion || "",
    canal: r.canal || "",
  }));
  try {
    const datos = await pedirJSON("/api/cola/agregar_varios", {
      method: "POST",
      body: JSON.stringify({
        items: items,
        carpeta: estado.carpetaDestino,
        bitrate: estado.bitrate,
      }),
    });
    const n = (datos && datos.ids) ? datos.ids.length : items.length;
    avisar("Añadidas " + n + " canciones a la cola", "ok");
    if (btn) btn.textContent = "✓ Añadidas (" + n + ")";
  } catch (e) {
    avisar("No se pudo añadir todo: " + e.message, "error");
    if (btn) {
      btn.disabled = false;
      btn.textContent = textoOriginal || "＋ Añadir todo";
    }
  }
}

function initBusqueda() {
  const btn = $("#btn-buscar");
  const input = $("#input-buscar");
  if (btn) btn.addEventListener("click", buscar);
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        buscar();
      }
    });
  }
}

// ===========================================================================
// Cola (GET /api/cola + acciones)
// ===========================================================================

async function cargarCola() {
  const lista = $("#lista-cola");
  if (!lista) return;
  try {
    const datos = await pedirJSON("/api/cola");
    renderCola((datos && datos.items) || []);
  } catch (e) {
    lista.innerHTML = '<p class="vacio">No se pudo cargar la cola: ' + esc(e.message) + "</p>";
  }
}

function actualizarBadgeCola(items) {
  const badge = $("#badge-cola");
  if (!badge) return;
  // Contamos los pendientes/activos (no terminados).
  const pendientes = items.filter(
    (it) => it.estado === "en_cola" || it.estado === "descargando"
  ).length;
  if (pendientes > 0) {
    badge.textContent = String(pendientes);
    badge.style.display = "";
  } else {
    badge.textContent = "";
    badge.style.display = "none";
  }
}

function renderCola(items) {
  const lista = $("#lista-cola");
  if (!lista) return;
  actualizarBadgeCola(items);

  // Mantener sincronizado el indicador "ya en la cola" del buscador.
  recalcularColaPorId(items);
  marcarResultadosEnCola();

  if (!items || items.length === 0) {
    lista.innerHTML = '<p class="vacio">La cola está vacía. Busca canciones y añádelas.</p>';
    return;
  }

  let html = "";
  items.forEach((it) => {
    const estadoClase =
      it.estado === "descargando" ? " descargando" :
      it.estado === "completado" ? " completado" :
      it.estado === "error" ? " error" : "";
    const progreso = typeof it.progreso === "number" ? it.progreso : 0;
    const meta = [];
    if (it.canal) meta.push(esc(it.canal));
    if (it.duracion) meta.push(esc(it.duracion));
    meta.push(esc(textoEstado(it)));
    const thumb = it.thumbnail || "";

    html +=
      '<div class="item-cola' + estadoClase + '" data-id="' + esc(it.id) + '">' +
      (thumb
        ? '<img class="item-cola-thumb" src="' + esc(thumb) + '" alt="" loading="lazy" onerror="this.style.visibility=\'hidden\'">'
        : '<div class="item-cola-thumb sin-thumb"></div>') +
      '<div class="item-cola-info">' +
      '<div class="item-cola-titulo">' + esc(it.titulo || it.url || "Sin título") + "</div>" +
      '<div class="item-cola-meta">' + meta.join(" · ") + "</div>" +
      '<div class="barra-contenedor"' + (it.estado === "descargando" ? "" : ' style="display:none"') + ">" +
      '<div class="barra" style="width:' + progreso + '%"></div>' +
      "</div>" +
      "</div>" +
      (it.estado === "en_cola"
        ? '<button class="item-cola-eliminar" data-id="' + esc(it.id) + '" title="Eliminar" aria-label="Eliminar">✕</button>'
        : "") +
      "</div>";
  });
  lista.innerHTML = html;

  lista.querySelectorAll(".item-cola-eliminar").forEach((btn) => {
    btn.addEventListener("click", () => eliminarDeCola(btn.dataset.id));
  });
}

// Texto legible del estado de un ítem.
function textoEstado(it) {
  switch (it.estado) {
    case "en_cola": return "En cola";
    case "descargando": return "Descargando…";
    case "completado": return "Completado";
    case "error": return it.error ? "Error: " + it.error : "Error";
    default: return it.estado || "";
  }
}

async function eliminarDeCola(id) {
  if (!id) return;
  try {
    await pedirJSON("/api/cola/eliminar", {
      method: "POST",
      body: JSON.stringify({ id: id }),
    });
    // El servidor emite cola_actualizada por SSE; recargamos por si acaso.
    cargarCola();
  } catch (e) {
    avisar("No se pudo eliminar: " + e.message, "error");
  }
}

async function descargarCola() {
  try {
    await pedirJSON("/api/cola/descargar", { method: "POST" });
    avisar("Descarga iniciada", "ok");
  } catch (e) {
    avisar("No se pudo iniciar la descarga: " + e.message, "error");
  }
}

async function limpiarCola() {
  try {
    await pedirJSON("/api/cola/limpiar", { method: "POST" });
    cargarCola();
  } catch (e) {
    avisar("No se pudo limpiar: " + e.message, "error");
  }
}

function initCola() {
  const bDesc = $("#btn-descargar-cola");
  const bLimp = $("#btn-limpiar-cola");
  const bExpl = $("#btn-explorar");
  const selBit = $("#select-bitrate");
  if (bDesc) bDesc.addEventListener("click", descargarCola);
  if (bLimp) bLimp.addEventListener("click", limpiarCola);
  if (bExpl) bExpl.addEventListener("click", abrirExplorador);
  if (selBit) {
    selBit.addEventListener("change", () => {
      estado.bitrate = selBit.value;
    });
  }
}

// ===========================================================================
// SSE (GET /api/eventos) con reconexión backoff
// ===========================================================================

let fuenteEventos = null;
let reconexionMs = 1000;
const RECONEXION_MAX = 30000;

function conectarSSE() {
  if (fuenteEventos) {
    try { fuenteEventos.close(); } catch (e) { /* ignorar */ }
  }
  fuenteEventos = new EventSource("/api/eventos");

  fuenteEventos.onopen = () => {
    reconexionMs = 1000; // reset del backoff al conectar bien
  };

  fuenteEventos.onmessage = (ev) => {
    if (!ev.data) return;
    let datos;
    try {
      datos = JSON.parse(ev.data);
    } catch (e) {
      return; // heartbeat o dato no-JSON: ignorar
    }
    manejarEvento(datos);
  };

  fuenteEventos.onerror = () => {
    // Forzamos un backoff controlado en lugar del reintento automático.
    try { fuenteEventos.close(); } catch (e) { /* ignorar */ }
    fuenteEventos = null;
    setTimeout(conectarSSE, reconexionMs);
    reconexionMs = Math.min(reconexionMs * 2, RECONEXION_MAX);
  };
}

function manejarEvento(datos) {
  if (!datos || !datos.tipo) return;
  switch (datos.tipo) {
    case "cola_actualizada":
      // El backend manda la lista completa; renderizamos directamente.
      if (Array.isArray(datos.items)) {
        renderCola(datos.items);
      } else {
        cargarCola();
      }
      break;
    case "descargando":
      marcarDescargando(datos.id, datos.titulo);
      break;
    case "progreso":
      actualizarProgreso(datos.id, datos.progreso, datos.mensaje);
      break;
    case "completado":
      // Refrescamos la cola; el badge se recalcula al renderizar.
      cargarCola();
      break;
    case "error":
      marcarError(datos.id, datos.error);
      break;
    default:
      break;
  }
}

// Marca visualmente un ítem como descargando sin recargar toda la cola.
function marcarDescargando(id, titulo) {
  const el = document.querySelector('.item-cola[data-id="' + cssEscapar(id) + '"]');
  if (!el) {
    cargarCola();
    return;
  }
  el.classList.remove("completado", "error");
  el.classList.add("descargando");
  const cont = el.querySelector(".barra-contenedor");
  if (cont) cont.style.display = "";
  const elimBtn = el.querySelector(".item-cola-eliminar");
  if (elimBtn) elimBtn.remove();
}

// Actualiza la barra de progreso de un ítem en descarga.
function actualizarProgreso(id, progreso, mensaje) {
  const el = document.querySelector('.item-cola[data-id="' + cssEscapar(id) + '"]');
  if (!el) return;
  el.classList.add("descargando");
  const cont = el.querySelector(".barra-contenedor");
  if (cont) cont.style.display = "";
  const barra = el.querySelector(".barra");
  if (barra && typeof progreso === "number") {
    const pct = Math.max(0, Math.min(100, progreso));
    barra.style.width = pct + "%";
  }
  if (mensaje) {
    const meta = el.querySelector(".item-cola-meta");
    if (meta) meta.textContent = mensaje; // textContent: seguro
  }
}

function marcarError(id, error) {
  const el = document.querySelector('.item-cola[data-id="' + cssEscapar(id) + '"]');
  if (!el) {
    cargarCola();
    return;
  }
  el.classList.remove("descargando", "completado");
  el.classList.add("error");
  const meta = el.querySelector(".item-cola-meta");
  if (meta) meta.textContent = error ? "Error: " + error : "Error"; // textContent: seguro
  const cont = el.querySelector(".barra-contenedor");
  if (cont) cont.style.display = "none";
}

// ===========================================================================
// Biblioteca (GET /api/biblioteca?q=)
// ===========================================================================

async function cargarBiblioteca() {
  const lista = $("#lista-biblioteca");
  if (!lista) return;
  const inp = $("#input-biblioteca");
  const q = (inp && inp.value.trim()) || "";
  lista.innerHTML = '<p class="cargando">Cargando biblioteca…</p>';
  try {
    const datos = await pedirJSON("/api/biblioteca?q=" + encodeURIComponent(q));
    estado.biblioteca = (datos && datos.items) || [];
    renderBiblioteca(estado.biblioteca);
  } catch (e) {
    lista.innerHTML = '<p class="vacio">No se pudo cargar la biblioteca: ' + esc(e.message) + "</p>";
  }
}

function renderBiblioteca(items) {
  const lista = $("#lista-biblioteca");
  if (!lista) return;
  if (!items || items.length === 0) {
    lista.innerHTML = '<p class="vacio">No hay música todavía. Descarga algo desde Buscar.</p>';
    return;
  }
  let html = "";
  items.forEach((it, i) => {
    const meta = [];
    if (it.artista) meta.push(esc(it.artista));
    if (it.album) meta.push(esc(it.album));
    html +=
      '<div class="track" data-i="' + i + '" tabindex="0" role="button" aria-label="Reproducir">' +
      '<span class="btn-play-track" data-i="' + i + '" aria-hidden="true">▶</span>' +
      '<div class="track-info">' +
      '<div class="track-titulo">' + esc(it.titulo || it.archivo || "Sin título") + "</div>" +
      '<div class="track-meta">' + (meta.join(" · ") || "—") + "</div>" +
      "</div>" +
      '<span class="track-dur">' + esc(it.duracion || "") + "</span>" +
      '<button class="track-carpeta" data-archivo="' + esc(it.archivo) + '" title="Abrir carpeta" aria-label="Abrir carpeta">📂</button>' +
      "</div>";
  });
  lista.innerHTML = html;

  // YouTube Music-style: la fila entera reproduce (excepto el botón de carpeta).
  lista.querySelectorAll(".track").forEach((row) => {
    const reproducir = () => reproducirIndice(parseInt(row.dataset.i, 10));
    row.addEventListener("click", (e) => {
      if (e.target.closest(".track-carpeta")) return;
      reproducir();
    });
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        reproducir();
      }
    });
  });
  lista.querySelectorAll(".track-carpeta").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      abrirCarpetaDe(btn.dataset.archivo);
    });
  });
}

// Abre, en el explorador del sistema, la carpeta que contiene el archivo.
async function abrirCarpetaDe(archivo) {
  try {
    await pedirJSON("/api/abrir-carpeta", {
      method: "POST",
      body: JSON.stringify({ archivo: archivo }),
    });
  } catch (e) {
    avisar("No se pudo abrir la carpeta: " + e.message, "error");
  }
}

function initBiblioteca() {
  const input = $("#input-biblioteca");
  if (input) {
    let t = null;
    input.addEventListener("input", () => {
      clearTimeout(t);
      t = setTimeout(cargarBiblioteca, 250);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        clearTimeout(t);
        cargarBiblioteca();
      }
    });
  }
}

// ===========================================================================
// Historial (GET /api/historial)
// ===========================================================================

async function cargarHistorial() {
  const lista = $("#lista-historial");
  if (!lista) return;
  lista.innerHTML = '<p class="cargando">Cargando historial…</p>';
  try {
    const datos = await pedirJSON("/api/historial");
    renderHistorial((datos && datos.items) || []);
  } catch (e) {
    lista.innerHTML = '<p class="vacio">No se pudo cargar el historial: ' + esc(e.message) + "</p>";
  }
}

function renderHistorial(items) {
  const lista = $("#lista-historial");
  if (!lista) return;
  if (!items || items.length === 0) {
    lista.innerHTML = '<p class="vacio">Sin descargas todavía.</p>';
    return;
  }
  let html = "";
  items.forEach((it) => {
    const tieneArchivo = !!it.archivo;
    html +=
      '<div class="hist-item">' +
      '<div class="hist-info">' +
      '<div class="hist-titulo">' + esc(it.titulo || "Sin título") + "</div>" +
      '<div class="hist-meta">' +
      esc(it.canal || "") +
      (it.completado ? " · " + esc(formatearFecha(it.completado)) : "") +
      "</div>" +
      "</div>" +
      (tieneArchivo
        ? '<button class="hist-reproducir btn-acento" data-archivo="' + esc(it.archivo) + '" title="Reproducir" aria-label="Reproducir">▶</button>'
        : "") +
      "</div>";
  });
  lista.innerHTML = html;

  lista.querySelectorAll(".hist-reproducir").forEach((btn) => {
    btn.addEventListener("click", () => {
      reproducirArchivoSuelto(btn.dataset.archivo);
    });
  });
}

// Formatea una fecha ISO-8601 a algo legible; si falla, devuelve el original.
function formatearFecha(iso) {
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch (e) {
    return iso;
  }
}

// ===========================================================================
// Reproductor (<audio id="audio-player">)
// ===========================================================================

function audio() {
  return $("#audio-player");
}

function mostrarReproductor() {
  const rep = $("#reproductor");
  if (rep) rep.classList.remove("oculto");
}

// Reproduce el track de la biblioteca en el índice dado (cola de reproducción).
function reproducirIndice(i) {
  if (i < 0 || i >= estado.biblioteca.length) return;
  estado.indiceActual = i;
  const track = estado.biblioteca[i];
  cargarYReproducir(track.archivo, track.titulo, track.artista, track.thumbnail);
}

// Reproduce un archivo suelto (p. ej. desde historial) que no está en la lista
// de biblioteca cargada. Anterior/siguiente no aplican hasta cargar biblioteca.
function reproducirArchivoSuelto(archivo) {
  // Si el archivo coincide con uno de la biblioteca cargada, usamos su índice.
  const idx = estado.biblioteca.findIndex((t) => t.archivo === archivo);
  if (idx >= 0) {
    reproducirIndice(idx);
    return;
  }
  estado.indiceActual = -1;
  cargarYReproducir(archivo, archivo, "", "");
}

function cargarYReproducir(archivo, titulo, artista, thumbnail) {
  const a = audio();
  if (!a || !archivo) return;
  a.src = urlAudio(archivo);
  const elTit = $("#player-titulo");
  const elArt = $("#player-artista");
  const elThumb = $("#player-thumb");
  if (elTit) elTit.textContent = titulo || archivo || "";
  if (elArt) elArt.textContent = artista || "";
  if (elThumb) {
    if (thumbnail) {
      elThumb.src = thumbnail;
      elThumb.style.display = "";
    } else {
      elThumb.removeAttribute("src");
      elThumb.style.display = "none";
    }
  }
  mostrarReproductor();
  const p = a.play();
  if (p && typeof p.catch === "function") {
    p.catch((e) => avisar("No se pudo reproducir: " + (e && e.message ? e.message : ""), "error"));
  }
  actualizarBotonPlay();
}

function actualizarBotonPlay() {
  const btn = $("#btn-play");
  const a = audio();
  if (!btn || !a) return;
  btn.textContent = a.paused ? "▶" : "⏸";
}

function alternarPlay() {
  const a = audio();
  if (!a) return;
  if (!a.src) return;
  if (a.paused) {
    const p = a.play();
    if (p && typeof p.catch === "function") p.catch(() => {});
  } else {
    a.pause();
  }
  actualizarBotonPlay();
}

function reproducirAnterior() {
  if (estado.biblioteca.length === 0) return;
  if (estado.indiceActual <= 0) {
    reproducirIndice(0);
  } else {
    reproducirIndice(estado.indiceActual - 1);
  }
}

function reproducirSiguiente() {
  if (estado.biblioteca.length === 0) return;
  if (estado.indiceActual < 0) {
    reproducirIndice(0);
  } else if (estado.indiceActual < estado.biblioteca.length - 1) {
    reproducirIndice(estado.indiceActual + 1);
  }
  // Si es el último, no hace nada (no hay bucle).
}

function initReproductor() {
  const a = audio();
  const btnPlay = $("#btn-play");
  const btnAnt = $("#btn-anterior");
  const btnSig = $("#btn-siguiente");
  const seek = $("#player-seek");
  const vol = $("#player-volumen");
  const elTiempo = $("#player-tiempo");
  const elDur = $("#player-duracion");

  if (btnPlay) btnPlay.addEventListener("click", alternarPlay);
  if (btnAnt) btnAnt.addEventListener("click", reproducirAnterior);
  if (btnSig) btnSig.addEventListener("click", reproducirSiguiente);

  if (!a) return;

  // Fija el porcentaje de relleno (var CSS --progreso) que el CSS usa para
  // pintar la parte ya recorrida de los range (seek y volumen).
  const fijarProgreso = (el, pct) => {
    if (el) el.style.setProperty("--progreso", Math.max(0, Math.min(100, pct)) + "%");
  };

  // Estado inicial de volumen (el input ya está en escala 0-1).
  if (vol) {
    a.volume = parseFloat(vol.value);
    if (isNaN(a.volume)) a.volume = 1;
    fijarProgreso(vol, a.volume * 100);
    vol.addEventListener("input", () => {
      a.volume = Math.max(0, Math.min(1, parseFloat(vol.value)));
      fijarProgreso(vol, a.volume * 100);
    });
  }

  // Seek bidireccional: usuario arrastra → currentTime; timeupdate → barra.
  if (seek) {
    fijarProgreso(seek, 0);
    seek.addEventListener("input", () => {
      estado.arrastrandoSeek = true;
      fijarProgreso(seek, parseFloat(seek.value));
      if (a.duration && !isNaN(a.duration)) {
        const t = (parseFloat(seek.value) / 100) * a.duration;
        if (elTiempo) elTiempo.textContent = formatearTiempo(t);
      }
    });
    seek.addEventListener("change", () => {
      if (a.duration && !isNaN(a.duration)) {
        a.currentTime = (parseFloat(seek.value) / 100) * a.duration;
      }
      estado.arrastrandoSeek = false;
    });
  }

  a.addEventListener("loadedmetadata", () => {
    if (elDur) elDur.textContent = formatearTiempo(a.duration);
    if (seek) seek.value = "0";
    fijarProgreso(seek, 0);
    if (elTiempo) elTiempo.textContent = "0:00";
  });

  a.addEventListener("timeupdate", () => {
    if (elTiempo && !estado.arrastrandoSeek) {
      elTiempo.textContent = formatearTiempo(a.currentTime);
    }
    if (seek && a.duration && !isNaN(a.duration) && !estado.arrastrandoSeek) {
      const pct = (a.currentTime / a.duration) * 100;
      seek.value = String(pct);
      fijarProgreso(seek, pct);
    }
  });

  a.addEventListener("play", actualizarBotonPlay);
  a.addEventListener("pause", actualizarBotonPlay);
  a.addEventListener("ended", () => {
    actualizarBotonPlay();
    reproducirSiguiente();
  });
}

// ===========================================================================
// Explorador de carpetas (overlay #overlay-carpetas)
// ===========================================================================

async function abrirExplorador() {
  const overlay = $("#overlay-carpetas");
  if (!overlay) return;
  overlay.classList.remove("oculto");
  await navegarExplorador(estado.rutaExplorador || "");
}

function cerrarExplorador() {
  const overlay = $("#overlay-carpetas");
  if (overlay) overlay.classList.add("oculto");
}

async function navegarExplorador(ruta) {
  const lista = $("#lista-carpetas");
  const elRuta = $("#ruta-explorador");
  const btnSubir = $("#btn-subir-carpeta");
  if (!lista) return;
  lista.innerHTML = '<p class="cargando">Cargando…</p>';
  try {
    const datos = await pedirJSON("/api/carpetas?ruta=" + encodeURIComponent(ruta || ""));
    estado.rutaExplorador = datos.ruta || "";
    if (elRuta) {
      elRuta.textContent = estado.rutaExplorador
        ? "descargas/" + estado.rutaExplorador
        : "descargas/ (raíz)";
    }
    if (btnSubir) btnSubir.disabled = !datos.puede_subir;
    renderCarpetas(datos.items || []);
  } catch (e) {
    lista.innerHTML = '<p class="vacio">No se pudo abrir: ' + esc(e.message) + "</p>";
  }
}

function renderCarpetas(items) {
  const lista = $("#lista-carpetas");
  if (!lista) return;
  // Solo se navega por carpetas; los archivos se listan informativos.
  let html = "";
  items.forEach((it) => {
    if (it.es_carpeta) {
      html +=
        '<button class="carpeta-item" data-ruta="' + esc(it.ruta) + '">' +
        '<span class="carpeta-icono">📁</span>' +
        '<span class="carpeta-nombre">' + esc(it.nombre) + "</span>" +
        "</button>";
    } else {
      html +=
        '<div class="carpeta-item es-archivo">' +
        '<span class="carpeta-icono">🎵</span>' +
        '<span class="carpeta-nombre">' + esc(it.nombre) + "</span>" +
        "</div>";
    }
  });
  if (!html) {
    lista.innerHTML = '<p class="vacio">Carpeta vacía.</p>';
    return;
  }
  lista.innerHTML = html;

  lista.querySelectorAll(".carpeta-item[data-ruta]").forEach((btn) => {
    btn.addEventListener("click", () => navegarExplorador(btn.dataset.ruta));
  });
}

async function crearCarpeta(e) {
  if (e) e.preventDefault();
  const input = $("#input-nueva-carpeta");
  if (!input) return;
  const nombre = input.value.trim();
  if (!nombre) return;
  try {
    await pedirJSON("/api/carpetas/crear", {
      method: "POST",
      body: JSON.stringify({ ruta_padre: estado.rutaExplorador || "", nombre: nombre }),
    });
    input.value = "";
    await navegarExplorador(estado.rutaExplorador || "");
  } catch (err) {
    avisar("No se pudo crear la carpeta: " + err.message, "error");
  }
}

// Fija la carpeta actual del explorador como destino de descargas.
function seleccionarDestino() {
  estado.carpetaDestino = estado.rutaExplorador || "";
  actualizarTextoDestino();
  cerrarExplorador();
}

// Refleja la carpeta destino actual en #ruta-destino.
function actualizarTextoDestino() {
  const elDest = $("#ruta-destino");
  if (elDest) {
    elDest.textContent = estado.carpetaDestino
      ? "descargas/" + estado.carpetaDestino
      : "descargas/ (raíz)";
  }
}

function initExplorador() {
  const btnSubir = $("#btn-subir-carpeta");
  const form = $("#form-nueva-carpeta");
  const overlay = $("#overlay-carpetas");

  if (btnSubir) {
    btnSubir.addEventListener("click", () => {
      const actual = estado.rutaExplorador || "";
      if (!actual) return;
      const partes = actual.split("/").filter(Boolean);
      partes.pop();
      navegarExplorador(partes.join("/"));
    });
  }
  if (form) form.addEventListener("submit", crearCarpeta);

  // Botón de seleccionar destino: por id conocido o por data-accion.
  const btnSel = $("#btn-seleccionar-destino") || document.querySelector('[data-accion="seleccionar-destino"]');
  if (btnSel) btnSel.addEventListener("click", seleccionarDestino);

  // Botón/zona de cierre del overlay (si existe).
  const btnCerrar = $("#btn-cerrar-overlay") || document.querySelector('[data-accion="cerrar-explorador"]');
  if (btnCerrar) btnCerrar.addEventListener("click", cerrarExplorador);

  // Clic en el fondo del overlay cierra (si el fondo es el propio overlay).
  if (overlay) {
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) cerrarExplorador();
    });
  }
  // Escape cierra el overlay.
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && overlay && !overlay.classList.contains("oculto")) {
      cerrarExplorador();
    }
  });
}

// ===========================================================================
// Configuración por defecto (GET /api/config)
// ===========================================================================

async function cargarConfig() {
  try {
    const datos = await pedirJSON("/api/config");
    if (datos) {
      estado.carpetaDestino = datos.carpeta_por_defecto || "";
      estado.bitrate = datos.bitrate_por_defecto || "320";
      // Aviso de ffmpeg: lo mostramos solo si el backend confirma que falta.
      const aviso = $("#aviso-ffmpeg");
      if (aviso) aviso.classList.toggle("oculto", datos.ffmpeg_disponible !== false);
    }
  } catch (e) {
    // Si falla, mantenemos los defaults locales ('' y '320').
    estado.carpetaDestino = estado.carpetaDestino || "";
    estado.bitrate = estado.bitrate || "320";
  }
  // Reflejar en la UI.
  const selBit = $("#select-bitrate");
  if (selBit) selBit.value = estado.bitrate;
  actualizarTextoDestino();
}

// ===========================================================================
// Inicialización en DOMContentLoaded
// ===========================================================================

function init() {
  initNavegacion();
  initBusqueda();
  initCola();
  initBiblioteca();
  initReproductor();
  initExplorador();

  conectarSSE();          // SSE primero para recibir actualizaciones de cola
  cargarCola();           // estado inicial de la cola
  cargarConfig();         // defaults de bitrate/destino
  cambiarVista("buscar"); // vista por defecto
}

document.addEventListener("DOMContentLoaded", init);
