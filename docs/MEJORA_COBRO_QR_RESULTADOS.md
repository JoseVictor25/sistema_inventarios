# Cobro QR con imagen personalizada

## Diseño y alcance

POS existente: carrito de sesión, HTMX, métodos Efectivo/QR/Transferencia y servicio
transaccional. Se conserva esa arquitectura. No se crean modelos ni migraciones.

La configuración usa `/sistema/qr/` (GET/POST, permiso `gestionar_usuarios`, incluido
Dueño y superusuario activo). Se reutiliza el permiso administrativo existente sin
alterar su matriz. Vendedor no puede modificar. `/sistema/qr/imagen/` sirve PNG
solo a usuarios activos con `vender` o `gestionar_usuarios`, sin caché y con nosniff.
No existe una ruta pública MEDIA ni se admiten nombres/rutas del navegador.

PNG/JPEG/WEBP se decodifican mediante Pillow (dependencia ya disponible, declarada
ahora explícitamente). Límites elegidos: 5 MiB, dimensiones entre 128 y 4096 píxeles
por lado, máximo 8 megapíxeles; se rechazan animaciones, archivos corruptos y bombas
de descompresión. Se normalizan a RGB PNG descartando metadatos.

Archivo único `DATA_DIR/qr_bancario.png`, sustitución atómica mediante provisional
en el mismo directorio y os.replace. No se usan Program Files, static ni recursos
internos. Se rechazan symlinks/junctions y enlaces físicos del archivo. Los archivos
heredan la ACL del directorio de datos de B3; no se cambia ningún permiso Windows.
La política concurrente es último reemplazo terminado; nunca se publica media imagen.

En el POS se identifica QR por el nombre del método existente, sin crear métodos.
Al seleccionarlo se abre un modal Bootstrap local, centrado, con imagen completa
y total de venta leído del carrito. Se aclara que, en pagos mixtos, se transfiere
solo el importe asignado a QR. Cerrar el modal no envía el formulario ni registra
una venta. Si falta imagen se muestra un aviso. Una casilla explícita en el POS
permite declarar recepción del pago: el backend rechaza confirmar un pago QR sin
esa declaración. No existe integración bancaria ni verificación automática.

## Archivos

- `backend/apps/core/qr.py`, `urls.py`, `tests/test_qr.py`.
- `backend/apps/ventas/views.py`: comprobación de confirmación QR antes del servicio.
- `frontend/templates/core/qr.html`, `ventas/partials/_qr_modal.html`.
- `frontend/templates/ventas/pos.html`, `ventas/partials/_carrito.html`.
- `frontend/templates/components/_menu.html`, `frontend/static/js/qr.js`.
- `backend/requirements.txt`, `.gitignore`, este informe.

## Persistencia y límites

- Datos en disco independientes del proceso y de SQLite, compatibles con DATA_DIR
  temporal e instalado. No se crea ni se modifica configuración de B3.
- Los respaldos nuevos incluyen la imagen en su manifiesto verificado. Los anteriores
  siguen siendo recuperables sin QR; en ese caso habrá que volver a cargar la imagen.
- No se incluyeron QR personales en el proyecto o instalador. Exclusiones Git
  para el nombre canónico y provisionales, además de DATA_DIR ya excluido.
- No se reconstruyó ni ejecutó instalador. El próximo paquete PyInstaller deberá
  incorporar el nuevo módulo, plantilla y JS, y verificar Pillow en Windows limpio.
- Pendiente inspección real del modal/selección/cierre en pywebview. Las pruebas
  HTTP y de plantillas no acreditan una inspección gráfica.

## Revisión manual aislada

```powershell
.\venv\Scripts\python.exe scripts/verificar_qr.py --abrir
```

Usar las credenciales ficticias indicadas. Como Dueño, entrar en QR bancario,
cargar una imagen de prueba y consultar/reemplazar/eliminar. Abrir caja si hace
falta, añadir productos en Venta y seleccionar QR. Comprobar total, ausencia de
recorte, cierre sin venta, métodos mixtos y casilla de recepción; confirmar solo
después de marcarla. Repetir sin imagen y como Vendedor (sin acceso a gestión).
No utilizar un QR personal para estas verificaciones.

## Ampliación: respaldo y validación final (2026-11-03)

### Contrato del respaldo

La API SQLite continúa generando una copia consistente. El manifiesto JSON v1 admite
ahora una sección opcional `qr` con PNG codificado en base64, tamaño y SHA-256. Se
comprueba el contenido de la imagen y sus límites antes de publicar. No se aceptan
rutas de destino dentro de ese contenido. El manifiesto se publica al final y la
retención solo elimina pares SQLite/manifiesto verificados; también valida el QR.
La respuesta web/consola no incluye los bytes de la imagen.

Guardar ambos archivos juntos es obligatorio. El manifiesto contiene una imagen
bancaria y debe mantenerse privado igual que SQLite, dentro de las carpetas con ACL
ya configuradas. El hash detecta corrupción, no autentica el origen ni cifra datos.
La imagen normalizada puede ocupar más que el archivo subido: se limita a 32 MiB y
el manifiesto a 48 MiB; sigue aplicándose el límite de 8 megapíxeles. No hay nuevas
dependencias, modelos ni migraciones.

Los llamadores web, consola, launcher `--respaldo` y mantenimiento pasan el archivo
canónico del directorio persistente. No se alteran SID ni ACL. El reemplazo atómico
del QR permite leer una versión completa; SQLite y la imagen son configuraciones
independientes, no una transacción conjunta. Si se cambia el QR mientras se respalda,
se incluye la versión completa leída en ese instante. Un QR corrupto hace fallar la
copia, conservando los respaldos anteriores. La ausencia del QR es válida.

`recuperar_temporal()` exige un directorio nuevo bajo TEMP y rechaza enlaces,
junctions, destinos existentes y manifiestos inválidos. Comprueba SQLite, claves
foráneas, tablas esenciales, hash y QR antes/durante la recuperación. Ante un error
retira solo los archivos que acaba de crear. No existe ruta web de restauración ni
se reemplaza ninguna instalación. El verificador de fase 9 reutiliza esta función.

### Archivos de esta ampliación

- `backend/apps/core/respaldos.py`, `services.py`.
- `desktop/launcher.py`, `desktop/mantenimiento.py`: inclusión del QR canónico.
- `scripts/respaldo.py`, `scripts/verificar_fase9.py`.
- Nuevo `backend/apps/core/tests/test_respaldos_qr.py`.
- `frontend/static/js/qr.js`: sincronización del total tras sustituciones HTMX.
- `frontend/templates/ventas/partials/_qr_modal.html`: área de imagen del ancho
  disponible y 55vh de alto, con `object-fit: contain`, sin recortar. Una imagen de
  baja resolución puede perder nitidez al ampliarse; no se inventan píxeles del QR.
- Nuevo `scripts/verificar_qr.py` y este documento.

### Evidencias y límites

- Regresión final: **373 pruebas aprobadas en 219,137 s**, Django `check` correcto
  y `makemigrations --check --dry-run` sin cambios. Evidencias:
  `%TEMP%/Inventarios_fase10_kqyiuzbk`. La ejecución previa de 388 incluía pruebas
  heredadas/importadas duplicadas; se eliminó esa duplicación y se repitió la suite.
- 14 pruebas específicas QR y respaldo aprobadas en 1,630 s, carpeta
  `%TEMP%/Inventarios_QR_final_s5lo05mv`.
- Verificación HTTP y recuperación de QR aprobadas, carpeta
  `%TEMP%/Inventarios_QR_visual_ipxh0yza`: total de carrito 8 y 16 Bs; POST sin
  confirmación rechazado con 422; Vendedor sin acceso a configuración (403) y con
  acceso a imagen (200). Ventas, cajas, movimientos de caja y lotes intactos.
- JS servido por Waitress/WhiteNoise con DEBUG=False e idéntico al código fuente.
- Recuperación de respaldo anterior sin QR: 33 tablas comparadas íntegramente,
  `%TEMP%/Inventarios_verificacion_fase9_82aqg1_m`.
- Intento real de WebView2: `Main window failed to start`, evidencia
  `%TEMP%/Inventarios_QR_visual_y0h8bql6/resultado.json`. No se obtuvieron capturas ni
  se verificaron visualmente nitidez, tamaño, centrado, recorte o clic de cierre.
  Las comprobaciones DOM previstas tampoco llegaron a ejecutarse.
- No se reconstruyó PyInstaller. Su spec recopila los módulos de apps, plantillas
  y JS; Pillow ya está declarado. La ejecución del paquete actualizado queda pendiente.
- Los cuatro hashes protegidos coinciden con los registrados en la implementación
  inicial (también comprobados al final de la regresión y del recorrido HTTP).
  `git diff --check` no detecta errores de espacios; Git advierte conversión LF/CRLF.
  Rama `main`, cambios locales preservados, informes privados sin seguimiento.
  No se ejecutaron instaladores, B4, migraciones reales, commit ni push.

Comandos reproducibles, siempre con datos ficticios y una instalación TEMP nueva:

```powershell
.\venv\Scripts\python.exe scripts/verificar_qr.py --http
.\venv\Scripts\python.exe scripts/verificar_qr.py
.\venv\Scripts\python.exe scripts/verificar_qr.py --abrir
```

El primer comando verifica HTTP y respaldo/recuperación sin ventana. El segundo
intenta interacciones automáticas públicas de pywebview a 1280, 768 y 390 px; no
sustituye la inspección humana. El tercero muestra credenciales temporales y permite
la revisión manual, con una imagen geométrica marcada como prueba, nunca un QR
bancario válido. Revisar carrito vacío y con productos, cambio de cantidades y
métodos, cierre del modal y confirmación manual. La revisión visual permanece abierta.

## Resultados de la implementación inicial (anteriores a esta ampliación)

- `verificar_fase10.py --pruebas`: Django check correcto, sin cambios de modelos
  pendientes y suite completa de **364 pruebas aprobadas en 217,445 segundos**.
  Evidencia: `%TEMP%/Inventarios_fase10_vmw0_mxn`. La suite descubrió las primeras
  cinco pruebas QR; las dos adicionales se verificaron después en ejecución específica.
- Ejecución final de `apps.core.tests.test_qr`: **7 pruebas aprobadas** en
  0,929 segundos. Evidencia: `%TEMP%/Inventarios_QR_final_kf905ssn/test.txt`.
  Incluye formatos, contenido/dimensiones/tamaño inválidos, permisos, carga,
  reemplazo, eliminación, persistencia del archivo leída por otro proceso,
  plantilla del modal, ausencia de venta al consultar POS, confirmación backend y CSRF.
- HTTP del JS `/static/js/qr.js` con DEBUG=False: 200, bytes idénticos a fuente.
- No hay migraciones nuevas, cambios de esquema ni operaciones sobre datos reales.
- SHA-256 de los cuatro archivos protegidos idéntico al inicio y al final:
  SQLite `40D61B7947251655E3AF6055FAB58130D29A24586B103AA62FF4D5B847E37F50`;
  .env `9BC65E53962E9CD7849EB41F2899DFA29D230DF7DCB217831793CA76BE8FC854`;
  REPORTE_MIGRACIONES_FASE1.md `B5239FC7F134851BF32225F7363604D500449538690C2658A101105C7C257E53`;
  SOLUCION_ERROR_TERMINAL.md `8D907AD4BD5AB07E2F3799033A21E83C9A77AA7095E4C6CF520709D5E1EFAE26`.
- Sin commit, push, ejecución de instaladores ni comienzo de B4.

---

## Corrección del importe QR en pagos mixtos (2026-11-03)

### Problema identificado

La función `actualizarTotal()` en `qr.js` leía `#monto-total-val` (el total global de la venta)
y lo mostraba en el modal como si fuera el importe QR. En pagos mixtos, esto era incorrecto.
El texto del modal decía «Total de la venta» en lugar de «Importe a pagar por QR».

### Corrección implementada

**`frontend/static/js/qr.js`:**
- Nueva función `calcularMontoQR()`: itera solo las filas DOM con `data-es-qr="1"` y
  suma sus importes. Devuelve `null` si no hay filas QR con importe > 0. Nunca lee el total global.
- Nueva función `actualizarImporteQR()`: muestra el importe QR calculado o `—` si es inválido.
- `abrir()` revisada: no abre el modal si el importe QR es nulo, cero o inválido.
- Evento `change` en `.select-metodo`: si el modal ya está abierto, actualiza solo el importe
  (sin recargar la imagen bancaria).
- Evento `input` en `#lista-pagos`: actualiza el importe del modal en tiempo real cuando está visible.

**`frontend/templates/ventas/partials/_qr_modal.html`:**
- Texto «Total de la venta» → «Importe a pagar por QR».
- Nota: «transfiere únicamente el importe indicado arriba, no el total de la venta».

### Pruebas — 34 de 34 aprobadas (100% OK)

`scripts/tests/test_cobro_qr_b3.py`

| Caso | Pruebas | Resultado |
|---|---|---|
| A — QR único Bs 100 | 3 | ✅ OK |
| B — Efectivo Bs 60 + QR Bs 40 | 3 | ✅ OK |
| C — Cambio de Bs 40 a Bs 25 | 3 | ✅ OK |
| D — Varias filas, una sola QR | 2 | ✅ OK |
| E — Importe QR = 0 (modal no se abre) | 2 | ✅ OK |
| F — Campo QR vacío (modal no se abre) | 3 | ✅ OK |
| G — Sin fila QR (modal no se abre) | 2 | ✅ OK |
| H — Cierre sin confirmar | 2 | ✅ OK |
| I — Múltiples filas QR suman correctamente | 2 | ✅ OK |
| Verificación del template HTML | 4 | ✅ OK |
| Verificación del JS | 8 | ✅ OK |
| **TOTAL** | **34** | **✅ 34 OK (0.045 s)** |

### Archivos protegidos verificados

| Archivo | Hash SHA-256 | Estado |
|---|---|---|
| `backend/datos/db.sqlite3` | `40D61B7947251655E3AF6055FAB58130D29A24586B103AA62FF4D5B847E37F50` | ✅ INTACTO |
| `backend/.env` | `9BC65E53962E9CD7849EB41F2899DFA29D230DF7DCB217831793CA76BE8FC854` | ✅ INTACTO |
| `backend/REPORTE_MIGRACIONES_FASE1.md` | `B5239FC7F134851BF32225F7363604D500449538690C2658A101105C7C257E53` | ✅ INTACTO |
| `backend/SOLUCION_ERROR_TERMINAL.md` | `8D907AD4BD5AB07E2F3799033A21E83C9A77AA7095E4C6CF520709D5E1EFAE26` | ✅ INTACTO |

Sin commit, push, instaladores, B4, ni migraciones reales.
