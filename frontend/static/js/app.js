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
