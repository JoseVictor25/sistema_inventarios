"use strict";

/**
 * Lógica auxiliar para la pantalla de registro de compras.
 * Calcula subtotales y total en vivo y previene el doble envío en el cliente.
 */
function recalcularTotales() {
  let total = 0;
  const filas = document.querySelectorAll(".linea-compra-fila");
  filas.forEach(fila => {
    const cantInput = fila.querySelector(".input-cantidad");
    const costoInput = fila.querySelector(".input-costo");
    const subtotalSpan = fila.querySelector(".subtotal-linea");

    const cant = parseFloat(cantInput ? cantInput.value : 0) || 0;
    const costo = parseFloat(costoInput ? costoInput.value : 0) || 0;
    const subtotal = Math.max(0, cant * costo);

    if (subtotalSpan) {
      subtotalSpan.textContent = subtotal.toFixed(2);
    }
    total += subtotal;
  });

  const totalSpan = document.getElementById("total-compra");
  if (totalSpan) {
    totalSpan.textContent = total.toFixed(2);
  }
}

document.addEventListener("input", function (e) {
  if (e.target.matches(".input-cantidad, .input-costo")) {
    recalcularTotales();
  }
});

document.addEventListener("htmx:afterSwap", function (e) {
  if (e.detail.target && e.detail.target.id === "lineas-compra") {
    recalcularTotales();
  }
});

const formCompra = document.getElementById("form-nueva-compra");
if (formCompra) {
  formCompra.addEventListener("submit", function (e) {
    const btn = document.getElementById("btn-guardar-compra");
    if (btn && !btn.disabled) {
      const filas = document.querySelectorAll(".linea-compra-fila");
      if (filas.length === 0) {
        e.preventDefault();
        alert("Debes agregar al menos un producto a la compra.");
        return;
      }
      btn.disabled = true;
      btn.textContent = "Guardando...";
    }
  });
}

document.addEventListener("DOMContentLoaded", recalcularTotales);
