/*
 * Funciones comunes de la interfaz:
 *  - api(): peticiones POST/GET con token CSRF y mensajes de error claros.
 *  - notificar(): avisos flotantes.
 *  - ControlCamara: botón iniciar/detener, video MJPEG, indicador de FPS y
 *    consulta periódica del estado. La cámara es siempre la de
 *    CAMARA_FUENTE (.env).
 */
"use strict";

const CSRF = document.querySelector('meta[name="csrf-token"]').content;

function leerJSON(id) {
  const nodo = document.getElementById(id);
  return nodo ? JSON.parse(nodo.textContent) : null;
}

async function api(url, datos = null) {
  const opciones = datos === null
    ? { method: "GET", headers: { "Accept": "application/json" } }
    : {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF, "Accept": "application/json" },
        body: JSON.stringify(datos),
      };
  try {
    const respuesta = await fetch(url, opciones);
    const tipo = respuesta.headers.get("Content-Type") || "";
    if (!tipo.includes("application/json")) {
      return { ok: false, mensaje: `El servidor respondió con un error (${respuesta.status}).` };
    }
    return await respuesta.json();
  } catch (error) {
    return { ok: false, sinConexion: true, mensaje: "No hay conexión con el servidor. ¿Sigue ejecutándose «python manage.py runserver»?" };
  }
}

function notificar(texto, tipo = "info", duracion = 4500) {
  const caja = document.getElementById("notificaciones");
  const nodo = document.createElement("div");
  nodo.className = `notificacion notificacion--${tipo}`;
  nodo.textContent = texto;
  caja.appendChild(nodo);
  setTimeout(() => nodo.remove(), duracion);
}

class ControlCamara {
  /**
   * @param {function} alActualizar  recibe el estado del servidor en cada consulta
   */
  constructor(alActualizar) {
    this.alActualizar = alActualizar || (() => {});
    this.video = document.getElementById("video");
    this.marcador = document.getElementById("marcador");
    this.marcadorTitulo = document.getElementById("marcador-titulo");
    this.marcadorTexto = document.getElementById("marcador-texto");
    this.btnCamara = document.getElementById("btn-camara");
    this.chip = document.getElementById("chip-camara");
    this.fps = document.getElementById("info-fps");
    this.ultimoEstado = null;
    this.ultimoError = null;
    this.temporizador = null;
    this.ocupado = false;
    this.errorEnServidor = false;

    // Un solo botón: inicia o detiene según el estado actual.
    this.btnCamara.addEventListener("click", () => {
      if (this.btnCamara.dataset.accion === "detener") this.detener();
      else this.iniciar();
    });
    this.video.addEventListener("error", () => this.reconectarVideo());
    // Al salir de la página se libera la cámara para que otra página pueda usarla.
    window.addEventListener("pagehide", () => {
      if (this.ultimoEstado && this.ultimoEstado.estado === "activa") {
        const datos = new FormData();
        datos.append("csrfmiddlewaretoken", CSRF);
        navigator.sendBeacon("/api/camara/detener/", datos);
      }
    });
    this.consultar();
  }

  marcadorMostrar(titulo, texto, cargando = false) {
    this.video.hidden = true;
    this.video.removeAttribute("src");
    this.marcador.hidden = false;
    this.marcadorTitulo.textContent = titulo;
    this.marcadorTexto.textContent = texto;
    const img = this.marcador.querySelector("img");
    let rueda = this.marcador.querySelector(".cargando");
    if (cargando && !rueda) {
      rueda = document.createElement("div");
      rueda.className = "cargando";
      this.marcador.prepend(rueda);
    }
    if (rueda) rueda.hidden = !cargando;
    if (img) img.hidden = cargando;
  }

  async iniciar() {
    if (this.ocupado) return;
    this.ocupado = true;
    this.btnCamara.disabled = true;
    this.marcadorMostrar("Abriendo la cámara…", "Si Windows pide permiso, acéptelo.", true);
    const r = await api("/api/camara/iniciar/", {});
    this.ocupado = false;
    if (!r.ok) {
      this.marcadorMostrar("No se pudo iniciar la cámara", r.mensaje || "Error desconocido.");
      notificar(r.mensaje || "No se pudo iniciar la cámara.", "error", 8000);
    }
    if (r.estado) this.aplicar(r.estado);
    else this.btnCamara.disabled = false;
  }

  async detener() {
    if (this.ocupado) return;
    this.btnCamara.disabled = true;
    const r = await api("/api/camara/detener/", {});
    if (r.estado) this.aplicar(r.estado);
    else this.btnCamara.disabled = false;
    if (!r.ok) notificar(r.mensaje, "error");
  }

  /** Texto e icono del botón principal: "Iniciar cámara" (play) o "Detener" (pausa). */
  mostrarBotonCamara(activa) {
    const accion = activa ? "detener" : "iniciar";
    this.btnCamara.dataset.accion = accion;
    this.btnCamara.querySelector(".boton__texto").textContent = activa ? "Detener" : "Iniciar cámara";
    for (const icono of this.btnCamara.querySelectorAll("[data-icono]")) {
      icono.hidden = icono.dataset.icono !== accion;
    }
  }

  mostrarVideo() {
    if (!this.video.hidden && this.video.getAttribute("src")) return;
    this.video.src = `/video/?t=${Date.now()}`;
    this.video.hidden = false;
    this.marcador.hidden = true;
  }

  reconectarVideo() {
    // El flujo MJPEG se cortó (por ejemplo, al detener o por la red).
    if (this.ultimoEstado && this.ultimoEstado.estado === "activa") {
      this.video.removeAttribute("src");
      setTimeout(() => this.mostrarVideo(), 800);
    }
  }

  aplicar(estado) {
    const anterior = this.ultimoEstado;
    this.ultimoEstado = estado;
    const activa = estado.estado === "activa";

    this.chip.className = "chip " + (activa ? "chip--activa" : estado.estado === "error" ? "chip--error" : "chip--neutro");
    this.chip.textContent = activa ? "Cámara activa"
                                   : estado.estado === "error" ? "Error de cámara" : "Cámara detenida";
    this.mostrarBotonCamara(activa);
    this.btnCamara.disabled = this.ocupado;
    this.fps.textContent = activa ? `${estado.fps.toFixed(1)} FPS` : "";

    if (activa) {
      this.mostrarVideo();
    } else if (estado.estado === "error") {
      this.marcadorMostrar("Problema con la cámara", estado.mensaje);
      if (this.ultimoError !== estado.mensaje && anterior && anterior.estado === "activa") {
        notificar(estado.mensaje, "error", 8000);
      }
      this.ultimoError = estado.mensaje;
    } else if (!this.ocupado) {
      this.marcadorMostrar("La cámara está apagada",
        "Pulse «Iniciar cámara» para comenzar. El video se procesa en su computadora y no se guarda.");
    }

    if (estado.advertencia && (!anterior || anterior.advertencia !== estado.advertencia)) {
      notificar(estado.advertencia, "error", 8000);
    }
    this.alActualizar(estado, anterior);
  }

  async consultar() {
    clearTimeout(this.temporizador);
    const r = await api("/api/estado/");
    if (r.ok && r.estado) {
      if (this.errorEnServidor) notificar("Conexión con el servidor restablecida.", "exito");
      this.errorEnServidor = false;
      this.aplicar(r.estado);
    } else if (!this.errorEnServidor) {
      this.errorEnServidor = true;
      notificar(r.mensaje || "No se pudo consultar el estado.", "error", 8000);
      this.marcadorMostrar("Sin conexión", r.mensaje || "");
      this.btnCamara.disabled = true;
    }
    const activa = this.ultimoEstado && this.ultimoEstado.estado === "activa";
    this.temporizador = setTimeout(() => this.consultar(), activa ? 400 : 2000);
  }
}
