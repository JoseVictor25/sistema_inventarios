# Fase 9 — Auditoría, respaldos y panel de inicio

Fecha: 27 de octubre de 2026. Base de trabajo: `main`, commit `799a6ab`.
Implementación autorizada sin cambios de esquema ni operaciones sobre datos reales.
La revisión visual del usuario y el cierre de fase permanecen pendientes.

## Funcionalidades

- Bitácora: `LogAuditoria` existente, 20 entradas por página, orden descendente
  por fecha e identificador, filtros opcionales por usuario, entidad exacta y
  fechas locales inclusivas. Sin límite de 366 días. Autores nulos e inactivos
  visibles, valores JSON legibles y escapados, sin edición ni eliminación.
- Se reutiliza `registrar_cambio()` sin duplicar los eventos de Catálogo, Caja e
  Inventario. Los respaldos generan registros técnicos, no nuevos eventos de negocio.
- Admin exige `ver_auditoria` y permiso técnico de consulta; incluso el superusuario
  carece de botones ordinarios para agregar, cambiar o borrar eventos.
- Panel: ventas y cantidad del día requieren `ver_reportes`; turno propio requiere
  `gestionar_caja`; alertas requieren `ver_stock`. Se cuentan productos distintos
  con stock bajo, próximos a vencer y vencidos, sin confundir productos con lotes.
  No se modifica el historial de ventas ni los permisos iniciales.
- Respaldos manuales y consulta autorizados por `respaldar`. Formulario POST con
  CSRF; no admite destinos ni parámetros del cliente. No hay restauración web.

## Rutas y permisos

| Método y ruta | Permiso |
|---|---|
| GET `/` | Sesión activa; cada bloque aplica su permiso |
| GET `/auditoria/` | `ver_auditoria` |
| GET `/sistema/respaldos/` | `respaldar` |
| POST `/sistema/respaldos/crear/` | `respaldar` y CSRF |

## Motor de respaldos

`core/respaldos.py` es compartido por el servicio web y `scripts/respaldo.py`.
El servicio autoriza al usuario; la consola requiere acceso del operador local
al entorno y a los archivos. No se admiten rutas desde el navegador.

1. Valida fuente existente, carpeta separada y retención positiva.
2. Obtiene un bloqueo de archivo entre procesos, mantenido durante la retención.
   Otra ejecución recibe un error controlado. El archivo de bloqueo permanece;
   Windows libera el bloqueo al cerrar el proceso.
3. Abre la fuente con `mode=ro` y usa `sqlite3.Connection.backup()` por páginas,
   con límite de tiempo. Incluye datos confirmados en WAL, no escrituras pendientes.
4. Crea provisional exclusivo; comprueba `integrity_check`, `foreign_key_check`
   y tablas esenciales, y calcula tamaño y SHA-256.
5. Publica sin sobrescritura `respaldo_YYYYMMDD_HHMMSS_UUID.sqlite3` y manifiesto
   `.json` (fecha UTC, tamaño, hash, migraciones presentes e identificador de motor).
6. Retiene las últimas `BACKUP_CONSERVAR` copias gestionadas y verificadas.
   No elimina desconocidas, alteradas, corruptas, provisionales ajenas ni copias
   sin manifiesto. Si la publicación del manifiesto falla, conserva la SQLite
   como no gestionada y no aplica retención. Si falla la retención, conserva
   el respaldo nuevo y comunica advertencia.

Los resultados y errores se escriben en el sistema de logs existente. No hay tablas,
triggers ni migraciones nuevos. Un manifiesto y su hash permiten detectar daños,
pero no son una firma criptográfica frente a un atacante con escritura en la carpeta.
La carpeta de respaldos debe quedar bajo permisos del operador. No se promete
atomicidad conjunta de los dos archivos ante corte eléctrico ni recuperación ante
pérdida del disco; la copia externa sigue siendo necesaria.

## Archivos de implementación

- Auditoría: `backend/apps/auditoria/{forms,services,views,urls,admin}.py`.
- Core: `backend/apps/core/{services,respaldos,views,urls}.py`.
- Pruebas: `backend/apps/core/tests/test_fase9.py` y `test_respaldos_fase9.py`.
- Interfaz: `frontend/templates/auditoria/lista.html`, `core/respaldos.html`,
  `inicio.html` y `components/_menu.html`.
- Scripts: `scripts/respaldo.py` y `scripts/verificar_fase9.py`.
- Documentación: este informe y ambas copias de `ESPECIFICACION_SISTEMA.md`.

## Verificación

Primera verificación integral: 342 pruebas aprobadas en 238,737 segundos,
`check` sin incidencias, `makemigrations --check --dry-run` sin cambios,
integridad frontend correcta. HTTP: 30 solicitudes sin 404 ni 500; los 403 y
422 corresponden a denegaciones y validaciones provocadas deliberadamente.
Recuperación: 33 tablas comparadas íntegramente en SQLite nueva, con integridad
y claves foráneas correctas. También se ejecutó el CLI de respaldo sobre esa
misma fuente ficticia. Evidencias iniciales:
`C:\Users\Jose\AppData\Local\Temp\Inventarios_verificacion_fase9_8yaq_z35`.

Resultado final de regresión: **346 pruebas aprobadas en 307,442 segundos**
(319 anteriores y 27 nuevas), sin fallos ni errores. `check`, verificación de
migraciones e integridad frontend finalizaron con código 0. Evidencia:
`C:\Users\Jose\AppData\Local\Temp\Inventarios_verificacion_fase9_syhd7anr`.

Después de esa suite, el verificador detectó un precio ficticio enviado como texto
en lugar de `Decimal` al servicio de Catálogo. Se corrigió únicamente la preparación
de la demostración y se repitieron `--http --respaldos`: **código 0**, 30 solicitudes
sin 404/500 y recuperación íntegra de 33 tablas. Evidencia definitiva de integración:
`C:\Users\Jose\AppData\Local\Temp\Inventarios_verificacion_fase9_3as1h2uy`.
El fallo previo queda registrado como evidencia histórica, no se presenta como aprobado.

| Comprobación | Resultado |
|---|---|
| Django check | Sin incidencias |
| makemigrations --check --dry-run | No changes detected |
| Suite completa | 346/346, OK |
| Frontend local | Integridad correcta |
| HTTP real en servidor localhost temporal | 30 peticiones; permisos y CSRF comprobados |
| Respaldo por servicio, web y CLI | Aprobado sobre SQLite ficticia |
| Recuperación en archivo nuevo | 33 tablas, filas y relaciones preservadas |
| Archivos protegidos | Los cuatro hashes coinciden |
| Inspección visual y ejecución JS en WebView2 | Pendientes del usuario |

Respaldo temporal utilizado en la recuperación: 540672 bytes,
`respaldo_20261027_195400_eadb5fde50ca4befae06a6760fbfae79.sqlite3`, dentro de
`respaldos/` de la evidencia definitiva. SHA-256:
`676b966e9e0baaf04a12a68e62196ce5cf3ce091a6ececd83867437cdd895e9a`.
`recuperacion.json` registra cantidades por tabla; `http.json`, los estados HTTP;
`respaldo_cli.txt`, el resultado del comando. No contienen datos del negocio real.
La primera ejecución específica detectó conexiones de las pruebas SQLite sin cerrar
en Windows y una expectativa que omitía la consulta de autorización; se corrigieron
antes de repetir las comprobaciones. No fueron errores sobre datos reales.

Los cuatro archivos protegidos conservan su SHA-256 inicial; no se abrieron
conexiones a la base original ni se leyó el contenido de `.env` o de los dos
informes privados. SHA-256 de la SQLite real antes y después:
`40d61b7947251655e3af6055fab58130d29a24586b103aa62ff4d5b847e37f50`.
Los verificadores vuelven a comparar los cuatro archivos al salir.

Pruebas añadidas: filtros y límites de medianoche, más de 366 días, orden y
paginación, autores nulos/inactivos, permisos de servicios/vistas/Admin, CSRF,
escapado HTML, panel según rol y productos sin duplicación por lotes, respaldo
válido, corrupto, tablas ausentes, FK inválidas, colisiones, limpieza de provisionales,
retención, fallo de publicación, límite de tiempo, bloqueo entre procesos,
conexión WAL abierta y recuperación temporal.

## Reproducción y revisión visual

Desde la raíz, en PowerShell:

```powershell
.\venv\Scripts\python.exe scripts/verificar_fase9.py --pruebas --http --respaldos
.\venv\Scripts\python.exe scripts/verificar_fase9.py --abrir
```

El segundo comando crea una SQLite nueva en TEMP, migra solo esa base, prepara
datos ficticios y abre el navegador local. Imprime dirección, usuarios
`dueno_fase8` y `vendedor_fase8` (reutilización de la fixture anterior) y una
contraseña aleatoria válida solo para esa demostración. Ctrl+C cierra el servidor.
La carpeta temporal conserva evidencias y bases ficticias para inspección.

Revisar en 1280×800 y 390×844:

1. Dueño: inicio con dos ventas ficticias por 38, turno cerrado y alertas; accesos rápidos.
2. Bitácora: cierre, cambio de precio y merma ficticios; filtros, valores y legibilidad.
3. Respaldos: crear copia, observar fecha/tamaño/hash y mensaje de éxito.
4. Vendedor: sin ventas globales, bitácora ni respaldos; URL directa de estas últimas
   devuelve 403. Puede consultar alertas y su estado de caja.
5. Confirmar menú, tablas y formularios sin desbordamiento de página; revisar consola
   y red del navegador. Las comprobaciones HTTP no equivalen a inspección visual
   ni prueban por sí mismas la ejecución de JavaScript en WebView2.

## Automatización preparada, no instalada

Después de aprobar la operación productiva, la acción diaria del Programador debe
apuntar a la ruta absoluta de `venv/Scripts/python.exe`, argumento absoluto
`scripts/respaldo.py`, directorio inicial raíz del proyecto y usuario Windows con
lectura de la base y escritura en `BACKUP_DIR`/`LOG_DIR`. Frecuencia diaria a las
21:00, sin iniciar otra instancia si una sigue activa. El motor mantiene además
su propio bloqueo. No se ejecutó ni instaló esta tarea. La integración del ejecutable
`--respaldo` corresponde al empaquetado, no a esta fase.

No ejecutar el comando de respaldo de producción para revisar esta implementación:
utilizar el verificador aislado indicado arriba.

## Limitaciones y pendientes

- Pendiente inspección visual del usuario; fase no cerrada.
- Auditoría inmutable en interfaces y servicios ordinarios, no frente a SQL/ORM
  privilegiado, conforme a la decisión de no incorporar triggers.
- No se ha probado recuperación en otro equipo; la comprobación aquí es temporal
  y local. Compatibilidad del esquema se documenta en el manifiesto, no se migra
  automáticamente una copia restaurada.
- Listar respaldos recalcula hashes y retener comprueba integridad; con bases grandes
  su coste es proporcional al volumen de las copias. Creación síncrona con límite
  de tiempo, sin tareas ni dependencias adicionales.
- Las migraciones previas pendientes sobre la base real siguen sin aplicar.
- Sin commits, staging, push, ramas o etiquetas. Los dos informes privados de fase 1
  se conservan sin seguimiento.

Estado Git de entrega: `main`, 11 archivos existentes modificados y 9 nuevos de
esta implementación, más los dos informes privados que ya estaban sin seguimiento.
`git diff --check` no detecta errores de espacios. Git avisa de conversión LF/CRLF
por la configuración existente de Windows; no se ha cambiado esa configuración.
Las exclusiones de `.env`, SQLite, `venv`, logs y carpetas de respaldo siguen vigentes.
