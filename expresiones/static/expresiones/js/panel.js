/* Panel en vivo: expresión estimada y probabilidades en vivo. */
"use strict";

(() => {
  const catalogo = leerJSON("datos-catalogo");
  const especiales = leerJSON("datos-emojis");
  const porClave = Object.fromEntries(catalogo.map((e) => [e.clave, e]));

  const emoji = document.getElementById("emoji-actual");
  const nombre = document.getElementById("nombre-actual");
  const detalle = document.getElementById("detalle-actual");
  const medidor = document.getElementById("medidor-actual");
  const filasProbabilidad = Object.fromEntries(
    [...document.querySelectorAll("#barras-probabilidad .barra")].map((f) => [f.dataset.clave, f]));

  /**
   * Porcentaje entero de una expresión. ÚNICA fuente de los números del panel:
   * estado.probabilidades redondeado con Math.round. La cabecera "Expresión
   * estimada" y la fila resaltada usan esta misma función, así nunca difieren.
   */
  function porcentaje(estado, clave) {
    const probabilidades = estado.probabilidades || {};
    return Math.round(probabilidades[clave] || 0);
  }

  function pintarBarra(fila, valor) {
    fila.querySelector(".pista span").style.width = `${Math.max(0, Math.min(100, valor))}%`;
    fila.querySelector(".valor").textContent = `${valor} %`;
  }

  function mostrarExpresion(estado) {
    const activa = estado.estado === "activa";
    let src = especiales.sin_rostro, texto = "—", info = "Cámara detenida", valor = 0, color = "#f2a516";
    if (activa && !estado.modelo.disponible) {
      info = "Modelo de emociones no disponible";
    } else if (activa && !estado.rostro) {
      info = "Sin rostro visible: colóquese frente a la cámara";
    } else if (activa && estado.expresion) {
      const e = porClave[estado.expresion];
      valor = porcentaje(estado, estado.expresion);
      src = e.emoji; texto = e.nombre; color = e.color;
      info = `Probabilidad actual del modelo: ${valor} %`;
    } else if (activa) {
      src = especiales.desconocida; texto = "No clara";
      info = "Ninguna expresión supera el mínimo de confianza";
    }
    if (emoji.getAttribute("src") !== src) {
      emoji.src = src;
      emoji.classList.add("salto");
      setTimeout(() => emoji.classList.remove("salto"), 250);
    }
    nombre.textContent = texto;
    detalle.textContent = info;
    medidor.style.width = `${valor}%`;
    medidor.style.background = color;
  }

  function mostrarProbabilidades(estado) {
    for (const [clave, fila] of Object.entries(filasProbabilidad)) {
      pintarBarra(fila, porcentaje(estado, clave));
      fila.classList.toggle("destacada", clave === estado.expresion);
    }
  }

  new ControlCamara((estado) => {
    mostrarExpresion(estado);
    mostrarProbabilidades(estado);
  });
})();
