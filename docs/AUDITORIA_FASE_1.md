# Fase 1 — Correcciones y verificación final

Fecha: 2026-10-24.

**Estado: correcciones implementadas y validadas; cierre operativo pendiente de
autorizar y aplicar seis migraciones a la base real.** No se inició la fase 2.

Este informe actualiza la auditoría previa, cuyo veredicto fue FASE 1 INCOMPLETA.
El informe histórico y su respaldo se conservaron, sin sobrescribirlos, en
`C:\Users\Jose\AppData\Local\Temp\SistemaInventarios_respaldo_privado_d7ziq840`.

## Criterios revisados

| Criterio | Resultado |
|---|---|
| Modelos, relaciones y datos iniciales de fase 1 | Se conservan los 20 modelos y sus relaciones; 12 permisos, 2 roles y 3 métodos de pago en la copia real. |
| Ocho campos monetarios | CHECK no negativo y validación de modelo; regresiones verificadas. |
| Historial de compras y ventas | Consulta en Admin; altas independientes, cambios, bajas e inlines protegidos. |
| Cajas cerradas y sus movimientos | POST de cambios/bajas rechazado, consulta permitida. No se admiten movimientos nuevos ni traslados a cajas cerradas. |
| Cinco Meta.ordering | Implementados y documentados, sin modificar cálculos. |
| Lotes y movimientos de inventario | Admin de solo lectura, justificado por las operaciones transaccionales de la especificación. |
| Migraciones | Seis archivos nuevos; ninguna migración anterior modificada. Aplicación y preservación comprobadas en copias. |
| Carga inicial | Sigue siendo idempotente; se conservan identificadores y relaciones al repetirla. |
| Pruebas | 81 aprobadas; check y detección de cambios pendientes satisfactorios. |
| Base real | Sin modificaciones; seis migraciones nuevas deliberadamente pendientes. |

## Restricciones monetarias

| Campo | CheckConstraint nuevo |
|---|---|
| Presentacion.precio_venta | presentacion_precio_no_negativo |
| Compra.total | compra_total_no_negativo |
| DetalleCompra.costo_unitario | detalle_compra_costo_no_negativo |
| DetalleCompra.subtotal | detalle_compra_subtotal_no_negativo |
| Lote.costo_unitario | lote_costo_no_negativo |
| DetalleVenta.precio_aplicado | detalle_venta_precio_no_negativo |
| DetalleVenta.subtotal | detalle_venta_subtotal_no_negativo |
| Caja.monto_contado | caja_monto_contado_no_negativo |

Los ocho campos admiten cero. `monto_contado` conserva `null=True, blank=True`,
añade `validar_dinero` y admite explícitamente NULL en el CHECK. Los otros siete
ya tenían ese validador. La diferencia de caja puede seguir siendo negativa.
No se modificaron las restricciones estrictamente positivas de Pago y MovimientoCaja.

Las pruebas usan `full_clean(validate_constraints=False)` para demostrar el rechazo
por validadores y `QuerySet.update()` para demostrar el rechazo por SQLite sin
ejecutar validación Python. También verifican cero, monto contado nulo y diferencia
negativa. No se agregó un `save()` que altere el comportamiento general del ORM.

## Protección del administrador

- Compra, DetalleCompra, Venta, DetalleVenta, DetalleVentaLote y Pago son de consulta.
  Se deniegan altas independientes porque no ejecutan los servicios transaccionales
  definidos en 8.1/8.3; crear pagos o detalles aislados alteraría el historial.
- Se aplica la misma protección a los inlines de compras y ventas, y se elimina la
  disponibilidad de borrado masivo mediante los permisos del administrador.
- Una Caja CERRADA y sus MovimientoCaja no admiten edición ni eliminación. Los
  inlines de un turno cerrado tampoco admiten altas ni cambios. El formulario de
  movimiento limita el destino a turnos abiertos y comprueba tanto el turno original
  como el destino para impedir traslados que alteren un cierre.
- Se conserva la administración existente de cajas abiertas. Los servicios de
  apertura/cierre y su auditoría transaccional siguen correspondiendo a fase 5.
- Lote y MovimientoInventario son de consulta: las altas y ajustes deben actualizar
  lotes, stock y bitácora conjuntamente mediante los servicios de 8.2/8.3. Así se
  eliminan los formularios de altas incompletos sin implementar fases posteriores.
- Las protecciones se verificaron con GET y POST reales del cliente de pruebas
  Django, incluso autenticado como superusuario; no dependen de ocultar botones.
  Son protecciones del administrador. No sustituyen los servicios de negocio ni
  impiden escrituras SQL arbitrarias realizadas fuera de la aplicación.

Ordenamientos añadidos: `Usuario: ["username"]`; `DetalleCompra`, `DetalleVenta`,
`DetalleVentaLote` y `Pago: ["pk"]`. La especificación exigía ordering sin fijar
estos cinco criterios: se documentó un orden estable de presentación, sin inventar
prioridad de negocio o cambiar FEFO.

El docstring de `cargar_datos_iniciales` ahora describe su comportamiento real:
no duplica datos y conserva descripciones/métodos existentes, pero repone permisos
iniciales retirados de los roles. No se cambió ese algoritmo ni la matriz de roles.

## Archivos modificados en esta corrección

- `backend/apps/{catalogo,compras,inventario,ventas,caja,usuarios}/models.py`.
- `backend/apps/{compras,ventas,inventario,caja}/admin.py`.
- `backend/apps/core/admin.py`: mixin compartido de consulta.
- `backend/apps/core/management/commands/cargar_datos_iniciales.py`: docstring.
- `.gitignore`: copias SQLite alternativas, respaldos y logs rotados.
- `ESPECIFICACION_SISTEMA.md` y `docs/ESPECIFICACION_SISTEMA.md`: mismo contenido,
  estado actualizado y precisiones de implementación; contratos y reglas conservados.

Archivos nuevos:

- `backend/apps/caja/forms.py`.
- `backend/apps/core/tests/test_regresiones_fase1.py`.
- Este informe: `docs/AUDITORIA_FASE_1.md`.
- Las seis migraciones siguientes.

| Aplicación | Migración nueva |
|---|---|
| caja | `0002_integridad_fase1.py` |
| catalogo | `0002_integridad_fase1.py` |
| compras | `0002_integridad_fase1.py` |
| inventario | `0002_integridad_fase1.py` |
| usuarios | `0003_integridad_fase1.py` |
| ventas | `0002_integridad_fase1.py` |

Se generan AlterModelOptions, un AlterField de validador y ocho AddConstraint.
No hay RunPython, eliminación de campos/modelos ni corrección automática de datos.
SQLite reconstruye internamente las tablas afectadas al añadir CHECK; por eso se
ensayó la actualización con comparación completa de registros.

## Resultados reales

Todas las ejecuciones Python utilizaron `venv/Scripts/python.exe`: Python 3.13.7,
Django 5.2.18. No se instalaron dependencias.

| Verificación | Resultado |
|---|---|
| manage.py check | Código 0; sin incidencias. |
| manage.py makemigrations --check --dry-run | Código 0; No changes detected. |
| manage.py test --noinput | Código 0; **81 pruebas en 55,905 s, OK**. |
| manage.py migrate --plan, configuración real | Seis migraciones pendientes; solo lectura, ninguna aplicada. |
| manage.py showmigrations, configuración real | 26 aplicadas, seis nuevas sin aplicar. |
| migrate --noinput en dos copias aisladas | Código 0; ambas pasan de 26 a 32 migraciones. |
| migrate --plan en copia actualizada | Sin operaciones pendientes. |
| PRAGMA integrity_check en ambas copias | ok. |
| PRAGMA foreign_key_check en ambas copias | Sin errores. |
| Datos existentes antes/después de migrar | Iguales en todas las tablas salvo django_migrations, que añade seis registros. |
| Búsqueda de negativos en los ocho campos reales | Cero registros incompatibles. |
| Hash de base real y .env antes/después | Sin cambios. |
| Hash de todas las migraciones anteriores | Sin cambios. |
| git diff --check | Sin errores de espacios; advertencias de conversión LF/CRLF. |

Se conservaron usuarios, superusuario, permisos, roles, relaciones M2M y métodos
de pago de la copia del estado real. Como la base actual no tiene pagos ni ventas,
una segunda copia recibió historial sintético antes de migrar para comprobar
también preservación de pagos, compras, ventas, lotes y movimientos no vacíos.
La prueba automatizada de migraciones repite ese escenario sobre la base exclusiva
del test runner. No se publicaron credenciales ni contenido de registros privados.

Las advertencias HTTP 403 del administrador son rechazos esperados de las pruebas
de protección. También se conservan los casos negativos CSRF y logout por GET
(403/405). No son errores de la suite. El primer recolector de comparación de
copias asumía una columna `id` en django_session y falló antes de migrar; se corrigió
para comparar todas las filas sin asumir el nombre de la clave. Los dos ensayos
de migración posteriores finalizaron correctamente.

Evidencias y copias de ensayo, fuera de Git y con ACL privada:

`C:\Users\Jose\AppData\Local\Temp\Inventarios_correcciones_fase1_skegidzf`

- `ensayo.sqlite3`: copia del estado real, actualizada.
- `ensayo_con_historial.sqlite3`: segunda copia con datos sintéticos, actualizada.
- `validacion_migraciones.json`: recuentos y huellas de filas antes/después.
- `test_final.txt`, `real_check.txt`, `real_makemigrations.txt`,
  `real_migrate.txt`, `real_showmigrations.txt`, `copia_plan.txt`.
- `verificacion_final.json`: conservación de originales y exclusiones de Git.

Estas son copias de ensayo en Temp, no un reemplazo del respaldo histórico. No se
eliminó ningún respaldo. La conservación permanente del respaldo anterior sigue
requiriendo trasladarlo fuera de Temp a una carpeta privada duradera.

## Git

No se hicieron commits ni push. Se conservó el trabajo previo sin sobrescribirlo.
La implementación inicial de fase 1 ya estaba modificada/sin seguimiento antes de
esta tarea: para versionar la fase completa deben incluirse también sus modelos,
administradores, migraciones iniciales, pruebas y comando de carga, además de los
archivos enumerados arriba. No basta con agregar únicamente las migraciones nuevas.

Se verificó que .env, SQLite, venv, logs, logs rotados, archivos .db/.bak y respaldos
en carpetas `respaldos/` o `backups/`, o ZIP con prefijo respaldo/backup, están
excluidos. Los ZIP arbitrarios de código no se excluyen globalmente. No se añadió
ninguna copia de datos a Git.

## Cómo verificar y condición de cierre

Desde la raíz del proyecto, estos comandos no aplican migraciones a la base real:

```powershell
.\venv\Scripts\python.exe .\backend\manage.py check
.\venv\Scripts\python.exe .\backend\manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe .\backend\manage.py test --noinput
.\venv\Scripts\python.exe .\backend\manage.py migrate --plan
```

Los defectos autorizados quedan corregidos y cubiertos por pruebas. **La actualización
es técnicamente apta para el estado de la base auditado:** no hay importes negativos
incompatibles y se demostró preservación completa en copias. Antes de aplicarla al
original se necesita autorización expresa, cerrar las conexiones de la aplicación
y conservar un respaldo reciente verificado. Si aparecen nuevos datos incompatibles,
hay que detenerse y revisarlos; no corregirlos ni eliminarlos automáticamente.

**No se declara cerrada la fase 1 en la instalación real mientras estas seis
migraciones sigan pendientes.** No se observan defectos pendientes de esta corrección
en código y pruebas. El cierre visual de fase 0 que figura en su documento no se
revalidó en esta tarea, y las funciones de fases posteriores permanecen fuera de alcance.
