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
document.addEventListener("DOMContentLoaded", () => {
  const toggler  = document.getElementById("menu-toggler");
  const navPanel = document.getElementById("nav-collapsible");

  if (!toggler || !navPanel) return;

  // Cerrar menú al hacer clic en cualquier enlace del área colapsable (solo móvil)
  navPanel.addEventListener("click", (e) => {
    const esEnlace = e.target.closest("a[href]");
    if (!esEnlace) return;
    // Solo actuar si el panel está expandido (viewport móvil)
    const estaExpandido = toggler.getAttribute("aria-expanded") === "true";
    if (estaExpandido && window.innerWidth < 768) {
      // Usar la API de Bootstrap Collapse si está disponible
      if (typeof bootstrap !== "undefined" && bootstrap.Collapse) {
        const instancia = bootstrap.Collapse.getOrCreateInstance(navPanel);
        instancia.hide();
      }
    }
  });
});
