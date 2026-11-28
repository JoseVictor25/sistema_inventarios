# Mejoras de frontend y avisos de guardado

Rama: `feature/mejoras-frontend`, creada desde `feature/impresion-tickets`. No se hizo push ni merge. Los cambios de impresión que estaban sin confirmar antes del trabajo permanecen en el árbol.

## Resultado por punto

| Punto | Estado | Resultado o límite |
|---|---|---|
| 0 | Hecho | Avisos de QR e impresión, cierre manual y automático, errores 422 sin éxito; pruebas de redirect y recarga. |
| 1 | Hecho | Botón ESC/POS en venta confirmada cuando está configurado; envío delegado compartido con comprobante. |
| 2 | Hecho | Historial activo solo en sus tres rutas, iconos y estado activo de QR e impresión. |
| 3 | Hecho | Filtros por fecha y vendedor, validación de 366 días, total y paginación de 20 con filtros. |
| 4 | Hecho | Cinco degradados solicitados y contraste con blanco comprobado por prueba WCAG. |
| 5 | Hecho | Modal único para desactivar producto, eliminar QR y cerrar caja; conserva el botón de envío. |
| 6 | Hecho | SVG locales y punto CSS; prueba rechaza símbolos y emojis en plantillas. |
| 7 | Hecho | Cero atributos `style="` en plantillas; visibilidad mediante `d-none`, incluida la lógica del POS. |
| 8 | Hecho | Paginación Bootstrap compartida, sin `?&page=` y con estados accesibles. |
| 9 | Hecho | Títulos de pestaña y un h1 en las 38 pantallas recorridas como Dueño. |
| 10 | Hecho | Una sola plantilla `_fila_pago.html` para la fila inicial y el template; flujo del POS probado en navegador. Los cambios simultáneos de iconos y clases alteran el HTML textual, pero conservan sus controles y valores. |
| 11 | Parcial | Se quitó el comentario obsoleto. Las reglas `.mensaje` siguen porque eliminarlas cambiaría los colores visibles de los avisos existentes. |
| 12 | Hecho | Todas las tablas tienen caption; prueba estructural recorre las plantillas. |
| 13 | Hecho | Login con campos Bootstrap, autocomplete, autofocus, marca local y errores como alerta. |
| 14 | Hecho | Estados vacíos con indicación útil, acción primaria única en productos e historial y margen uniforme del título. En caja, las dos acciones primarias están en ramas excluyentes. |
| 15 | Hecho | Historial de Git confirmó el texto del QR personalizado; la prueba ahora afirma el modal vigente. |

## Verificación

- `check`: `System check identified no issues (0 silenced).` [Salida completa](evidencias_frontend/check.txt).
- `makemigrations --check --dry-run`: `No changes detected`. [Salida completa](evidencias_frontend/migraciones.txt).
- `test --noinput`: **394 pruebas, OK**. [Salida completa, con rutas locales sustituidas](evidencias_frontend/pruebas_completas.txt).
- `scripts/recorrer_frontend.py`: 38 GET por rol Dueño y 38 por rol Vendedor, solo 200/403, sin HTML desequilibrado; Dueño con título no vacío y un h1.
- `scripts/capturar_frontend.py`: 39 pantallas, dos tamaños reales (1366×768 y 375×812), 78 [capturas](evidencias_frontend/capturas/), sin desbordamiento horizontal ni errores JavaScript observados. Se ejercitaron pagos mixtos, referencia, efectivo y vuelto en el DOM del POS.
- Búsquedas: cero `style="`, cero símbolos o emojis prohibidos y cero URLs externas `http(s)://` en recursos propios. La única llamada a `confirm(` es el fallback previsto en `app.js`.
- SQLite real, `.env` y los dos informes privados conservaron SHA-256 antes y después. [Huellas](evidencias_frontend/huellas_sha256.txt).
- `git diff --check`: sin errores de espacios.

## Pruebas existentes modificadas

- `backend/apps/core/tests/test_qr.py`: expectativa corregida del modal según el commit `28050cc`; añadidos casos de guardar, recargar, eliminar y error.
- `backend/apps/ventas/tests/test_comprobante.py`: añadidos avisos de configuración y ausencia de éxito en 422; la comprobación del `fetch` pasó a leer `escpos.js`, porque el script dejó de estar dentro del HTML. Este archivo ya tenía cambios de impresión sin confirmar y permanece sin commit.
- `backend/apps/ventas/tests/test_fase6.py`: nuevo caso del botón ESC/POS en la tarjeta del POS con cola simulada.

Pruebas nuevas: `test_historial_frontend.py`, `test_menu_frontend.py`, `test_frontend_static.py` y `test_paginacion_frontend.py`. No se cambió la prueba de “Ventas del día” ni el texto protegido “Ver / Imprimir comprobante” en el detalle.

## Límites

No se hizo impresión física, envío RAW real ni comprobación del corte o del papel de una impresora. Las capturas corresponden a datos ficticios; la pantalla de configuración inicial no se pudo fotografiar después de crear usuarios para el recorrido. La interacción del modal de confirmación queda pendiente de una prueba manual; sus atributos y los POST directos están cubiertos por pruebas.

## Git

Commits de código: `3cf4cc1` (ventas), `6f39e9f` (login), `9fa7df3` (navegación) y `7e4376c` (plantillas). Las evidencias y este informe tienen commits separados. Se conservan sin confirmar `backend/apps/ventas/tests/test_comprobante.py`, `frontend/templates/ventas/configurar_impresion.html`, `frontend/templates/ventas/venta_comprobante.html` y `docs/IMPRESION_TICKETS_RESULTADOS.md`, que ya estaban modificados al empezar. Las aportaciones de este trabajo a los tres primeros conviven con las correcciones previas; no se incluyeron en los commits para no atribuirlas a esta rama. Los informes privados y la evidencia previa de tickets tampoco se agregaron a Git.

La lista completa de archivos y `git diff --stat` se entrega en [archivos y diferencias](evidencias_frontend/archivos_y_diff.txt).
