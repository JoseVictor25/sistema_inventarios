"use strict";
// Añade formularios con el prefijo del formset de Django; no calcula precios.
document.getElementById("agregar-formulario-presentacion")?.addEventListener("click", () => {
  const total = document.getElementById("id_presentaciones-TOTAL_FORMS");
  const plantilla = document.getElementById("presentacion-vacia");
  const destino = document.getElementById("formularios-presentaciones");
  const numero = Number(total.value);
  destino.insertAdjacentHTML("beforeend", plantilla.innerHTML.replaceAll("__prefix__", String(numero)));
  total.value = String(numero + 1);
  destino.lastElementChild.querySelector("input:not([type=hidden])")?.focus();
});
