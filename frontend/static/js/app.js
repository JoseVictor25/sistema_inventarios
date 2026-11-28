"use strict";

/* ── HTMX: permitir swap en respuestas 422 (validación del servidor) ── */
document.body.addEventListener("htmx:beforeSwap", (evento) => {
  if (evento.detail.xhr.status === 422) {
    evento.detail.shouldSwap = true;
    evento.detail.isError = false;
  }
});

/* ── Menú hamburguesa responsive ──
   Bootstrap JS (bundle con Popper) ya maneja data-bs-toggle="collapse".
   Este bloque: cierra el menú colapsado al hacer clic en un enlace de navegación,
   para que en móvil el usuario no deba cerrarlo manualmente. */
document.addEventListener('DOMContentLoaded', () => {
  const panel = document.getElementById('nav-collapsible');
  if (!panel) return;
  panel.querySelectorAll('a.nav-link[href]').forEach(enlace => {
    if (new URL(enlace.href).pathname === location.pathname) enlace.classList.add('active');
    if (enlace.classList.contains('active')) enlace.setAttribute('aria-current', 'page');
  });
  panel.addEventListener('click', evento => {
    if (evento.target.closest('a[href]') && window.bootstrap) bootstrap.Offcanvas.getInstance(panel)?.hide();
  });
  const ancho = matchMedia('(min-width: 992px)');
  ancho.addEventListener('change', () => {
    if (ancho.matches && window.bootstrap) bootstrap.Offcanvas.getInstance(panel)?.hide();
  });
});

document.addEventListener('DOMContentLoaded', () => {
  if (!window.bootstrap) return;
  const reducir = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.querySelectorAll('#mensajes .alert-success, #mensajes .alert-info').forEach(aviso => {
    window.setTimeout(() => {
      if (aviso.isConnected) {
        if (reducir) aviso.classList.remove('fade');
        bootstrap.Alert.getOrCreateInstance(aviso).close();
      }
    }, 6000);
  });
});

document.addEventListener('submit', evento => {
  const form = evento.target.closest('form[data-confirmar]');
  if (!form) return;
  if (form.dataset.confirmado === 'si') { delete form.dataset.confirmado; return; }
  evento.preventDefault();
  if (!form.checkValidity()) { form.reportValidity(); return; }
  const origen = evento.submitter || form.querySelector('button[type="submit"]');
  const mensaje = (form.dataset.confirmarMensaje || '').replace(/\{([^{}]+)\}/g, (_, campo) => {
    const elemento = form.elements.namedItem(campo);
    return elemento && 'value' in elemento ? elemento.value : '';
  });
  if (!window.bootstrap) {
    if (window.confirm(mensaje)) { form.dataset.confirmado = 'si'; form.requestSubmit(origen); }
    else origen?.focus();
    return;
  }
  const nodo = document.getElementById('modal-confirmacion');
  const modal = bootstrap.Modal.getOrCreateInstance(nodo);
  const aceptar = document.getElementById('modal-confirmacion-aceptar');
  document.getElementById('modal-confirmacion-titulo').textContent = form.dataset.confirmarTitulo || '';
  document.getElementById('modal-confirmacion-mensaje').textContent = mensaje;
  aceptar.textContent = form.dataset.confirmarBoton || 'Confirmar';
  aceptar.className = 'btn btn-' + (form.dataset.confirmarVariante === 'warning' ? 'warning' : 'danger');
  aceptar.onclick = () => { modal.hide(); form.dataset.confirmado = 'si'; form.requestSubmit(origen); };
  nodo.addEventListener('hidden.bs.modal', () => origen?.focus(), {once: true});
  modal.show();
});
