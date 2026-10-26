/* Solo representación: los cálculos monetarios se realizan con Decimal en Django. */
(() => {
  const datos = document.getElementById('datos-grafico');
  const lienzo = document.getElementById('grafico-ventas');
  if (!datos || !lienzo || !window.Chart) return;
  const grafico = JSON.parse(datos.textContent);
  new Chart(lienzo, {
    type: 'bar',
    data: {labels: grafico.etiquetas, datasets: [{label: 'Total de ventas', data: grafico.valores, backgroundColor: '#0d6efd'}]},
    options: {responsive: true, maintainAspectRatio: false, scales: {y: {beginAtZero: true}}}
  });
})();
