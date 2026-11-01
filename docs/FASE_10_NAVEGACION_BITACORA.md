# Navegación y bitácora — revisión del 28/10/2026

Estado: implementación para revisión, sin cierre visual aprobado por el usuario.

## Diagnóstico

El menú anterior usaba `navbar-expand-md` (expansión desde 768 px), una lista
con `flex-wrap` y todos los módulos al mismo nivel. Esa combinación permitía
varias filas. La marca tenía `text-truncate`, `min-w-0` y `max-width:50vw`, que
explican el recorte con puntos suspensivos. Medir solo scrollWidth no detecta
estos problemas: una lista puede envolver sin desbordarse.

No se recibieron imágenes adjuntas en este turno. No había un proceso
SistemaInventarios activo identificable durante la consulta; no puede atribuirse
la captura del usuario a un ejecutable concreto. Un paquete previo conserva sus
recursos antiguos aunque cambie el código fuente. El launcher fuente ya recolecta
estáticos en TEMP; se conserva ese cambio anterior.

## Cambios

- Una sola lista de enlaces y condiciones de permisos en `_menu.html`.
- En ancho suficiente (desde 1280 px), Inicio/Venta/Caja/Inventario y desplegable
  Más módulos; los mismos nodos se reubican, no se duplican reglas de permisos.
- Si la marca y los enlaces no caben, vuelve al panel colapsado. Por debajo de
  1280 px, panel vertical desplazable. Marca completa, usuario y logout visibles.
- Sin reducción exagerada de fuente, elipsis ni overflow-x oculto.
- Bootstrap Collapse/Dropdown, estado activo por URL y cierre con Escape.
- Bitácora en tabla: fecha, hora, responsable, acción legible, entidad/ID y detalle.
- Modal Bootstrap de solo lectura con desplazamiento interno; comparación de
  valores anteriores/nuevos, campos modificados, estructuras anidadas y nulos.
- Precio de venta: `Bs 50,00` → `Bs 60,00`. Acciones desconocidas conservan su
  identificación convertida a texto legible. Campos de credenciales omitidos.
- Valores escapados por Django; no se insertan datos de auditoría mediante innerHTML.
- Se conserva `registrar_cambio()` sin cambios, además de filtros, permisos,
  paginación y orden. Sin modelos ni migraciones.
- CSS/JS propios con versión SHA-256 del recurso servido para invalidar caché.

## Archivos de esta corrección

`frontend/templates/base.html`, `components/_menu.html`, `auditoria/lista.html`,
`frontend/static/css/app.css`, `js/app.js`, `core/context_processors.py`,
`auditoria/services.py`, nuevo `auditoria/presentacion.py`, pruebas
`core/tests/test_presentacion_auditoria.py`, script de revisión
`scripts/revisar_navegacion_fase10.py` y ampliación de anchos del verificador gráfico.
Se preservan los demás cambios de Bloque A y correcciones previas sin seguimiento.

## Evidencia y límites

Primera suite: 354 pruebas aprobadas en 207,838 s. Check y detección de migraciones
sin incidencias; HTTP de reportes y auditoría/respaldos aprobado (36 solicitudes
en este último recorrido), y launcher/Waitress en dos ejecuciones aprobado.
Evidencia: `Inventarios_fase10_ne7yyn8s` en TEMP.

Suite final con pruebas del formateador: **356 aprobadas en 212,282 s**, check
sin incidencias y sin migraciones no previstas. Evidencia:
`Inventarios_fase10_ce4a7bfv` en TEMP. Incluye permisos y escape HTML existente.

Se intentó pywebview con 1920, 1366, 1280, 1024, 768 y 390 px. Falló la espera del
documento en el primer ancho, 1920 px, en `/login/`. No se pudo inspeccionar JS,
abrir menús ni modales en el motor gráfico. Resultado real: automatización gráfica
**no aprobada**; evidencia `Inventarios_visual_nav_3oeryind/resultado.json` en TEMP.
No se atribuye el timeout a una causa específica no demostrada.

Integridad de bibliotecas locales correcta. Comparación adicional en WhiteNoise
con DEBUG=False: CSS/JS HTTP idénticos byte por byte a las fuentes actuales.

Reconstrucción final limpia: `Inventarios_build_fase10_rfqwokpg/dist/SistemaInventarios`
en TEMP. CSS/JS coinciden byte por byte entre fuente, frontend empaquetado y
staticfiles empaquetado. SHA-256 final CSS:
`f48d06446188ebeb96114992e6fa2c0e657537fc5af07ec90001246a27ff4e3c`;
JS: `1c0f99e816fe570db6a1952e07ecd16d8e221bace9f2838c34ebbd6fa81d271d`.
Esto evita entregar un paquete con las primeras versiones intermedias del menú.
La verificación del ejecutable se registra en `Inventarios_fase10_vsuq1iud`.

## Revisión humana necesaria

```powershell
.\venv\Scripts\python.exe scripts/revisar_navegacion_fase10.py
```

Crea instalación ficticia nueva, datos de compras/ventas/cierre y cambios de precio
50→60; imprime usuarios Dueño/Vendedor y contraseña temporal. Usa el launcher con
pywebview. No conecta a la base original. Si abre navegador alternativo, indicarlo
en la revisión: no cuenta como prueba de WebView2.

Revisar a 390, 768, 1024, 1280, 1366 y 1920 px: marca completa, fila amplia única,
abrir/cerrar hamburguesa, desplegable, navegación por Tab/Escape, logout y permisos
del Vendedor. En Bitácora abrir/cerrar detalles con botón, Escape y teclado;
comprobar precios, textos largos, filtros y paginación. No basta medir scrollWidth.

No se modificaron datos reales, `.env`, los dos reportes privados ni reglas de
negocio. No hay commit, push, tareas programadas ni instalación del Bloque B.
Los cuatro hashes protegidos coinciden con los registrados antes de estas correcciones.
# Actualización de estado — 01/11/2026

El usuario aprobó visualmente la interfaz definitiva y el ajuste final del POS.
La referencia y navegación horizontal históricas de este informe fueron
sustituidas por `FASE_10_REFERENCIA_VISUAL.md`. Consultar el cierre técnico en
`FASE_10_RESULTADOS.md`; los intentos gráficos fallidos se conservan como evidencia
histórica y no se presentan como pruebas aprobadas.

