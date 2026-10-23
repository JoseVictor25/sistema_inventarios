# Fase 0 — base temporal, autenticación y sincronización (2026-10-23)

**Estado: correcciones de backend/verificador comprobadas; recorrido visual completo
pendiente.** No se inició fase 1. No se hicieron commits, ni se modificaron .env o la
base del negocio. Todas las ejecuciones Python usaron `venv/Scripts/python.exe`.

## Diagnóstico a partir de la ejecución manual

Se revisó `docs/verificacion_fase0/manual/resultado.json`, aportado por el usuario:
login a 1280 cargó las cinco bibliotecas y hojas CSS; el siguiente resultado de
login mostraba `Server Error (500)`, sin CSS/JS y con ancho 1536 pese a solicitar 390.
El inicio sintético cargó, y hubo además un 404 de `/favicon.ico`.

La base anterior era SQLite `:memory:` sin migraciones. Cada conexión podía tener
su propia base vacía. Un POST real de login consulta usuarios_usuario, que no existía.
Las bibliotecas indefinidas sobre el documento 500 eran consecuencia de esa página
de error; no demostraban por sí mismas un defecto en los bundles locales.
El inicio previo era un fixture con usuario simulado, no una autenticación real.

El servidor previo atendía una sola conexión. Las conexiones anticipadas de Chromium
podían dejarlo esperando una petición y demorar otras solicitudes. Se corrigió esta
limitación, sin atribuirle todos los timeouts observados en la sesión del agente.

## Correcciones aplicadas

### Base de datos y autenticación

- Se crea un directorio temporal propio y `datos_prueba.sqlite3` dentro de él.
- Antes de migrar se comprueba que tanto settings como la conexión Django apuntan
  exactamente a ese archivo y que el motor configurado es SQLite. Si no, se rechaza.
- Se aplican las migraciones EXISTENTES únicamente a esa base temporal y se verifica
  mediante introspección la tabla `usuarios_usuario`.
- Solo entonces se crea `usuario_prueba`, con contraseña aleatoria por ejecución.
  La contraseña no se guarda en el JSON ni se imprime.
- No se lee .env: ENV_FILE apunta a un archivo inexistente del directorio temporal;
  clave de Django, datos, respaldos, logs y perfil WebView2 son exclusivos de la prueba.
- El servidor usa el mismo archivo SQLite. Las conexiones Django se cierran al terminar
  cada hilo; se cierran servidor y conexiones antes de limpiar la carpeta temporal.
- Se eliminó `/vista-inicio/` y el usuario simulado. Se usan login, inicio `/` y logout
  reales de Django, incluida la protección CSRF y las sesiones de la base temporal.

### Comprobación HTTP previa obligatoria

Antes de abrir la GUI se prueba por HTTP real en loopback:

1. El inicio anónimo redirige a login.
2. El formulario entrega CSRF y autentica al usuario temporal.
3. Inicio responde 200 y muestra `usuario_prueba`.
4. Nueve CSS/JS y el favicon responden 200 y coinciden byte a byte con sus fuentes.
5. Logout por POST redirige a login y una nueva petición a inicio vuelve a exigir sesión.
6. Una conexión anticipada sin petición no bloquea la otra conexión del cliente.

Si esto falla, el script no continúa a la GUI. Los estados y métodos HTTP se conservan
en `http_local`; los HTTP 404/500 impiden aprobar. No se ocultan esos errores.

### Servidor y sincronización del navegador

- Servidor WSGI con un hilo por conexión, SQLite compartido mediante archivo y timeout
  de cinco segundos para conexiones que no envían datos. Cierres/reset de transporte
  se registran separadamente en `avisos_transporte`; no se confunden con un HTTP 500.
- Se mantienen exclusivamente APIs públicas de pywebview; no hay COM/CoreWebView2/Invoke.
- Cada respuesta HTML lleva un identificador único de documento, instrumentación de
  errores JS/violaciones CSP y `Cache-Control: no-store`.
- El sondeo espera documento NUEVO, ruta esperada, readyState complete, las cinco
  bibliotecas definidas, reglas CSS aplicadas y los nueve scripts/estilos requeridos.
- También espera un ancho interior coherente con 1280 o 390; no acepta 1536 como 390.
- No usa un sleep fijo como señal de finalización. Reintenta mientras el puente JS
  cambia de documento, con límite de tiempo y cancelación al cerrar la ventana.
- Tras la pausa visual repite la inspección para detectar errores tardíos.
- El navegador recorre login a 1280/390, envía el formulario con el usuario temporal,
  recorre el inicio REAL a 1280/390 y finalmente comprueba logout y acceso denegado
  a inicio tras cerrar sesión. El usuario no debe escribir ni pulsar botones durante
  este recorrido automático.
- Se conserva CSP para bloquear recursos externos y el registro mediante eventos
  públicos y Performance API. Eso no pretende bloquear telemetría interna del motor.

### Favicon

Se añadió `frontend/static/img/favicon.svg` y su enlace local en base.html.
Esto elimina la solicitud implícita al favicon inexistente sin ocultar un 404 en
el verificador ni cambiar reglas o funcionalidades de negocio.

## Resultados reales de esta revisión

| Comprobación | Resultado |
|---|---|
| `manage.py check` | Sin incidencias |
| Suite Django final | **31 pruebas aprobadas**, 13.632 segundos |
| Integridad vendor | Correcta; bibliotecas y licencias sin modificar |
| collectstatic | 2 archivos copiados y 142 sin cambios |
| Verificador `--solo-http` | Código 0; `solo_http_aprobado: true`; sin errores |
| Tabla temporal | `usuarios_usuario` existe y fue verificada antes de crear el usuario |
| Login/inicio/logout HTTP real | Aprobados, con CSRF y sesión del usuario temporal |
| Recursos HTTP | Diez recursos locales correctos; ningún estado >=400 |
| Preconexión concurrente | Otra petición completó correctamente con la conexión anticipada abierta |
| Verificador gráfico | Código 1: no obtuvo documento inspeccionable en /login/ a 1280 |

La suite añadió cinco pruebas respecto a las 26 anteriores: rechazo de migración
fuera del directorio temporal, dimensión incorrecta, espera de documento nuevo y
bibliotecas, cancelación y prueba integral HTTP en un proceso independiente.
Esta última comprueba también la preconexión, el acceso real al archivo compartido,
la presencia de diez recursos y hashes intactos de .env y base del negocio.
Las migraciones del runner se aplicaron solo a su base de pruebas; el verificador
migró solo su archivo temporal. Ninguna migración se ejecutó sobre datos del negocio.
Los warnings de 403 sin CSRF y 405 al usar GET en logout son esperados por la suite.

Evidencia guardada:

- `docs/verificacion_fase0/base_temporal_http/resultado.json`: modo HTTP de la versión
  final; aprobado. `automatizacion_aprobada` permanece false deliberadamente porque
  `--solo-http` no verifica JavaScript ni renderizado.
- `docs/verificacion_fase0/base_temporal_visual/resultado.json`: intento gráfico tras
  corregir el servidor paralelo. La fase HTTP fue correcta; el sondeo del navegador
  agotó 20 segundos sin obtener documento. No se evaluaron las bibliotecas ni el diseño.
- Los resultados anteriores/manuales se conservan como historial, no como aprobación
  de la versión corregida.

En una ejecución gráfica anterior al cambio a servidor paralelo se observó un reset
WinError 10054 de una conexión. La ejecución con servidor paralelo no mostró ese
traceback. La nueva prueba de preconexión se añadió después y pasó en el modo HTTP
y en la suite completa; no se presenta como una aprobación visual adicional.

**No se observaron HTTP 404/500 en las comprobaciones corregidas realizadas. No se
completaron las cuatro páginas dentro de WebView2 en esta sesión.** La apertura básica
y el renderizado parcial que el usuario observó en Windows 11 se reconocen, pero
no sustituyen una ejecución completa con automatizacion_aprobada=true.

## Protección de datos y alcance

Se compararon hashes de .env y SQLite antes/después: permanecen intactos. Las licencias
y archivos vendor conservan su integridad. No se modificaron modelos, migraciones,
servicios de negocio ni reglas RN-01 a RN-21. No se creó el launcher de fase 10.

Archivos modificados/nuevos en esta corrección:

- `scripts/verificar_interfaz_fase0.py`.
- `backend/apps/core/tests/test_verificacion_interfaz.py`.
- `frontend/templates/base.html` y nuevo `frontend/static/img/favicon.svg`.
- `docs/FASE_0_RESULTADOS.md`.
- Los dos JSON de evidencia `base_temporal_http/` y `base_temporal_visual/`.
- Notas de estado e inventario en ambas copias de `ESPECIFICACION_SISTEMA.md`.
- Archivos recolectados, logs y cachés ignorados por Git, generados por las pruebas.

## Comando exacto para repetir en Windows 11

Desde la raíz del proyecto en PowerShell:

```powershell
.\venv\Scripts\python.exe scripts/preparar_frontend.py --verificar
.\venv\Scripts\python.exe backend/manage.py collectstatic --noinput
.\venv\Scripts\python.exe scripts/verificar_interfaz_fase0.py --visible --espera 60 --pausa 5 --salida docs/verificacion_fase0/manual_corregido
$LASTEXITCODE
```

Puede desconectarse internet antes de ejecutar. No introducir credenciales ni interactuar
con los formularios durante el recorrido: el script crea y utiliza su usuario temporal.
Debe verse login dos veces, un login automático, inicio dos veces y cierre de sesión;
la ventana cambia de tamaño y se cierra al finalizar. No se generan capturas PNG.

Resultado esperado: cuatro líneas de comprobaciones correctas, código 0, cuatro entradas
en `paginas`, `autenticacion_http.aprobada: true`, `autenticacion_navegador: true`,
`automatizacion_aprobada: true`, errores vacíos y ningún HTTP >=400 en el JSON nuevo.
Revisar además que formularios, estilos y menú sean legibles y no estén recortados.
Código 0 acredita automatización; la apariencia debe confirmarse humanamente.

Para aislar problemas sin abrir ventana:

```powershell
.\venv\Scripts\python.exe scripts/verificar_interfaz_fase0.py --solo-http --salida docs/verificacion_fase0/manual_http
```

En ese modo se espera `solo_http_aprobado: true`, pero NO automatizacion_aprobada=true.
Si el recorrido gráfico falla, conservar el JSON nuevo y la salida de consola.

**La fase 0 sigue pendiente del recorrido gráfico completo corregido y la revisión
visual. No se inicia la fase 1 sin autorización explícita.**
