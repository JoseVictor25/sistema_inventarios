"use strict";
document.addEventListener('submit', async (evento) => {
  const formulario = evento.target.closest('form[data-escpos]');
  if (!formulario) return;
  evento.preventDefault();
  const boton = evento.submitter || formulario.querySelector('button[type="submit"]');
  const estado = document.getElementById(formulario.dataset.estado);
  if (boton) boton.disabled = true;
  if (estado) { estado.classList.remove('error'); estado.textContent = 'Enviando a la cola de impresión…'; }
  try {
    const respuesta = await fetch(formulario.action, {
      method: 'POST', body: new FormData(formulario),
      headers: {'X-Requested-With': 'fetch'}, credentials: 'same-origin'
    });
    const texto = await respuesta.text();
    if (estado) {
      estado.classList.toggle('error', !respuesta.ok);
      estado.textContent = respuesta.ok ? texto : 'No se imprimió: ' + texto;
    }
  } catch (error) {
    if (estado) { estado.classList.add('error'); estado.textContent = 'No se pudo contactar con el sistema.'; }
  } finally { if (boton) boton.disabled = false; }
});
