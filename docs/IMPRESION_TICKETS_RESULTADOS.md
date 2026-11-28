# Impresión de comprobantes no fiscales

Rama: `feature/impresion-tickets`. El comprobante GET de `/ventas/<id>/comprobante/`
reutiliza `obtener_venta()` y exige `vender`. Muestra identificador, negocio,
fecha, cajero, cantidades, precio aplicado histórico, subtotales, total y cada
pago aplicado. No inventa monto recibido ni vuelto. El detalle, historial y mensaje
de confirmación enlazan al comprobante; la venta no abre impresión automáticamente.

La impresión HTML anterior se probó físicamente por el usuario con la DT-230 y
produjo espacios y saltos de página. El motor continuo descrito abajo sustituye la
vista previa HTML, pero su resultado en papel todavía requiere una nueva prueba.
La ruta Windows conserva `window.print()` como alternativa: el controlador puede
ignorar el alto solicitado. El PDF de una página y ESC/POS son salidas adicionales.
La impresión física nueva, el diálogo WebView2 y la cancelación requieren revisión
manual; no se afirma compatibilidad absoluta de hardware.

`/ventas/impresion/` permite a `gestionar_usuarios` guardar ancho, vista previa,
oferta posterior, impresión manual y mensaje en `DATA_DIR/impresion.json`. Valores
predeterminados: Windows, 80 mm, vista previa sí, oferta no, impresión manual sí.
El nombre comercial usa `NOMBRE_NEGOCIO` existente. La preferencia de impresora no
se guarda: la selección queda en el diálogo del controlador Windows. La preferencia
de oferta posterior controla si se muestra el enlace en el mensaje de venta
confirmada; nunca dispara impresión. Los enlaces del detalle e historial permanecen.
La opción de vista previa se almacena, pero la página de comprobante sigue
mostrándose antes del diálogo: no se automatiza una impresión sin validación real
de WebView2. La opción inicial está activada.
No hay modelos ni migraciones. El JSON hereda los permisos del directorio de datos
del modo temporal o instalado y está excluido de Git.

Archivos: `backend/apps/ventas/impresion.py`, `views.py`, `urls.py`,
`tests/test_comprobante.py`; `frontend/templates/ventas/venta_comprobante.html`,
`configurar_impresion.html`, `venta_lista.html`, `venta_detalle.html`,
`partials/_venta_confirmada.html`, `components/_menu.html`; `.gitignore`.

Para revisión manual aislada, iniciar la demostración temporal:

```powershell
.\venv\Scripts\python.exe scripts/revisar_navegacion_fase10.py
```

Usar las credenciales ficticias mostradas. En Historial de ventas abrir una venta
ficticia, pulsar Comprobante y luego Imprimir comprobante. Para registrar otra
venta ficticia, abrir primero una caja, agregar productos en POS y completar un
pago de prueba; abrir el comprobante desde el mensaje de confirmación. Probar el
diálogo con Microsoft Print to PDF y, por separado, con Tally DASCOM DT-230 y el
papel correcto. Cancelar un diálogo y verificar que la venta registrada persiste.

## Verificaciones

- `venv/Scripts/python.exe scripts/verificar_fase10.py --pruebas`: `check` correcto,
  `makemigrations --check --dry-run` correcto; suite: 376 pruebas, 375 aprobadas,
  una fallida. Evidencia: `%TEMP%/Inventarios_fase10_4r5t6lb9/test.txt`.
- Fallo ajeno a tickets: `apps.core.tests.test_qr.QRTests.test_pos_modal_y_confirmacion`
  exige el texto `Total de la venta: Bs`, pero el modal QR actual presenta
  `Importe a pagar por QR`, que corresponde al importe asignado a QR en pagos
  mixtos. No se cambió la prueba ni el flujo QR.
- Suite específica `apps.ventas.tests.test_comprobante`: 4 pruebas aprobadas;
  datos y SQLite temporales. Evidencia: `%TEMP%/Ticket_ultimo_l6w9oqr3`.
- Tras el ajuste del enlace de oferta, toda `apps.ventas.tests`: **34 pruebas
  aprobadas en 100,211 s**, `%TEMP%/Ticket_ventas_final_1oc7_p46/test.txt`.
- `git diff --check`: sin errores de espacios. Los cuatro archivos protegidos
  conservan los hashes registrados antes de esta implementación.

Pendientes: diálogo real WebView2, Print to PDF, Tally DASCOM DT-230, márgenes y
papel de 58/80 mm con controladores instalados, cancelación de impresión y
verificación visual. El nombre del producto no se guarda como instantánea en
`DetalleVenta`; si luego se renombra en el catálogo, un ticket reimpreso mostrará
el nombre actual. Precio, cantidades y pagos sí proceden de la venta histórica.

## Prueba de longitud variable (2026-11-06)

El CSS anterior usaba `@page { size: 80mm auto; }`: ese valor no garantiza una
altura derivada del contenido. El botón mide el alto real del ticket renderizado
tras cargar fuentes (`scrollHeight` y `getBoundingClientRect`), convierte píxeles
CSS a milímetros, añade 2 mm de resguardo y establece una regla `@page` de dos
longitudes antes de `window.print()`. `beforeprint` vuelve a calcular. El margen
inferior configurable es de 2 a 15 mm (predeterminado 4). La página impresa no
incluye botones ni márgenes de pantalla. La anchura sigue siendo 80 o 58 mm.
Si el contenido excede 3276 mm, el motor deberá paginar; no se afirma que el
controlador permita un rollo de cualquier longitud.

La solución sigue usando el controlador Windows. [Microsoft documenta](https://learn.microsoft.com/en-us/microsoft-edge/webview2/how-to/print)
que las dimensiones personalizadas de WebView2 requieren ancho y alto explícitos.
La [guía oficial de DT-230](https://www.dascomla.com/toolbox/downloads/DT-230_UG_V1_4-SP.pdf)
documenta compatibilidad ESC/POS y cortador, pero eso no verifica qué accesorio,
modo o ajuste del controlador está instalado en este equipo. No se enviaron
comandos RAW ni de corte. Para añadir ESC/POS opcional deben verificarse primero
el hardware y la emulación activos, con autorización y pruebas físicas. La opción
de corte queda pendiente por el mismo motivo. La consulta local `Get-Printer` y
`Get-PrinterDriver` devolvió `Acceso denegado (0x80041003)`.

Pruebas nuevas: casos de 1, 5 y 15 líneas, ancho 58 y 80 mm, margen inferior,
precio histórico, pagos y reimpresión sin cambios de negocio. El script
`scripts/verificar_ticket_pdf.py` genera HTML desde datos ficticios y solicita
PDF a Edge en TEMP; en este entorno Edge devolvió código 2147483651 antes de
producir el primer PDF. Por ello no se verificó el tamaño de página PDF ni la
salida física. Para reproducir con Python del entorno:

```powershell
.\venv\Scripts\python.exe scripts/verificar_ticket_pdf.py
```

En Windows, abrir la demostración temporal con
`.\venv\Scripts\python.exe scripts/revisar_navegacion_fase10.py`; entrar con las
credenciales ficticias, consultar la venta de ejemplo en Historial y abrir su
comprobante. Elegir la DT-230 en el diálogo, comprobar que el papel seleccionado
coincide con el ancho y que la vista previa muestre una sola página corta. Imprimir
primero un ticket de una línea, luego cinco y quince; medir la longitud física y
comprobar el margen y el corte, sin utilizar ventas reales. Repetir con Microsoft
Print to PDF y comparar dimensiones. Cancelar el diálogo y reabrir el comprobante
para verificar que la venta original permanece igual.

La ejecución más reciente de `scripts/verificar_fase10.py --pruebas` terminó con
`check=0`, `migraciones=0` y **378 pruebas: 377 aprobadas, una fallida** en
239,399 s. Evidencia: `%TEMP%/Inventarios_fase10_0vlw2z6z/test.txt`. Es el mismo
fallo anterior del texto del modal QR (`test_pos_modal_y_confirmacion`); no está
relacionado con el ticket. Los cuatro archivos protegidos conservaron sus SHA-256.
No se hizo commit ni push.

## Ajuste de márgenes y consumo de papel (2026-11-15)

El comprobante tenía `padding-top: 4mm` y `padding-bottom: 4mm`; además, la regla
dinámica solicitaba 2 mm de tolerancia. `html` y `body` ya usaban margen cero en
impresión, y los botones estaban en `display:none`, por lo que no ocupaban altura
impresa. Se redujo el padding superior predeterminado a **2 mm** y se aumentó el
inferior predeterminado a **5 mm**. El rango configurable superior es 1–10 mm y
el inferior continúa en 2–15 mm. Un `impresion.json` antiguo sin margen superior
hereda 2 mm y conserva su margen inferior anterior; no se sobrescribe la preferencia.

La medición de `ticket.scrollHeight` incluye texto, líneas envueltas, tabla,
encabezado, pie y ambos paddings. La altura solicitada es
`ceil(max(scrollHeight, boundingHeight) × 25,4 / 96) + 2 mm`, limitada a 3276 mm.
Los 2 mm finales son tolerancia de paginación; los paddings no se vuelven a sumar.
La anchura de pantalla y papel permanece en 80/58 mm. El controlador puede añadir
avance inicial/final o ignorar el tamaño de página solicitado; esos componentes
no pueden atribuirse al CSS sin comparar el PDF o la impresión física.

Prueba específica: **6 pruebas aprobadas en 18,468 s** con SQLite temporal en
`%TEMP%/Ticket_margenes_mxrrl04w`. Incluye 1, 5, 10 y 15 líneas,
configuración de márgenes y rangos inválidos, compatibilidad con configuración
antigua, pagos y permisos. `verificar_ticket_pdf.py` volvió a fallar antes de
generar el primer PDF: Edge devolvió **2147483651**. Evidencia temporal:
`%TEMP%/Inventarios_ticket_pdf_mi4ujrx8`. No se verificó el número de páginas,
los márgenes de un PDF ni el papel de la DT-230 en esta ejecución.

Para la prueba física: con datos ficticios, abrir
`.\venv\Scripts\python.exe scripts/revisar_navegacion_fase10.py`, iniciar sesión
con las credenciales mostradas, ir a Impresión de tickets y fijar superior 2 mm e
inferior 5 mm. Abrir una venta ficticia desde Historial → Comprobante → Imprimir.
Seleccionar Tally DASCOM DT-230, 80 mm, escala 100 % y márgenes del diálogo en
ninguno o mínimo si el controlador lo permite. Medir desde el inicio de la zona
imprimible hasta «Mi tienda», desde la última línea al corte y el papel sobrante.
Repetir con 1, 5, 10 y 15 productos y un nombre largo. Si la impresora adelanta
papel antes/después del trabajo pese a un PDF compacto, revisar la configuración
del controlador; no se enviaron comandos de corte ni ESC/POS.

La consulta local `Get-Printer` devolvió `Acceso denegado` (HRESULT `0x80041003`).
No se verificaron márgenes internos, avance previo, formato activo ni ajuste de
corte del controlador instalado. La causa física del espacio superior sigue
abierta; el CSS aportaba 4 mm y ahora aporta 2 mm. Se requiere nueva impresión
física antes de declarar resuelto el consumo de papel.

Para comparar cuatro longitudes sin registrar ventas reales, el verificador tiene
un modo que crea datos y HTML ficticios en una carpeta TEMP nueva:

```powershell
.\venv\Scripts\python.exe scripts/verificar_ticket_pdf.py --solo-html
```

La última ejecución aprobada generó `ticket_1.html`, `ticket_5.html`,
`ticket_10.html` y `ticket_15.html` en
`%TEMP%/Inventarios_ticket_pdf_u9jstyim`. Los importes y pagos del conjunto
ficticio se mantienen consistentes. Abrir cada HTML en Edge desde esa carpeta,
pulsar «Imprimir comprobante» y escoger la DT-230 con ancho 80 mm. Comparar
longitud, primer texto y última línea; después probar Microsoft Print to PDF.
Esto constituye una instrucción de prueba, no una validación física realizada.

Regresión completa final: `venv/Scripts/python.exe scripts/verificar_fase10.py
--pruebas` ejecutó `check` y `makemigrations --check --dry-run` correctamente.
Ejecutó **379 pruebas en 239,918 s: 378 aprobadas y una fallida**, la ya conocida
`apps.core.tests.test_qr.QRTests.test_pos_modal_y_confirmacion` (texto esperado del
modal QR distinto del actual). Evidencia: `%TEMP%/Inventarios_fase10_ws8nfiri`.
Los SHA-256 de SQLite, `.env` y ambos informes privados se mantuvieron idénticos;
`git diff --check` no reportó errores de espacios. Rama `feature/impresion-tickets`,
sin commit ni push.

## Motor continuo de comprobantes (2026-11-15)

**Causa comprobada:** la vista anterior era HTML con una regla `@page` creada por
JavaScript. En las pruebas físicas del usuario, el navegador/controlador siguió
paginando: separó pagos con 10 artículos y líneas con 15. Una medida DOM no
garantiza que el controlador acepte el alto solicitado; los tamaños ofrecidos por
Windows eran de longitud fija. La vista previa propia ahora usa una imagen única
sin páginas. No se atribuye al controlador una opción no inspeccionada.

`backend/apps/ventas/ticket.py` crea un `Ticket` congelado desde una venta ya
autorizada por `obtener_venta()`. Contiene líneas, precio histórico, pagos,
identificador, fecha, usuario, total, negocio y leyenda no fiscal. Pillow distribuye
el texto midiendo cada línea con la fuente Vera incluida en ReportLab, incluso
palabras largas y acentos. Para 80 mm usa **576 puntos**, ancho imprimible indicado
por el [manual oficial DT-230](https://www.dascomla.com/toolbox/downloads/DT-230_UG_V1_4-SP.pdf).
Para 58 mm usa 384 puntos conservadores; el ancho efectivo requiere confirmación
del equipo. La altura es el final real de las líneas más el margen inferior; no
hay límite artificial de productos. Una imagen demasiado alta para una sola
página PDF produce un error explícito, sin truncarla.

La vista previa carga esa imagen PNG desde una ruta autorizada, sin paginación del
navegador. El PDF de ReportLab coloca la misma imagen en **una página** con ancho
58/80 mm y altura proporcional. La salida Windows conserva `window.print()` y
solicita el alto de la imagen; algunos controladores pueden imponer sus páginas
fijas. El botón PDF ofrece una alternativa de una sola página, sujeta a lo que
admita el lector y el controlador al imprimir.

ESC/POS es opcional, desactivado por defecto. Un administrador debe elegir una cola
Windows instalada y confirmar que acepta RAW ESC/POS; no se escribe al puerto
USB002. El adaptador envía el raster en bandas `GS v 0` por WinSpool, con 0–8 líneas
finales y corte parcial opcional, apagado por defecto. El resultado HTTP y el log
registran solo la aceptación del spooler, nunca una impresión física confirmada.
Microsoft documenta [StartDocPrinter y WritePrinter](https://learn.microsoft.com/windows/win32/printdocs/startdocprinter)
para trabajos de cola; el manual del fabricante documenta la emulación y el
cortador. No se instaló pywin32 ni se envió un trabajo real.

Rutas nuevas, todas con `vender`: GET `/ventas/<id>/comprobante/imagen/`, GET
`/ventas/<id>/comprobante/pdf/`, POST
`/ventas/<id>/comprobante/imprimir-escpos/`. La configuración sigue protegida por
`gestionar_usuarios`. No hay modelos o migraciones nuevos, ni escritura en ventas,
pagos, inventario o caja.

El verificador `scripts/verificar_ticket_pdf.py` creó cinco conjuntos ficticios
(1, 5, 10, 15 y 30 líneas) con PNG/HTML/PDF en
`%TEMP%/Inventarios_ticket_pdf_856z4hhb`. **Cada PDF tuvo una página** y aumentó de
tamaño según las líneas. La imagen ficticia de una línea se inspeccionó visualmente
en `docs/ticket_ejemplo_1.png`: no hay corte de encabezado, pagos ni leyenda.
En la primera ejecución pasaron **7 pruebas específicas** en SQLite temporal;
posteriormente se agregó una prueba de texto largo y márgenes y pasaron **8**.
La cola DT-230 real y el papel físico permanecen pendientes; la verificación
del paquete PyInstaller figura al final de este documento.

Comandos:

```powershell
.\venv\Scripts\python.exe scripts/verificar_ticket_pdf.py
.\venv\Scripts\python.exe scripts/revisar_navegacion_fase10.py
```

En la demostración temporal, abrir Historial de ventas → Comprobante; comparar
imagen y PDF. En Configuración de tickets, conservar Windows o elegir ESC/POS solo
tras comprobar que la cola/firmware lo aceptan. Para prueba física, seleccionar la
DT-230 y papel 80 mm, imprimir primero el PDF de 1 línea y luego 30; comprobar
corte, escala 100 % y longitud. El envío RAW debe ensayarse con un dispositivo
compatible y consentimiento del operador. Ningún resultado de prueba automatizada
acredita impresión física.

### Verificación final del motor continuo

- `scripts/verificar_ticket_pdf.py`: 1, 5, 10, 15 y 30 productos ficticios; cada
  PDF contiene una página y las imágenes aumentan de alto con el contenido.
  Evidencias: `%TEMP%/Inventarios_ticket_pdf_856z4hhb`. Las imágenes de
  1 y 30 líneas se inspeccionaron visualmente y quedaron en
  `docs/ticket_ejemplo_1.png` y `docs/ticket_ejemplo_30.png`.
- `manage.py test apps.ventas.tests.test_comprobante --noinput`, con SQLite
  temporal: **8 pruebas aprobadas**. Incluyen texto largo, margen blanco, raster
  segmentado, permisos y fallo simulado de la cola.
- `scripts/verificar_fase10.py --pruebas`: `check` y control de migraciones
  correctos; última suite completa: **381 ejecutadas, 380 aprobadas, 1 fallida**.
  La falla es `apps.core.tests.test_qr.QRTests.test_pos_modal_y_confirmacion`:
  espera el texto «Total de la venta: Bs» en el modal QR. No se alteró el cobro QR.
  Registro: `%TEMP%/Inventarios_fase10_gukjxejf/test.txt`.
- `scripts/compilar_fase10.py`: paquete `onedir` reconstruido en
  `%TEMP%/Inventarios_build_fase10_oc6xewvp/dist/SistemaInventarios`.
  `scripts/verificar_fase10.py --paquete` aprobó primer inicio, segundo inicio,
  respaldo y ausencia de SQLite, `.env` y documentos privados dentro del paquete.
  Incluye `apps.ventas.ticket`, `apps.ventas.escpos` y `reportlab/fonts/Vera.ttf`.
- Los cuatro archivos protegidos conservaron sus SHA-256. No hubo impresión real
  ni migraciones en la base del negocio.

**Pendiente de aceptación física:** comparar imagen y PDF de 1 y 30 productos
contra papel real en la DT-230; comprobar alimentación, corte y eventual paginación
del método Windows. La cola RAW no se utilizó con una impresora real. La imagen
continua y el PDF no garantizan que un controlador Windows de página fija avance
solo el papel necesario.

## Corrección de orientación y polaridad ESC/POS (2026-11-15)

**Síntoma confirmado por el usuario:** con un ticket corto, Chrome y WebView2
mostraban una hoja horizontal de aproximadamente 210 × 80 mm. La regla anterior
creaba `@page` en JavaScript con ancho 80 mm y alto cercano a 63 mm; al quedar
el alto por debajo del ancho, el navegador o controlador giraba el formato fijo.
Además, el raster ESC/POS invertía los bits: fondo blanco se enviaba como puntos
negros. Este defecto se detectó antes de enviar trabajos RAW a una impresora real.

`ticket.medidas_pagina()` calcula el alto desde la imagen y exige al menos
`ancho + 1 mm` para la alternativa Windows. La plantilla recibe esa medida del
servidor y deja de crear reglas `@page` en JavaScript. Esto evita solicitar una
hoja horizontal; **no obliga al controlador Windows a aceptar longitud variable**.
La ruta principal de térmicas compatibles es ESC/POS: se invierte correctamente la
polaridad raster (`1` = punto negro), se envía por la cola Windows y se muestra el
resultado del envío sin salir del comprobante. El texto aclara que una aceptación
del spooler no equivale a impresión física. Windows y el PDF siguen disponibles.

Para configurar una térmica: entrar como administrador en **Impresión de tickets**,
elegir `ESC/POS`, el ancho 80 o 58 mm, seleccionar la cola Windows y marcar la
confirmación RAW solo si el modelo y la cola lo aceptan. Guardar. El corte sigue
desactivado por defecto. Si no funciona, volver a `Controlador Windows`. Una marca
o un ancho de papel no garantizan compatibilidad ESC/POS; depende del firmware y
de la cola. Como prueba alternativa en la DT-230, el operador puede crear una cola
Windows adicional con controlador `Generic / Text Only` para el mismo puerto USB
configurado en Windows y seleccionar esa cola; no se crea ni modifica aquí.

**Evidencia automatizada:** `check` produjo `System check identified no issues
(0 silenced).`; `makemigrations --check --dry-run` produjo `No changes detected`.
`manage.py test apps.ventas apps.core.tests.test_qr --noinput` ejecutó **48 pruebas**:
**47 aprobadas y 1 fallida**, la discrepancia conocida del texto del modal QR
(`test_pos_modal_y_confirmacion` espera `Total de la venta: Bs`). Salida completa
guardada íntegra en `docs/evidencias_tickets/check_2026-11-15.txt`,
`docs/evidencias_tickets/migraciones_2026-11-15.txt` y
`docs/evidencias_tickets/pruebas_2026-11-15.txt`.

`scripts/verificar_raster_escpos.py` codificó el ticket ficticio de 30 productos y
lo decodificó con la semántica ESC/POS: 576 × 2971 px, 12 bandas, texto negro sobre
fondo blanco. Imagen: `docs/ticket_escpos_decodificado.png`. No hubo impresión
física, validación del diálogo WebView2 actualizado ni prueba con la cola DT-230.

**Discrepancia preexistente:** la regla general de la especificación pide que toda
configuración viva en `.env`, pero las preferencias de tickets ya se guardan en
`DATA_DIR/impresion.json` para permitir cambios desde la pantalla. Esta corrección
no cambia esa persistencia ni toca `.env`; requiere una decisión aparte si se
quiere reconciliar el contrato general con esa pantalla.
