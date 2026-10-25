# Fase 5 — Caja

## Implementación autorizada de OperacionCaja (2026-10-25)

Esta sección sustituye el estado provisional conservado al final del documento.
El usuario autorizó el nuevo modelo y su migración exclusivamente en SQLite
temporal. No se ha autorizado ni realizado su aplicación en la base real.
**La fase permanece abierta hasta completar las verificaciones y la revisión
visual del usuario.**

### Modelo, migración e idempotencia

- Nuevo `OperacionCaja`: UUID único, usuario responsable (PROTECT), acción,
  SHA-256, caja y movimiento resultantes (PROTECT), fecha de creación. Índice
  usuario/fecha y restricciones de acción válida y tipo de referencia a movimiento.
- Nueva `caja/0003_operacion_caja.py`, dependiente de `0002_integridad_fase1`.
  Solo crea la tabla nueva; no modifica los modelos históricos ni migraciones
  anteriores. Las referencias son nulas durante la reserva, invisible fuera de
  la transacción, y se completan antes del commit. Movimiento queda nulo en
  aperturas/cierres.
- Cada servicio exige autorización antes de iniciar su transacción. La primera
  consulta dentro de ella es el INSERT de reserva, que adquiere el escritor
  SQLite. No se utilizan bloqueos en memoria ni `select_for_update()`.
- La huella incluye usuario, acción, caja explícita (null en apertura, porque aún
  no existe), importes Decimal normalizados a dos decimales y textos recortados.
  No incluye CSRF ni decisiones de permisos enviadas por el cliente.
- Mismo UUID/datos: devuelve la referencia o resumen anterior. Mismo UUID/datos
  distintos: error controlado. Dos claves distintas permiten movimientos iguales.
  El índice único arbitra entre conexiones y procesos.
- Reserva, validación del turno, modificación y auditoría se confirman juntas.
  Fallos revierten todo. Si SQLite sigue ocupado al vencer el timeout de conexión,
  se solicita reintentar con la misma clave/datos; no se repite automáticamente
  una escritura. Cierre y movimiento compiten por el mismo escritor: o el
  movimiento entra antes y aparece en el cierre, o se rechaza por turno cerrado.

### Funcionalidades y permisos

- Apertura propia con monto inicial no negativo y turno opcional; una sola caja
  abierta por usuario, protegida también por la restricción SQL existente.
- INGRESO/EGRESO positivos con concepto y turno explícito. No se interpreta un
  POST antiguo como una operación sobre un turno nuevo. No se exige saldo mínimo
  para un egreso ni se vinculan compras automáticamente.
- Resumen Decimal con efectivo separado de otros métodos, ingresos, egresos y
  esperado. Cierre con contado, diferencia, CUADRA/SOBRA/FALTA, fecha y actor.
- LogAuditoria almacena el resumen completo versión 1 (propietario y actor,
  importes, métodos y fechas). Los cierres nuevos se consultan desde esa
  instantánea. Los antiguos sin instantánea se identifican como recalculados.
- `gestionar_caja` en vistas y servicios; solo el propietario registra movimientos.
  Dueño o superusuario activo pueden consultar y cerrar excepcionalmente otra
  caja. `ver_historial_caja` no concede esa excepción. Historial cerrado paginado
  de 20 registros y protegido por ese permiso.
- Admin de Caja, MovimientoCaja y OperacionCaja de consulta: sin altas, edición,
  borrado ni escritura en inlines. La modificación de regresiones antiguas está
  autorizada expresamente; el historial sigue protegido.
- Cinco rutas del contrato habilitadas. `/caja/?caja_id=ID` consulta un turno
  autorizado sin cambiar la identidad del turno del formulario. Menú por permisos.
- Pantallas con Bootstrap/AdminLTE locales, columnas adaptables y tablas con
  desplazamiento. HTMX sustituye movimientos y actualiza el resumen mediante OOB;
  conserva la clave en errores y emite otra para la siguiente operación exitosa.
  Los mismos formularios funcionan sin HTMX mediante POST ordinario.
- No hay ventas/POS ni implementación de fase 6. RN-10/RN-14 se mantienen como
  contrato para ventas; solo se usan pagos de fixtures para comprobar el resumen.

### Archivos de esta fase

Modificados: `backend/apps/caja/{admin,forms,models,services,urls,views}.py`,
`backend/apps/core/tests/test_regresiones_fase1.py`,
`frontend/templates/components/_menu.html`, ambas copias de
`ESPECIFICACION_SISTEMA.md`, `docs/FASE_4_RESULTADOS.md` y este informe.

Nuevos: `backend/apps/caja/migrations/0003_operacion_caja.py`,
`backend/apps/caja/tests/test_{preparacion,operaciones,concurrencia,migracion}_fase5.py`,
`frontend/templates/caja/{estado,cierre,historial}.html`,
`frontend/templates/caja/partials/_{movimientos,resumen,actualizacion}.html`
y `scripts/verificar_caja_fase5.py`.

Las correcciones documentales previas se conservan: fase 3 completada según
confirmación del usuario y cifra final de fase 4 corregida de 168 a 170, coincidente
con su propio apartado de pruebas. Los requisitos originales no se eliminan;
las decisiones nuevas autorizadas se registran explícitamente en §9.7.

### Verificación reproducible y revisión visual pendiente

Desde la raíz, en PowerShell:

```powershell
& .\venv\Scripts\python.exe scripts/verificar_caja_fase5.py --pruebas --http
& .\venv\Scripts\python.exe scripts/verificar_caja_fase5.py --abrir
```

El script crea una carpeta única en TEMP, configuración sin `.env`, SQLite y
TEST.NAME temporales. Valida la ruta antes de migrar, crea cuentas temporales,
usa un servidor WSGI en localhost con puerto libre y conserva evidencia allí.
Compara los hashes de la base real, `.env` y los dos reportes antes/después.
`--abrir` ejecuta primero HTTP y muestra URL/credenciales **temporales**; se detiene
con Ctrl+C. No modifica ni elimina bases o respaldos existentes.

Revisión manual requerida (no acreditada por los tests):

1. Abrir DevTools en el navegador, revisar a 1280×800 y 390×844. Iniciar sesión
   con `vendedor_fase5` y la contraseña temporal impresa.
2. Abrir caja con Bs 100, turno opcional. Registrar ingreso 10 y egreso 5.
   Verificar resumen Bs 105 y actualización parcial sin recargar toda la pantalla.
3. Dejar una pestaña antigua abierta. Cerrar contando 105 (CUADRA), iniciar otro
   turno y enviar un movimiento desde la pestaña antigua: debe rechazarlo sin
   afectar el nuevo. Repetir cierres con contado superior/inferior para SOBRA/FALTA.
4. Con Dueño consultar historial y seleccionar el turno abierto de Vendedor;
   debe permitir cierre excepcional e indicar propietario y responsable. Vendedor
   no debe ver el enlace de historial ni acceder mediante URL directa (403).
5. Revisar menú móvil, formularios, mensajes, tablas y ausencia de solapamientos.
   En Network/Console no debe haber 404/500, errores JS ni recursos de dominios
   externos. Desconectar Internet manteniendo localhost accesible y repetir;
   no usar el modo Offline de DevTools si bloquea también localhost.

El análisis de HTML y las peticiones HTTP no acreditan ejecución JavaScript,
layout ni inspección visual. Es necesaria la revisión anterior del usuario.

### Resultados de la ejecución actual

En proceso de consolidación al terminar las verificaciones. La ejecución inicial
del módulo aprobó 44 pruebas en 42,035 s; incluye las carreras de apertura,
movimiento y cierre, reenvíos, permisos y rollback. No sustituye la suite final.

### Límites y pasos pendientes

- La revisión visual y la ejecución JavaScript en navegador siguen pendientes:
  no se han abierto e inspeccionado estas pantallas desde este entorno.
- La base real sigue en el esquema anterior. No utilizar las escrituras de caja
  sobre ella antes de autorizar y aplicar la migración nueva; el código requiere
  la tabla OperacionCaja. Este trabajo solo acredita la actualización aislada.
- SQLite admite un escritor a la vez. Un conflicto transitorio puede requerir
  reenviar la misma clave; no debe reemplazarse por otra después de perder una
  respuesta, porque podría representar una nueva operación legítima.
- No se purgan claves idempotentes ni se reescriben cierres antiguos. Las
  referencias nulas de reserva solo existen dentro de la transacción del servicio;
  escrituras SQL/ORM arbitrarias fuera de servicios no forman parte del contrato.
- Las ventas, sus pagos y la validación de caja abierta al vender pertenecen a
  fase 6. No se implementan aquí ni se cambian las reglas de compras.
- No hay commits, push ni tags. Los reportes locales de fase 1 permanecen sin
  seguimiento. SQLite, `.env`, logs y venv continúan ignorados y no están
  versionados; las dos copias de la especificación permanecen idénticas.

## Registro del avance anterior (antes de autorizar OperacionCaja)

El texto siguiente es histórico y no describe el estado actual.

Fecha de inicio: 2026-10-25. Implementación parcial; **fase no terminada**.

## Autorización pendiente: idempotencia persistente

La autorización del usuario exige distinguir un reenvío de dos movimientos
legítimos iguales, incluso entre procesos, y prohíbe cambiar el esquema sin
autorización previa. Se propone una nueva tabla `caja.OperacionCaja`:

| Campo | Definición propuesta |
|---|---|
| id | BigAutoField, clave primaria |
| clave | UUIDField único, clave de la operación enviada por el formulario |
| usuario | FK al usuario, PROTECT |
| accion | CharField(10): ABRIR, MOVIMIENTO o CERRAR |
| huella | CharField(64): SHA-256 de los datos normalizados, incluido turno objetivo |
| caja | FK a Caja, PROTECT, nullable mientras se construye el resultado |
| movimiento | FK a MovimientoCaja, PROTECT, nullable para apertura/cierre |
| creado_en | DateTimeField(auto_now_add=True) |

Ordering propuesto: `[-creado_en, -pk]`. No contendrá contraseñas ni datos de sesión.
La migración nueva solo crearía la tabla y sus índices/relaciones; no alteraría
las tablas ni los registros existentes. Solo se aplicaría sobre SQLite temporal.

La clave se reserva mediante escritura dentro de la misma transacción que la
operación. Su unicidad se garantiza en SQL, no con memoria del proceso. Al repetir
la clave se comprueban usuario, acción y huella antes de devolver el resultado
original. Cambiar datos con la misma clave se rechaza. Dos claves distintas permiten
dos movimientos iguales. Si falla la operación se revierte también la reserva.
En SQLite la primera escritura serializa escritores; ante bloqueo se revierte y
se informa al usuario para reintentar con la misma clave. No se presupone bloqueo
de filas por `select_for_update()`.

La unicidad existente de turnos abiertos protege aperturas, pero no distingue
reenvíos de movimientos; un cierre se protege además por la transición condicional
ABIERTA→CERRADA. No se usará LogAuditoria como sustituto improvisado de una tabla
de idempotencia ni se garantizará persistencia con bloqueos en memoria.

**Estado: propuesta enviada para aprobación. No se ha creado el modelo ni una
migración, y las escrituras de caja no se habilitarán hasta resolver este punto.**

## Decisiones ya autorizadas

- Cierre excepcional ajeno solo por rol Dueño o superusuario activo, con permiso
  de gestión; `ver_historial_caja` por sí solo no lo concede.
- Caja y MovimientoCaja quedan de consulta en Admin, incluidos turnos abiertos,
  inlines, altas, cambios y borrados. La regresión de fase 1 que permitía escritura
  administrativa se actualiza por autorización expresa, no para ocultar un fallo.
- Formularios de movimiento/cierre identifican explícitamente el turno mostrado.
- El cierre almacenará resumen completo en LogAuditoria, con propietario y actor.
  Un cierre antiguo sin resumen se mostrará como recalculado, sin alterar datos.
- No se conectan compras con egresos ni se implementa fase 6.

## Avance independiente del esquema

Implementado:

- `caja/admin.py`: consulta para Caja y MovimientoCaja, también abiertos e inlines.
- `caja/forms.py`: AbrirCajaForm, MovimientoCajaForm y CerrarCajaForm, importes
  Decimal, límites, turno objetivo explícito y rechazo de campos manipulados.
  La clave UUID está preparada como entrada; todavía no hay escritura persistente.
- `caja/services.py`: consultas `obtener_caja`, `calcular_resumen_caja`,
  `listar_cierres` y comprobación `puede_cerrar_ajena`. Cierre excepcional limitado
  a Dueño/superusuario activo; historial solo no permite consultar turnos ajenos
  abiertos. No se implementó todavía la operación de cierre.
- Resumen de pagos separado de agregaciones de movimientos, con efectivo y otros
  métodos. Los métodos inactivos con pagos históricos siguen incluidos.
- Lectura de instantáneas de LogAuditoria versión 1; sin instantánea compatible,
  el cierre se recalcula y entrega `recalculado=True`. Ninguna consulta escribe.
- Historial paginado de cerradas, con autorización `ver_historial_caja`.
- `caja/tests/test_preparacion_fase5.py`: pruebas de estas partes y Admin.
- Regresiones administrativas de fase 1 actualizadas: altas ahora devuelven 403,
  y se comprueba que tampoco pueda editarse un turno abierto. Se conserva la
  validación del formulario administrativo heredado y la protección de cerrados.
- Se corrigió la casilla de fase 3 según confirmación del usuario y la conclusión
  de fase 4 de 168 a 170, sin modificar requisitos ni inventar ejecuciones.

Archivos modificados: `backend/apps/caja/admin.py`, `forms.py`, `services.py`,
`backend/apps/core/tests/test_regresiones_fase1.py`, `ESPECIFICACION_SISTEMA.md`,
`docs/ESPECIFICACION_SISTEMA.md` y `docs/FASE_4_RESULTADOS.md`.
Archivos nuevos: `backend/apps/caja/tests/test_preparacion_fase5.py` y este informe.

## Pendientes antes de cerrar la fase

1. Aprobar o revisar la propuesta de esquema de OperacionCaja.
2. Implementar y probar escrituras transaccionales/idempotentes de apertura,
   movimiento y cierre, incluido resumen completo persistido en LogAuditoria.
3. Conectar las cinco rutas, vistas, formularios, HTMX, plantillas y navegación.
4. Probar concurrencia de escrituras, reenvíos, formularios antiguos y HTTP aislado.
5. Preparar el comando de revisión visual y revisar realmente escritorio/móvil.

Las rutas de caja siguen vacías. No hay prueba HTTP de pantallas nuevas ni comando
visual terminado en este avance. No se declara completa ni operativa la fase 5.

## Resultados reales de este avance

Ejecutados con `venv/Scripts/python.exe`, configuración sin leer `.env` y SQLite
temporal independiente (incluido TEST.NAME). La suite se ejecutó desde `backend`.

| Comprobación | Resultado |
|---|---|
| `manage.py check` | Código 0, sin incidencias |
| `makemigrations --check --dry-run` | Código 0, No changes detected |
| `manage.py test --noinput` | **183 pruebas en 84,963 s, OK** |
| `scripts/preparar_frontend.py --verificar` | Código 0, integridad correcta |

Son las 170 pruebas anteriores (con la protección administrativa actualizada por
autorización expresa) y 13 nuevas. No acreditan las escrituras ni concurrencia de
caja pendientes. Los HTTP 403 de pruebas negativas del Admin son esperados.

Evidencia: `C:\Users\Jose\AppData\Local\Temp\Inventarios_fase5_e453906b85174d46bdf87e23c7ce5863`
(`check.txt`, `makemigrations.txt`, `test.txt`, `frontend.txt`, `protegidos.json`).
Comparación final de SHA-256: `.env`, SQLite real y ambos reportes locales sin
cambios. No se tocaron modelos ni migraciones, no se ejecutaron migraciones en la
base real, y no se hicieron commits, push ni tags. Rama `main`.
