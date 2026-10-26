# Fase 8 — Reportes y exportación

Base de trabajo: `main`, commit `1326d79`. Implementación autorizada de ocho
reportes y Excel/PDF. No incluye auditoría general, respaldos ni panel de fase 9.

## Estado

Implementación y verificaciones automatizadas aprobadas; pendiente de revisión
visual del usuario antes de cerrar la fase. Las comprobaciones y resultados se
registran abajo. No se acredita inspección visual por haber obtenido respuestas
HTTP o generado documentos.

## Reportes, filtros y permisos

Todos los nombres pertenecen al espacio `reportes`. Cada pantalla está en
`/reportes/<nombre>/`; cada descarga en `/reportes/<nombre>/exportar/`, nombre
`<nombre>_exportar`, con `formato=xlsx|pdf` y los mismos filtros.
El menú es `/reportes/`, nombre `inicio`.

| Nombre | Reporte y filtros | Permisos |
|---|---|---|
| ventas | Desde, hasta, agrupar día/semana/mes | ver_reportes |
| ventas_metodo_pago | Desde, hasta | ver_reportes |
| productos_mas_vendidos | Desde, hasta, categoría exacta opcional | ver_reportes |
| compras | Desde, hasta, proveedor opcional | ver_reportes + ver_costos |
| inventario_valorizado | Categoría exacta opcional | ver_reportes + ver_costos |
| ganancias | Desde, hasta, categoría exacta opcional | ver_reportes + ver_costos |
| vencimientos | Días no negativos; predeterminado de settings | ver_stock |
| cierres_caja | Desde, hasta, propietario del turno opcional | ver_historial_caja |

Se validan filtros en servicios y formularios; permisos en vistas, servicios y
exportadores. El menú solo ofrece reportes accesibles. Los anónimos van al login;
sin permiso se responde 403; filtros inválidos 422. POST no está permitido en
consultas; CSRF permanece activo. El Vendedor consulta y exporta únicamente
vencimientos. No se cambia la matriz inicial de roles.

## Fórmulas y decisiones aprobadas

- Ventas: sumar cada Venta.total una vez y contar cabeceras. TruncDate/TruncWeek/
  TruncMonth sobre America/La_Paz, con lunes como inicio de semana.
- Pagos: sumar Pago.monto, nunca Venta.total a través del join. Cantidad es
  ventas distintas por método; se indica además el número global de ventas únicas.
  El total de conteos por método puede ser mayor por pagos mixtos.
- Productos vendidos: sumar unidades_totales y subtotal guardados en DetalleVenta.
  No recalcular con el precio o equivalencia actuales de la presentación.
- Compras: fecha, proveedor y Compra.total históricos.
- Inventario: stock físico = Σ cantidad_actual; valor = Σ cantidad_actual ×
  costo_unitario de cada lote. Promedio = valor/stock, redondeado con ROUND_HALF_UP
  solo para mostrar dos decimales. Nunca se calcula valor a partir del promedio
  redondeado. Stock cero no tiene promedio: «—» en HTML/PDF, celda vacía en Excel.
  Incluye vencidos y productos inactivos con existencias identificados.
- Ganancias: Σ subtotales de venta − Σ cantidades de DetalleVentaLote × costo
  histórico del lote. Ingresos y salidas se consultan por separado; una línea
  abastecida desde varios lotes no duplica ingresos. Es ganancia bruta de
  mercadería, no utilidad neta: no deduce gastos generales ni movimientos de caja.
- Vencimientos: stock positivo y fecha entre hoy y hoy+días inclusivos. Excluye
  sin fecha, agotados y ya vencidos; estos últimos siguen en las alertas existentes.
- Cierres: fecha_cierre y usuario propietario, no quien ejecutó el cierre ajeno.
  Prefiere resumen auditable versión 1 del cierre; si falta o es inválido, calcula
  inicial + pagos efectivos + ingresos − egresos y contado − esperado, identificando
  cada turno recalculado. Un cierre sin contado genera error controlado.
- Intervalos: máximo 366 fechas calendario incluidas. DateTimeField usa comienzo
  local inclusivo y comienzo del día siguiente al final exclusivo. Categorías
  exactas, no descendientes implícitos. Entidades inactivas consultables.

## Arquitectura y precisión

`consultar_reporte(usuario, nombre, filtros)` entrega columnas tipadas, filas,
totales, filtros normalizados, notas y gráfico. Los adaptadores de §8.6 conservan
sus nombres e incorporan actor obligatorio. HTML, Excel y PDF consumen el mismo
resultado; no existen cálculos independientes en plantillas o exportadores.

Se proyectan columnas mínimas mediante ORM e iterator; acumulación con Decimal
para evitar SUM monetario de SQLite con aritmética flotante. No se hace una
consulta de stock por producto ni una consulta por cierre. Se materializan las
lecturas relacionadas en una transacción breve y se genera el documento después.

Excel se genera con openpyxl en BytesIO: encabezados y totales en negrita,
anchos ajustados, importes numéricos con dos decimales y hoja Información.
Textos forzados como cadenas para impedir fórmulas inyectadas. PDF se genera con
ReportLab en BytesIO: negocio, título, filtros, moneda, notas, tabla con encabezados
repetidos, totales y numeración de páginas. Texto escapado antes de Paragraph.
Los documentos no se guardan permanentemente en el servidor.

Las pantallas heredan AdminLTE/Bootstrap existentes, con tablas desplazables,
filtros responsivos, mensajes vacíos y botones de descarga. Chart.js usa el recurso
local y json_script; los números del gráfico representan los resultados del
servidor, no realizan cálculos monetarios de negocio.

## Archivos

Modificados:

- `backend/apps/reportes/services.py`, `views.py`, `urls.py`.
- `frontend/templates/components/_menu.html`.
- `ESPECIFICACION_SISTEMA.md` y `docs/ESPECIFICACION_SISTEMA.md`.

Nuevos:

- `backend/apps/reportes/forms.py`, `exportadores.py`.
- `backend/apps/reportes/tests/datos.py`, `test_servicios.py`,
  `test_pantallas_exportacion.py`.
- `frontend/templates/reportes/inicio.html`, `_reporte.html`, `ventas.html`,
  `ventas_metodo_pago.html`, `productos_mas_vendidos.html`, `compras.html`,
  `inventario_valorizado.html`, `ganancias.html`, `vencimientos.html`,
  `cierres_caja.html`.
- `frontend/static/js/reportes.js`.
- `scripts/verificar_reportes_fase8.py` y este informe.

No se modifican modelos, migraciones, servicios de fases anteriores, matriz de
permisos ni dependencias. Las especificaciones aclaran la autorización posterior
de idempotencia de fase 7 y el cierre de fases 5–7 confirmado por el usuario;
no se reescriben los informes históricos ni los documentos privados locales.

## Verificación ejecutada

Primera ejecución específica: **35 pruebas de reportes en 10,777 segundos, OK**,
con `venv/Scripts/python.exe` y SQLite temporal. Evidencia:
`C:\Users\Jose\AppData\Local\Temp\Inventarios_fase8_desarrollo_ua0cy8bk\test.txt`.

Incluye los ocho reportes, Decimal, ganancias históricas, varias salidas por venta,
pagos mixtos, modificación de equivalencia/precio actual, vencimientos, fechas y
366 días, categorías exactas, filtros inválidos, períodos vacíos, cierres con y sin
instantánea, consultas constantes al aumentar filas, permisos en tres capas,
CSRF/métodos HTTP, HTML, documentos vacíos, Excel consistente y PDF con tablas
largas de 300 filas. Las comprobaciones PDF validan bytes PDF y las filas/totales
entregados a la tabla real de ReportLab; no equivalen a una inspección visual.

Verificación completa ejecutada con el script de fase 8:

| Comprobación | Resultado real |
|---|---|
| `manage.py check` | Código 0, sin incidencias |
| `makemigrations --check --dry-run` | Código 0, No changes detected |
| Suite completa | **319 pruebas en 210,119 s; OK, cero fallidas** |
| Regresiones | 284 pruebas anteriores incluidas en la suite |
| Pruebas nuevas de reportes | 35, también ejecutadas separadamente |
| Integridad de recursos locales | Código 0 |
| HTTP aislado final | **68 solicitudes; ocho reportes y dieciséis exportaciones comprobados** |
| HTTP 404 / 500 | Ninguno |
| Archivos protegidos | Hashes iguales antes/después de ambas ejecuciones |
| Migraciones nuevas | Ninguna; modelos sin cambios |

La primera ejecución combinada completó check, dry-run, 319 pruebas y frontend,
pero el recorrido HTTP se interrumpió por una llamada incorrecta del verificador
a `TokenCSRF`. Se corrigió pasando el HTML al constructor y se ejecutó nuevamente
`--http`, aprobado. No fue un fallo de una pantalla ni de una exportación.
Los 403 y 422 del recorrido final son rechazos deliberados de permisos y filtros.

Evidencias reales:

- Suite y comprobaciones:
  `C:\Users\Jose\AppData\Local\Temp\Inventarios_verificacion_fase8_rnogln1v`
  (`check.txt`, `makemigrations.txt`, `test.txt`, `frontend.txt`, `resultados.json`).
- HTTP final aprobado:
  `C:\Users\Jose\AppData\Local\Temp\Inventarios_verificacion_fase8_82lw8va_`
  (`http.json`, `resultados.json`, ocho HTML y SQLite temporal).

El script conserva los tamaños y SHA-256 de las dieciséis descargas en http.json;
los documentos descargados no se almacenan permanentemente.

## Reproducción aislada

Desde la raíz del proyecto en PowerShell:

```powershell
& .\venv\Scripts\python.exe scripts/verificar_reportes_fase8.py --pruebas --http
& .\venv\Scripts\python.exe scripts/verificar_reportes_fase8.py --abrir
```

El script crea una carpeta única en TEMP, configura ENV_FILE inexistente, DB_PATH,
TEST.NAME, logs y respaldos temporales antes de cargar Django. Comprueba la ruta
exacta antes de migrar. Aplica las migraciones pendientes solo allí y genera datos
ficticios mediante los servicios de Compra/Venta/Caja. Registra check, dry-run,
suite, frontend, HTTP y hashes de los cuatro archivos protegidos, sin imprimir
secretos. No usa datos reales. Las exportaciones HTTP se verifican en memoria;
solo se conservan sus tamaños y hashes como evidencia.

`--abrir` verifica primero HTTP y luego abre el navegador y conserva el servidor
local hasta Ctrl+C. Muestra URL, contraseña aleatoria temporal y rango de fechas
de demostración. Usuarios: `dueno_fase8` y `vendedor_fase8`.

Revisión manual pendiente, en escritorio 1280×800 y móvil 390×844:

1. Ingresar como Dueño y recorrer las ocho tarjetas del menú Reportes.
2. Para reportes por período, seleccionar desde/hasta mostrados en la consola;
   probar día, semana y mes en Ventas. Comprobar gráfico, tabla y totales.
3. Datos ficticios esperados: ventas 38,00; efectivo 28,00 y QR 10,00; 7 unidades
   vendidas; compra 50,00; inventario restante 8 unidades y valor 32,00; costo
   vendido 18,00 y ganancia bruta 20,00; cierre esperado 81,00, contado 80,00,
   diferencia −1,00. Vencimientos incluye el lote restante de 8 unidades.
4. Descargar ambos formatos de cada reporte; abrirlos y comprobar rótulos,
   importes, filtros, totales, caracteres acentuados y diseño de páginas.
5. Cambiar filtros; probar rango vacío, fechas invertidas y más de 366 días.
6. Entrar como Vendedor: solo Vencimientos en Reportes; intentar directamente
   `/reportes/ganancias/` y su exportación debe responder 403.
7. Comprobar menú móvil, etiquetas, botones y desplazamiento de tablas. Revisar
   consola/Network sin 404/500 ni recursos externos. Desconectar Internet
   manteniendo localhost disponible; repetir consultas y descargas.

## Limitaciones y pendientes

- La inspección visual de navegador y documentos queda pendiente del usuario.
- Cada descarga vuelve a consultar los datos. Con operaciones entre peticiones,
  el resultado puede cambiar; no existe congelación persistente de reportes.
- Los rótulos y categorías usan el catálogo actual; el esquema no guarda su
  denominación histórica. Los importes, unidades y costos provienen del historial.
- Sin recortes de filas. La memoria crece con el resultado y el documento; la
  prueba de tabla larga usa 300 filas, no constituye una prueba de carga ilimitada.
- Las celdas numéricas Excel están sujetas a la precisión propia de Excel; los
  cálculos de negocio se realizan previamente con Decimal, no en Excel.
- No se aplicaron migraciones a la base real. Las migraciones pendientes de
  Caja, Ventas e Inventario requieren un procedimiento autorizado independiente.
- No se realiza commit, push, tag, cambio de rama ni staging. Los dos reportes
  locales de fase 1 deben permanecer sin seguimiento.
