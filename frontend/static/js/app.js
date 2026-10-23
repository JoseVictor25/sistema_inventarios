"use strict";
document.body.addEventListener("htmx:beforeSwap", (evento) => {
  if (evento.detail.xhr.status === 422) {
    evento.detail.shouldSwap = true;
    evento.detail.isError = false;
  }
});
