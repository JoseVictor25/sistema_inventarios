# Fase 7 — Inventario y alertas

Fecha: 2026-10-25. Rama de trabajo: `main`, base `23bcd1f`.

**Estado: implementación funcional y verificaciones automatizadas aprobadas. Fase no cerrada: requiere
inspección visual del usuario y decisión sobre idempotencia persistente.**

## Funcionalidades y contratos implementados

- Cinco rutas exactas de §9.5: stock, lotes, alertas, ajuste/merma y movimientos.
- Fuente única de stock: `Lote.cantidad_actual`. La consulta agrega lotes mediante
  SUM/COALESCE y entrega proyecciones; no consulta stock individual por fila.
- Stock físico incluye vencidos. Disponible suma lotes sin fecha o con fecha
  desde hoy. No implica que un producto o presentación inactivos puedan venderse.
- Stock bajo: físico <= mínimo, incluido cero. Activos sin lotes aparecen con cero.
  Productos inactivos con existencias se muestran e identifican. Los inactivos
  sin existencias no aparecen en la lista general ni en stock bajo, pero sus lotes
  y movimientos históricos permanecen consultables.
- Por vencer: stock > 0, desde hoy hasta hoy + DIAS_ALERTA_VENCIMIENTO, inclusivo.
  Vencidos: stock > 0 y fecha anterior a hoy. Agotados y fechas nulas no generan
  alerta de vencimiento. Se usa `timezone.localdate()`; no se modifica `.env`.
- Paginación de 20 filas. Alertas tiene tres paginaciones independientes, sin
  ocultar registros tras un límite fijo. Orden estable con PK como desempate.
- Filtros validados: stock (`q`, `solo_bajo`, `page`); lotes (`q`, `producto`,
  `estado`, `page`); movimientos (`q`, `producto`, `lote`, `tipo`, `desde`, `hasta`,
  `page`). Alertas admite `page_bajo`, `page_por_vencer`, `page_vencidos`.
  Campos inesperados, fechas y opciones inválidas se rechazan con 422.
- `ajustar_inventario(usuario, lote, tipo, cantidad, motivo)`: AJUSTE firmado,
  MERMA negativa; entero estricto no cero, motivo limpio 5–200 caracteres,
  resultado entre cero y cantidad inicial. Relee el lote y actualiza mediante
  condición sobre la cantidad anterior. No cambia costos ni cantidades iniciales.
- Lote, MovimientoInventario y LogAuditoria se guardan atómicamente. Auditoría
  `AJUSTE_INVENTARIO` registra anterior/nuevo, producto, movimiento, tipo, delta y
  motivo; el usuario y fecha quedan en LogAuditoria. Nunca se editan movimientos
  previos. El servicio de auditoría existente se reutiliza.
- Formulario con CSRF, POST/Redirect/GET y mensaje de resultado. La pérdida de una
  respuesta exige revisar historial antes de repetir: PRG no garantiza idempotencia.
- Cinco pantallas Bootstrap/AdminLTE con recursos locales, navegación por permisos,
  tablas desplazables, formularios adaptables y mensajes en español. No se añade
  un contrato HTMX nuevo: las peticiones HX y Accept JSON mantienen autorización
  y retornan HTML sin costos no autorizados; no se ofrece una API JSON.

## Permisos y protección de costos

- `ver_stock`: existencias, lotes, alertas y movimientos operativos (no bitácora).
- `ajustar_inventario`: formulario y servicio de ajustes/mermas.
- `ver_costos`: proyección de costo unitario exclusivamente para quien lo posee.
  Las filas de consultas son diccionarios; no se entregan modelos con relaciones
  o campos diferidos que permitan cargar un costo accidentalmente desde HTML.
- Permisos en servicios y vistas, sin conceder nuevos permisos al Vendedor.
  Usuarios anónimos se redirigen al login; sin permiso reciben 403. Servicios
  rechazan anónimos, inactivos y usuarios sin rol; superusuario activo permitido.
- Se confirmó una exposición en Admin: los permisos técnicos de consulta bastaban
  para ver costos de Lote, Compra y DetalleCompra. Ahora sus administradores y el
  inline financiero exigen además `ver_costos`. Quien no lo posee recibe 403 en
  estos registros financieros, incluidos enlaces directos y filtros manipulados.
  Sigue pudiendo consultar inventario ordinario con `ver_stock`.
- No se alteran grupos, permisos técnicos, roles, privilegios ni datos de usuarios.
  Tener `ver_costos` no reemplaza el permiso técnico de Django Admin.
- No se ha cambiado el POS, FEFO, reglas de Compras ni los servicios de Caja/Ventas.
  El único cambio fuera de Inventario es la protección administrativa indicada y
  su mixin compartido, además del menú y documentación.

## Concurrencia actual y sus límites

El ajuste usa una transacción y un UPDATE condicionado por PK/cantidad anterior,
con expresión F para el delta y comprobación de límite inicial. Si otra escritura
cambia la fila o SQLite no puede promover el bloqueo, se revierte y devuelve un
ErrorDeNegocio. No se presupone bloqueo por fila de `select_for_update()`.

Las pruebas usan conexiones independientes y comprueban carreras merma/merma,
ajuste/ajuste y merma/venta FEFO, sin stock negativo, pérdida de actualizaciones
ni movimiento/bitácora parciales. Los conflictos pueden requerir recargar; no se
reintenta automáticamente una escritura de resultado incierto.

## Implementación autorizada: Idempotencia persistente con OperacionAjusteInventario

Conforme a la autorización expresa, se implementó el modelo `OperacionAjusteInventario` y su migración `0003_operacion_ajuste_inventario.py` (probada y aplicada exclusivamente en bases temporales):

| Campo | Finalidad |
|---|---|
| id | PK automática |
| clave | UUID único global de solicitud |
| usuario | Actor autenticado, FK PROTECT |
| lote | Lote objetivo explícito, FK PROTECT |
| tipo | AJUSTE o MERMA, con CHECK (`operacion_ajuste_tipo_valido`) |
| huella | SHA-256 canónico de usuario, lote, tipo, cantidad entera y motivo limpio |
| movimiento | Referencia al resultado inmutable, PROTECT |
| auditoria | Referencia al LogAuditoria del resultado, PROTECT |
| creado_en | Fecha/hora de creación automática |

Índice compuesto `[usuario, -creado_en]` y restricción única sobre `clave`. Registrado en Admin bajo `SoloLecturaAdminMixin` (sin permisos de alta, cambio ni eliminación).

### Flujo transaccional y protección de concurrencia:

1. **Normalización y huella canónica:** El actor se fija desde la sesión autenticada; se normaliza la cantidad (entero con signo distinto de cero), el tipo y el motivo limpio (5 a 200 caracteres). Se calcula la huella SHA-256 canónica sobre el JSON ordenado de `(usuario_id, lote_id, tipo, cantidad, motivo)`.
2. **Consulta previa idempotente:** Si la clave ya existe y tiene movimiento confirmado:
   - Misma solicitud (mismo usuario y huella): retorna el `MovimientoInventario` anterior sin re-ejecutar CAS, sin modificar existencias y sin crear bitácoras adicionales.
   - Solicitud alterada (distinto usuario o datos diferentes): se rechaza con `ErrorDeNegocio`.
3. **Reserva y confirmación atómica unificada:**
   - En una única transacción (`transaction.atomic()`), se reserva primero la `OperacionAjusteInventario`. Si ocurre carrera entre conexiones sobre la misma clave, se captura `IntegrityError` y se recupera la operación ganadora.
   - Se actualiza el lote mediante CAS (`filter(pk=actual.pk, cantidad_actual=anterior, cantidad_inicial__gte=nueva).update(...)`).
   - Se crea el `MovimientoInventario` y se registra el `LogAuditoria`.
   - Se enlazan el movimiento y la auditoría a la `OperacionAjusteInventario` y se confirman todos juntos.
   - Cualquier error o excepción revierte la transacción completa (rollback total: ni lote, ni movimiento, ni auditoría, ni clave reservada persisten).
4. **Claves diferentes:** Permiten operaciones legítimas independientes y consecutivas conforme al stock disponible.
5. **Integración UX y Formulario:**
   - `AjusteInventarioForm` incorpora el campo oculto `clave` (`UUIDField` con `initial=uuid4`).
   - Si la validación falla o se reintenta, el formulario conserva la misma clave.
   - Al completar la operación con éxito y redirigir, una nueva carga emite un nuevo UUID.
   - El formulario incluye protección JavaScript inmediata ante doble clic (`pointer-events: none`, clase `disabled` y texto de carga).

## Archivos

Modificados:

- `backend/apps/inventario/services.py`, `views.py`, `urls.py`, `admin.py`.
- `backend/apps/core/admin.py` (mixin de consulta financiera).
- `backend/apps/compras/admin.py` (solo protección de costos en Admin).
- `frontend/templates/components/_menu.html`.
- Ambas copias de `ESPECIFICACION_SISTEMA.md` (precisiones de §9.5).

Nuevos:

- `backend/apps/inventario/forms.py`.
- `backend/apps/inventario/tests/test_fase7.py` y `test_concurrencia_fase7.py`.
- `frontend/templates/inventario/stock_lista.html`, `lote_lista.html`, `alertas.html`,
  `ajuste_form.html`, `movimiento_lista.html`.
- Componentes `_navegacion.html`, `_filtros.html`, `_stock_tabla.html`, `_lotes_tabla.html`.
- `scripts/verificar_inventario_fase7.py` y este informe.

Se implementó el modelo `OperacionAjusteInventario` y se creó la migración `backend/apps/inventario/migrations/0003_operacion_ajuste_inventario.py`, conforme a la autorización de la fase 7.

La migración fue aplicada y verificada exclusivamente sobre bases SQLite temporales. No se modificó ni migró la base de datos real `backend/datos/db.sqlite3`.

Las migraciones pendientes de Caja, Ventas e Inventario continuarán sin aplicarse a la base real hasta contar con un respaldo verificado y autorización expresa del usuario.
## Resultados reales

Primera verificación del módulo: **41 pruebas, 9,187 s, OK**, sobre archivo SQLite
temporal. Incluye modelos y FEFO anteriores y pruebas nuevas de fase 7.

Ejecución final con `venv/Scripts/python.exe scripts/verificar_inventario_fase7.py
--pruebas --http`:

## Mejora de Usabilidad (UX) del Formulario de Ajustes y Mermas

En respuesta a la revisión visual del usuario, se implementó una mejora integral de usabilidad exclusivamente en el formulario de ajustes y mermas (`ajuste_form.html`), sin modificar las reglas de negocio, Compras, Ventas, FEFO ni Caja:

1. **Guía conceptual explicativa:**
   - **Ajuste positivo:** Corregir existencias cuando hay más unidades físicas en almacén que las registradas en el sistema (sobrante por conteo).
   - **Ajuste negativo:** Corregir existencias cuando hay menos unidades físicas que las registradas (faltante por descuadre).
   - **Merma:** Retirar productos dañados, deteriorados, vencidos, perdidos o no aptos (siempre resta unidades).
   - **Nueva compra:** Advertencia clara de que los ingresos de mercadería nueva de proveedores deben registrarse desde el módulo de **Compras**, nunca mediante ajustes.
2. **Enlace condicional a Compras:**
   - Botón directo «Ir a Registrar compra» hacia `compras:compra_crear`, visible **exclusivamente** para usuarios con el permiso `gestionar_compras`.
3. **Detalles dinámicos del lote seleccionado:**
   - Al seleccionar o cargar un lote, se muestran en tiempo real:
     - Código y nombre del producto (`producto__codigo` · `producto__nombre`).
     - Cantidad inicial registrada al ingresar el lote.
     - Existencia actual en almacén.
     - Máximo ajuste positivo permitido: `cantidad_inicial - cantidad_actual`.
     - Máximo descuento permitido: `cantidad_actual` (hasta `-cantidad_actual`).
     - Stock resultante estimado: actualizado dinámicamente según la cantidad ingresada.
4. **Mensajes claros de límites en tiempo real:**
   - Si la suma supera la cantidad inicial:
     *«Este lote tiene {actual} unidades y originalmente ingresaron {inicial}. Puedes sumar como máximo {max_positivo} unidades mediante un ajuste. Si recibiste mercadería nueva, regístrala en Compras.»*
   - Si el descuento supera las existencias:
     *«Este lote tiene {actual} unidades disponibles. No puedes retirar más de {actual} unidades mediante un ajuste o merma (el stock no puede ser negativo).»*
   - Si se selecciona Merma y la cantidad no es negativa:
     *«Una merma siempre retira unidades del lote: debes ingresar una cantidad negativa (ejemplo: -3).»*
5. **Ejemplos destacados junto a la Cantidad:**
   - Badges visuales con ejemplos: `+2` (sumar dos unidades), `-3` (retirar tres unidades) y aviso destacado para que Merma sea siempre negativa.
6. **Etiquetas y validaciones mejoradas:**
   - Contador de caracteres en tiempo real para el motivo (entre 5 y 200).
   - Mensajes de error en servidor y cliente más comprensibles.
   - Selector visual de lotes con búsqueda rápida sincronizado con el campo de entrada.
7. **Diseño responsivo:**
   - Optimizado para 1280 × 800 (vista a dos columnas: formulario a la izquierda y guía a la derecha) y 390 × 844 (flujo vertical fluido sin desbordamientos).

---

## Pruebas y verificación técnica

| Comprobación | Resultado real |
|---|---|
| `manage.py check` | Código 0, sin incidencias |
| `makemigrations --check --dry-run` | Código 0, No changes detected |
| Suite completa | **284 pruebas en 174,989 s, OK; cero fallidas** |
| Regresiones anteriores | Las 243 pruebas existentes (fases 0 a 6) incluidas y aprobadas |
| Pruebas fase 7 | **41 pruebas aprobadas** (consultas, costos, UX, transacciones atómicas, idempotencia, concurrencia y migración) |
| Recursos locales | Código 0, integridad correcta |
| HTTP aislado | Aprobado; pantallas, permisos, costos, ajuste, auditoría, filtros, CSRF, recursos locales e idempotencia HTTP con deduplicación y rechazo |
| HTTP 404/500 | Ninguno |
| Archivos protegidos | Hashes iguales antes/después: SQLite real, `.env`, ambos reportes |
| Especificación raíz/docs | Copias idénticas |
| `git diff --check` | Sin errores; avisos de conversión LF/CRLF de Git |

Los 403 son pruebas deliberadas de permisos/CSRF; los 422 corresponden a ajuste
imposible, clave utilizada con datos alterados y filtro inválido. No representan fallos inesperados.
La suite comprueba protección de costos en Admin, consultas sin crecimiento N+1 por fila,
preservación de movimientos de compra/venta, pagos/caja, rollback de auditoría y deduplicación
idempotente con misma clave y mismos datos.

Evidencia conservada en:
`C:\Users\Jose\AppData\Local\Temp\Inventarios_verificacion_fase7_cu53l0cz`
(`check.txt`, `makemigrations.txt`, `test.txt`, `frontend.txt`, `http.json`,
`resultados.json`, cinco documentos HTML de respuesta y SQLite temporal).
No se han creado commits, push ni tags. Rama `main`; ambos reportes siguen sin seguimiento.

## Reproducción y revisión manual

Desde la raíz del proyecto, PowerShell:

```powershell
& .\venv\Scripts\python.exe scripts/verificar_inventario_fase7.py --pruebas --http
& .\venv\Scripts\python.exe scripts/verificar_inventario_fase7.py --abrir
```

El verificador comprueba el ejecutable, crea una carpeta única en TEMP, fija
ENV_FILE a un archivo inexistente y DB_PATH/TEST.NAME a SQLite temporales. Antes
de migrar comprueba la ruta exacta. Compara hashes de `.env`, SQLite real y ambos
reportes privados antes/después sin revelar contenido. Conserva logs y resultados.

`--abrir` ejecuta primero HTTP y deja el servidor en localhost con puerto libre.
Muestra la URL y contraseña aleatoria de `dueno_fase7` y `vendedor_fase7`, válidas
exclusivamente en esa base temporal. Ctrl+C detiene el servidor.

Revisar realmente a 1280×800 y 390×844:

1. Stock físico/disponible; producto «Solo vencidos» con físico 10 y disponible 0;
   productos sin lotes, stock bajo e inactivo con existencias.
2. Lotes y filtros, paginación general y de alertas; fechas nulas, hoy y límite.
3. Con Dueño, enlace Ajustar de un lote:
   - Tarjeta informativa dinámica con código, inicial, actual y límites calculados.
   - Retirar una unidad o registrar merma negativa; observar stock y movimiento.
   - Enviar y comprobar retroalimentación ("Registrando...") y protección anti doble clic.
   - Reenviar con misma clave y datos: recupera resultado sin duplicar stock ni movimientos.
   - Intentar merma positiva o cantidad excesiva: mensajes comprensibles y advertencias.
4. Con Vendedor, cuatro consultas permitidas y costos ausentes; URL de ajuste 403.
5. Menú móvil, etiquetas y errores, desplazamiento de tablas y navegación.
6. Network/Console sin 404/500 ni errores JS. Desconectar Internet conservando
   localhost accesible; todos los recursos deben seguir disponibles localmente.

Pendiente: revisión visual del usuario. La fase 7 permanece abierta hasta la aprobación final.
