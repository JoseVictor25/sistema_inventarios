"use strict";

(function () {
  /**
   * Convierte cualquier valor monetario (string con coma o punto, o número)
   * a un número entero de centavos para evitar imprecisiones de punto flotante.
   */
  function centavos(valor) {
    if (typeof valor === "number") return Math.round(valor * 100);
    if (!valor) return 0;
    const limpio = String(valor).trim().replace(",", ".");
    const num = parseFloat(limpio);
    return isNaN(num) ? 0 : Math.round(num * 100);
  }

  /**
   * Formatea centavos a formato decimal "0.00".
   */
  function formatoMoneda(cents) {
    return (cents / 100).toFixed(2);
  }

  function recalcularPagos() {
    const contenedor = document.getElementById("lista-pagos");
    if (!contenedor) return;

    const totalSpan = document.getElementById("monto-total-val");
    const totalCents = totalSpan
      ? centavos(totalSpan.getAttribute("data-total") || totalSpan.textContent)
      : 0;

    const filas = contenedor.querySelectorAll(".fila-pago");
    let totalCubiertoCents = 0;
    let efectivoAplicadoCents = 0;
    let hayEfectivo = false;
    const metodosSeleccionados = new Set();
    let hayDuplicados = false;

    filas.forEach(function (fila) {
      const select = fila.querySelector(".select-metodo");
      const inputMonto = fila.querySelector(".input-monto-pago");
      const filaRef = fila.querySelector(".fila-referencia");
      const btnQuitar = fila.querySelector(".btn-quitar-metodo");

      // Botón quitar visible solo si hay más de 1 fila de pago
      if (btnQuitar) {
        btnQuitar.style.display = filas.length > 1 ? "" : "none";
      }

      if (select) {
        const opt = select.options[select.selectedIndex];
        const esEfectivo = opt ? opt.getAttribute("data-es-efectivo") === "1" : false;
        const metodoId = select.value;

        if (metodoId) {
          if (metodosSeleccionados.has(metodoId)) {
            hayDuplicados = true;
          }
          metodosSeleccionados.add(metodoId);
        }

        // Mostrar u ocultar campo de referencia de transacción
        if (filaRef) {
          filaRef.style.display = esEfectivo ? "none" : "";
        }

        const montoCents = centavos(inputMonto ? inputMonto.value : 0);
        totalCubiertoCents += montoCents;

        if (esEfectivo) {
          hayEfectivo = true;
          efectivoAplicadoCents += montoCents;
        }
      }
    });

    // 1. Resumen de cobertura y saldo pendiente
    const spanCubierto = document.getElementById("monto-cubierto-val");
    const spanPendiente = document.getElementById("monto-pendiente-val");
    const saldoPendienteCents = totalCents - totalCubiertoCents;

    if (spanCubierto) {
      spanCubierto.textContent = formatoMoneda(totalCubiertoCents);
    }

    if (spanPendiente) {
      if (saldoPendienteCents === 0) {
        spanPendiente.className = "fw-bold text-success";
        spanPendiente.textContent = "Bs 0.00 (Cubierto)";
      } else if (saldoPendienteCents > 0) {
        spanPendiente.className = "fw-bold text-danger";
        spanPendiente.textContent = "Bs " + formatoMoneda(saldoPendienteCents) + " (Falta)";
      } else {
        spanPendiente.className = "fw-bold text-warning";
        spanPendiente.textContent = "Bs " + formatoMoneda(Math.abs(saldoPendienteCents)) + " (Excede)";
      }
    }

    // 2. Sección de efectivo y cálculo de vuelto
    const secEfectivo = document.getElementById("seccion-efectivo");
    const spanEfAplicado = document.getElementById("efectivo-aplicado-val");
    const recvInput = document.getElementById("recv");
    const chgSpan = document.getElementById("chg");
    const avisoInsuficiente = document.getElementById("aviso-efectivo-insuficiente");

    if (secEfectivo) {
      secEfectivo.style.display = hayEfectivo ? "" : "none";
    }
    if (spanEfAplicado) {
      spanEfAplicado.textContent = formatoMoneda(efectivoAplicadoCents);
    }

    if (hayEfectivo && recvInput && chgSpan) {
      const recvCents = centavos(recvInput.value);
      if (recvCents > 0 && recvCents < efectivoAplicadoCents) {
        chgSpan.textContent = "Bs 0.00";
        if (avisoInsuficiente) avisoInsuficiente.style.display = "";
      } else {
        const cambioCents = Math.max(0, recvCents - efectivoAplicadoCents);
        chgSpan.textContent = "Bs " + formatoMoneda(cambioCents);
        if (avisoInsuficiente) avisoInsuficiente.style.display = "none";
      }
    }

    // 3. Control del botón añadir método (máximo el número total de métodos configurados)
    const btnAgregar = document.getElementById("btn-agregar-metodo");
    if (btnAgregar) {
      const template = document.getElementById("template-fila-pago");
      const totalMetodosPosibles = template
        ? template.content.querySelectorAll(".select-metodo option").length
        : 3;
      btnAgregar.disabled = filas.length >= totalMetodosPosibles;
    }

    // 4. Validación de botón de confirmar venta
    const btnConfirmar = document.getElementById("btn-confirmar-venta");
    if (btnConfirmar) {
      const cartTieneLineas = document.querySelectorAll(".linea-item").length > 0;
      const sinCaja = !!document.getElementById("alerta-caja-cerrada");

      const esValido =
        cartTieneLineas &&
        totalCents > 0 &&
        saldoPendienteCents === 0 &&
        !hayDuplicados &&
        !sinCaja;

      btnConfirmar.disabled = !esValido;
    }
  }

  function asignarEventosFila(fila) {
    const select = fila.querySelector(".select-metodo");
    const inputMonto = fila.querySelector(".input-monto-pago");
    const btnQuitar = fila.querySelector(".btn-quitar-metodo");

    if (select) {
      select.addEventListener("change", recalcularPagos);
    }
    if (inputMonto) {
      inputMonto.addEventListener("input", recalcularPagos);
    }
    if (btnQuitar) {
      btnQuitar.addEventListener("click", function () {
        const contenedor = document.getElementById("lista-pagos");
        if (!contenedor) return;
        if (contenedor.querySelectorAll(".fila-pago").length > 1) {
          fila.remove();
          recalcularPagos();
        }
      });
    }
  }

  function agregarFilaPago() {
    const contenedor = document.getElementById("lista-pagos");
    const template = document.getElementById("template-fila-pago");
    if (!contenedor || !template) return;

    const clon = template.content.cloneNode(true);
    const nuevaFila = clon.querySelector(".fila-pago");

    // Buscar el primer método aún no seleccionado
    const filasExistentes = contenedor.querySelectorAll(".fila-pago");
    const metodosUsados = new Set();
    filasExistentes.forEach(function (f) {
      const s = f.querySelector(".select-metodo");
      if (s) metodosUsados.add(s.value);
    });

    const nuevoSelect = nuevaFila.querySelector(".select-metodo");
    if (nuevoSelect) {
      for (let i = 0; i < nuevoSelect.options.length; i++) {
        if (!metodosUsados.has(nuevoSelect.options[i].value)) {
          nuevoSelect.selectedIndex = i;
          break;
        }
      }
    }

    // Pre-llenar el monto con el saldo pendiente restante
    const totalSpan = document.getElementById("monto-total-val");
    const totalCents = totalSpan
      ? centavos(totalSpan.getAttribute("data-total") || totalSpan.textContent)
      : 0;

    let cubiertoCents = 0;
    filasExistentes.forEach(function (f) {
      const inp = f.querySelector(".input-monto-pago");
      cubiertoCents += centavos(inp ? inp.value : 0);
    });

    const pendienteCents = Math.max(0, totalCents - cubiertoCents);
    const inputMonto = nuevaFila.querySelector(".input-monto-pago");
    if (inputMonto) {
      inputMonto.value = formatoMoneda(pendienteCents);
    }

    contenedor.appendChild(nuevaFila);
    asignarEventosFila(nuevaFila);
    recalcularPagos();
  }

  function inicializarEventosCarrito() {
    const contenedor = document.getElementById("lista-pagos");
    if (contenedor) {
      const filas = contenedor.querySelectorAll(".fila-pago");
      filas.forEach(function (f) {
        asignarEventosFila(f);
      });
    }

    const btnAgregar = document.getElementById("btn-agregar-metodo");
    if (btnAgregar) {
      // Remover listener previo si existe para no duplicar
      btnAgregar.onclick = agregarFilaPago;
    }

    const recvInput = document.getElementById("recv");
    if (recvInput) {
      recvInput.addEventListener("input", recalcularPagos);
    }

    recalcularPagos();
  }

  function inicializarBuscador() {
    const inputQ = document.getElementById("q");
    if (!inputQ) return;

    inputQ.focus();

    // Soporte para lector de código de barras y tecla Enter
    inputQ.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        const lista = document.getElementById("lista-productos");
        if (!lista) return;

        const primerBoton = lista.querySelector(".btn-agregar-producto");
        if (primerBoton) {
          primerBoton.click();
          inputQ.value = "";
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    inicializarBuscador();
    inicializarEventosCarrito();
  });

  document.body.addEventListener("htmx:afterSwap", function (evento) {
    const targetId = evento.detail.target ? evento.detail.target.id : "";
    if (targetId === "carrito") {
      inicializarEventosCarrito();
      const inputQ = document.getElementById("q");
      if (inputQ) inputQ.focus();
    } else if (targetId === "lista-productos") {
      const inputQ = document.getElementById("q");
      if (inputQ) inputQ.focus();
    }
  });
})();
