"use strict";
document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('modal-qr');
  if (!modal) return;

  /** Devuelve true si alguna fila de pago activa tiene QR seleccionado. */
  const seleccionQR = () =>
    Array.from(document.querySelectorAll('#lista-pagos .select-metodo'))
      .some(s => s.selectedOptions[0]?.dataset.esQr === '1');

  /**
   * Calcula la suma de los montos asignados exclusivamente a filas QR.
   * Nunca devuelve el total global de la venta.
   * Devuelve null si no hay filas QR con importe válido > 0.
   */
  function calcularMontoQR() {
    let suma = 0;
    let encontrado = false;
    document.querySelectorAll('#lista-pagos .fila-pago').forEach(fila => {
      const select = fila.querySelector('.select-metodo');
      if (select?.selectedOptions[0]?.dataset.esQr !== '1') return;
      const val = parseFloat(fila.querySelector('.input-monto-pago')?.value);
      if (isFinite(val) && val > 0) {
        suma += val;
        encontrado = true;
      }
    });
    return encontrado ? suma : null;
  }

  /** Actualiza el texto del modal con el importe QR real, no con el total de la venta. */
  function actualizarImporteQR() {
    const monto = calcularMontoQR();
    const el = document.getElementById('qr-total');
    if (!el) return;
    if (monto === null || monto <= 0) {
      el.textContent = '—';
    } else {
      el.textContent = monto.toFixed(2);
    }
  }

  /**
   * Abre el modal QR solo si hay una fila QR con importe positivo válido.
   * Si el monto QR es cero, vacío o inválido, no presenta el modal.
   */
  function abrir() {
    if (!seleccionQR()) return;
    const monto = calcularMontoQR();
    if (monto === null || monto <= 0) return;   // importe QR inválido: no abrir
    actualizarImporteQR();
    const img = document.getElementById('qr-imagen');
    const aviso = document.getElementById('qr-ausente');
    img.hidden = true; aviso.hidden = false; aviso.textContent = 'Cargando imagen bancaria…';
    img.onload = () => { img.hidden = false; aviso.hidden = true; };
    img.onerror = () => { img.hidden = true; aviso.textContent = 'No hay una imagen QR disponible. Solicita al Dueño que la configure.'; };
    img.src = modal.dataset.imagen + '?v=' + Date.now();
    bootstrap.Modal.getOrCreateInstance(modal).show();
  }

  function invalidar() { const c = document.getElementById('qr-confirmado'); if (c) c.checked = false; }

  // Cambio de método de pago: actualizar modal si ya está abierto o abrirlo si QR fue seleccionado
  document.addEventListener('change', e => {
    if (!e.target.matches('.select-metodo')) return;
    invalidar();
    const instancia = bootstrap.Modal.getInstance(modal);
    if (instancia?._isShown) {
      // Modal ya abierto: actualizar importe sin recargar imagen
      actualizarImporteQR();
    } else {
      abrir();
    }
  });

  // Cambio de importe en cualquier fila: invalidar confirmación y actualizar modal si está visible
  document.addEventListener('input', e => {
    if (!e.target.closest('#lista-pagos')) return;
    invalidar();
    if (bootstrap.Modal.getInstance(modal)?._isShown) {
      actualizarImporteQR();
    }
  });

  // Botón «+ Añadir método»: abrir modal solo después de que el DOM se actualice
  document.addEventListener('click', e => {
    if (!e.target.closest('#btn-agregar-metodo')) return;
    invalidar();
    setTimeout(abrir, 0);
  });

  // Tras intercambio HTMX del carrito: recalcular importe QR (total puede haber cambiado)
  document.body.addEventListener('htmx:afterSwap', () => { invalidar(); actualizarImporteQR(); });

  // Bloquear confirmación de venta si hay QR pero no se marcó la casilla
  document.body.addEventListener('htmx:configRequest', e => {
    if (e.detail.elt.id === 'form-confirmar-venta' && seleccionQR() && !document.getElementById('qr-confirmado')?.checked) {
      e.preventDefault(); alert('Verifica y confirma manualmente la recepción del pago QR.');
    }
  });
});
