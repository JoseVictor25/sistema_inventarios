# Fase 2 — Usuarios, roles y permisos

Fecha de verificación: 2026-10-24.

**Resultado funcional: implementado y aprobado en pruebas automatizadas. Cierre
visual final pendiente.** Las funcionalidades obligatorias están implementadas y
las 106 pruebas automatizadas pasaron. No hay migraciones nuevas ni pendientes.
La comprobación final posterior ejecutó 52 peticiones HTTP reales sobre SQLite
temporal, sin 404/500, pero los navegadores del entorno no consiguieron cargar
una página. No se aprueba la inspección visual. Ver
`docs/VERIFICACION_FINAL_FASE_2.md`. No se inició fase 3.

## Funcionalidades y contrato

| Ruta | Nombre | Comportamiento |
|---|---|---|
| `/usuarios/` | `usuarios:lista` | GET; usuarios, nombre, rol, estado y acciones permitidas. |
| `/usuarios/nuevo/` | `usuarios:usuario_crear` | GET/POST; alta validada de cuenta ordinaria. |
| `/usuarios/<int:pk>/editar/` | `usuarios:usuario_editar` | GET/POST; edición, asignación de rol existente y activación/desactivación. |
| `/usuarios/roles/` | `usuarios:rol_lista` | GET; matriz de roles y permisos, sin escritura. |

Todas exigen `gestionar_usuarios` antes de procesar la petición. Usuarios anónimos
van al login; usuarios autenticados sin permiso reciben 403 con la página existente.
Un POST autorizado a una pantalla solo de consulta devuelve 405 sin escribir.

Se conservan LoginView, LogoutView, sesiones, CSRF y los recursos locales existentes.
Las nuevas plantillas heredan de base.html. El menú muestra usuarios y roles solo
cuando corresponde; el backend verifica permisos independientemente de la interfaz.

## Seguridad y decisiones autorizadas

- `tiene_permiso` consulta los permisos del rol, sin comparar el nombre del rol.
- Un superusuario autenticado y activo conserva acceso. Usuarios inactivos o sin
  rol no tienen permisos de negocio. No se asignan permisos individuales.
- `codigos_permitidos` proporciona al contexto los códigos efectivos. No se guardan
  permisos en la sesión: el cambio de rol se refleja en la siguiente petición.
- La autenticación estándar de Django rechaza cuentas inactivas. Si se desactiva
  una cuenta con sesión previa, la siguiente petición se trata como anónima y va al
  login. El decorador también deniega una instancia autenticada marcada inactiva.
- Los campos ordinarios son username, first_name, last_name, rol e is_active.
  El alta añade contraseña y confirmación; se aplican los validadores de Django y
  se usa set_password. La edición no altera contraseña ni privilegios técnicos.
- Se rechazan formularios que envíen is_staff, is_superuser, groups,
  user_permissions, password u otros campos protegidos. Los servicios tienen
  parámetros explícitos y no realizan asignación masiva del POST.
- Se deniega editar o desactivar la cuenta propia, incluso a un superusuario.
  Ningún superusuario puede editarse desde estas pantallas, aunque el actor sea
  otro administrador. La comprobación se hace en GET, POST y en el servicio.
- Las cuentas ordinarias con is_staff existente mantienen ese valor y sus grupos
  técnicos al editar campos de negocio. No se conceden privilegios técnicos nuevos.
- Roles y permisos son de consulta: no hay rutas para crear, editar o eliminar
  roles, ni se modificaron los 12 permisos y la matriz inicial. El administrador
  técnico preexistente de fase 1 no fue modificado.
- En la matriz, `catalogo_permisos` contiene el catálogo y `filas` sus asignaciones;
  `permisos` conserva su significado global de códigos efectivos.
- No hay eliminación de usuarios ni restablecimiento ordinario de contraseña:
  no forman parte del alcance autorizado. Los usuarios sin rol se conservan como
  posibilidad del modelo existente, sin permisos de negocio.

## Archivos

Modificados:

- `backend/apps/core/permissions.py`.
- `backend/apps/core/context_processors.py`.
- `backend/apps/usuarios/views.py`.
- `backend/apps/usuarios/urls.py`.
- `frontend/templates/components/_menu.html`.
- `ESPECIFICACION_SISTEMA.md` y su copia idéntica en `docs/`.

Creados:

- `backend/apps/usuarios/forms.py`.
- `backend/apps/usuarios/services.py`.
- `backend/apps/usuarios/tests/test_fase2.py`.
- `frontend/templates/usuarios/usuario_lista.html`.
- `frontend/templates/usuarios/usuario_form.html`.
- `frontend/templates/usuarios/rol_lista.html`.
- Este informe.

No se modificaron modelos, migraciones, settings, .env, dependencias, bibliotecas
vendor ni las pruebas anteriores. Las referencias históricas de fases 0 y 1 se
complementaron con la confirmación de cierre proporcionada por el usuario.

## Pruebas ejecutadas

Intérprete utilizado exclusivamente: `venv/Scripts/python.exe`, Python 3.13.7.

| Comprobación | Resultado real |
|---|---|
| `manage.py check` | Código 0; sin incidencias. |
| `manage.py makemigrations --check --dry-run` | Código 0; No changes detected. |
| `manage.py test --noinput` | Código 0; **106 pruebas en 87,451 segundos, OK**. |
| `manage.py migrate --plan` | Código 0; No planned migration operations. Solo consulta. |
| `git diff --check` | Sin errores; advertencias de conversión LF/CRLF. |

La suite contiene las 81 pruebas anteriores y 25 nuevas, algunas con subcasos:

- Matriz de Dueño/Vendedor, superusuario activo, rol vacío, ausencia de rol,
  inactividad y anonimato; código inexistente denegado a usuario ordinario.
- GET/POST autorizados y denegados en las cuatro rutas; 403 en acceso directo.
- Alta con contraseña hash, rol correcto y ausencia de privilegios técnicos.
- Contraseñas cortas, comunes, diferentes o vacías; nombres inválidos/duplicados,
  rol inexistente y límites de campos.
- Edición, activación/desactivación, cambio de rol, usuario inexistente y POST vacío.
- Preservación de contraseña, grupos, permisos internos e is_staff preexistentes.
- POST de escalada rechazado en alta y edición sin persistir cambios.
- Cuentas propias y superusuarios protegidos en vistas y servicios.
- Matriz solo de consulta; POST rechazado y relaciones sin cambios.
- Menú, contexto, recursos locales y GET sin cambios en usuarios.
- Cambio de rol efectivo en la siguiente petición y denegación de sesión desactivada.
- CSRF en alta/edición: rechazo sin token y aceptación con token válido.
- Validación y autorización de servicios invocados directamente.

Las advertencias 403/405 emitidas por pruebas negativas existentes del administrador,
CSRF y logout son esperadas; no hubo pruebas fallidas. Las pruebas usan bases aisladas
de Django. Las regresiones previas que ejercitan migraciones lo hacen exclusivamente
en esa base de pruebas; no se ejecutó migrate sobre la base real.

## Conservación de datos y Git

Se compararon hashes SHA-256 de **36 archivos protegidos** antes y después:
base SQLite activa, .env, modelos, migraciones y los dos reportes locales.
**Todos permanecen iguales**. No se creó ningún usuario ni se ejecutó la carga
inicial sobre la base real. No se revelaron secretos ni credenciales.

Rama de trabajo: `main`; commit base `e72eb81`. No se cambió de rama ni se hicieron
commits o push. Se conservaron, sin modificar ni agregar a Git:

- `backend/REPORTE_MIGRACIONES_FASE1.md`.
- `backend/SOLUCION_ERROR_TERMINAL.md`.

Se verificaron exclusiones de .env, SQLite, venv, respaldos y logs. Las salidas
completas y evidencia de hashes quedan fuera del repositorio en:

`C:\Users\Jose\AppData\Local\Temp\Inventarios_fase2_ayhc_3uw`

Archivos: `check.txt`, `makemigrations.txt`, `test.txt`, `migrate_plan.txt`,
`protegidos.json` y `resultado_final.json`. El directorio temporal puede ser
limpiado por Windows; este informe versionable conserva el resumen de resultados.

## Verificación manual y límites

Desde la raíz:

```powershell
.\venv\Scripts\python.exe .\backend\manage.py check
.\venv\Scripts\python.exe .\backend\manage.py makemigrations --check --dry-run
.\venv\Scripts\python.exe .\backend\manage.py test --noinput
.\venv\Scripts\python.exe .\backend\manage.py runserver
```

Con un superusuario o Dueño existente, abrir `/usuarios/`, el formulario de alta y
`/usuarios/roles/`. Deben conservar el diseño base, mostrar los roles/permisos y
ocultar la edición de cuentas propias o superusuarios. Con Vendedor, el menú no
debe mostrar estas opciones y el acceso directo debe responder 403. Los formularios
de modificación manual deben probarse sobre una copia de pruebas, no con registros
del negocio. La suite automatizada ya ejercita las operaciones de escritura aisladas.

No se abrió un navegador gráfico ni una ventana WebView2 para inspeccionar estas
nuevas pantallas. Se verificaron HTTP, contenido renderizado y enlaces locales
mediante el cliente de pruebas; no se afirma una revisión visual manual. No hay
fallos automatizados ni funcionalidades obligatorias pendientes del alcance aprobado.
