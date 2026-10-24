# Verificación funcional y visual final — Fase 2

Fecha: 2026-10-24.

**Verificación funcional HTTP aprobada. Inspección visual NO aprobada: pendiente
de ejecutar y revisar en una sesión de Windows que pueda abrir el navegador.**
No se cierra la verificación visual de fase 2 con evidencia exclusivamente HTTP.

## Ejecución y aislamiento

Se revisaron la especificación y el informe de fase 2. Se añadió
`scripts/verificar_usuarios_fase2.py`, un verificador independiente del launcher.
Se ejecutó exclusivamente con `venv/Scripts/python.exe`.

El script crea una carpeta temporal y configura DB_PATH, DATA_DIR, LOG_DIR,
BACKUP_DIR y un ENV_FILE inexistente antes de iniciar Django. Migra únicamente
`datos_prueba.sqlite3`, verificando que la configuración y la conexión apuntan a
ese archivo temporal mediante el guardado existente del verificador de fase 0.
No carga ni escribe .env. Los usuarios y sesiones son nuevos y temporales.

Se inicia un servidor WSGI real en 127.0.0.1 con puerto libre. Las comprobaciones
usan peticiones HTTP, cookies, login y POST con CSRF, no solo el cliente de tests
de Django. Al finalizar se detiene el servidor y se elimina únicamente su propia
carpeta temporal. El resultado JSON se conserva en el directorio de salida.

Los hashes de la base local `backend/datos/db.sqlite3`, `.env` y los dos reportes
locales sin seguimiento coinciden antes/después. No se modificaron datos reales,
modelos, migraciones ni funcionalidades del negocio. No hubo commits ni push.

## Resultados funcionales realmente ejecutados

| Comprobación | Resultado |
|---|---|
| Resolución de rutas y nombres de §9.2 | Coinciden las cuatro rutas y sus nombres. |
| Anónimo | Las cuatro rutas redirigen al login. |
| Dueño | Listado, alta, edición y matriz responden 200; menú de usuarios/roles presente. |
| Alta | POST real crea usuario temporal, contraseña hash y rol Vendedor, sin is_staff. |
| Edición | Cambia nombre y asigna rol Dueño, conservando la identidad del registro. |
| Desactivación | Usuario temporal queda inactivo y su login es rechazado. |
| Reactivación | Vuelve a activo, se asigna Vendedor y el login funciona. |
| Matriz | Presenta los 12 códigos de permisos y los dos roles existentes. |
| Menú del Vendedor | No contiene enlaces a usuarios ni roles. |
| URL directa como Vendedor | 403 en GET y POST de listado, alta, edición y matriz; POST con CSRF válido. |
| Recursos locales | Diez archivos servidos con 200 y contenido idéntico al original. |
| Manifiesto frontend | `preparar_frontend.py --verificar`: integridad correcta. |

Total del recorrido: **52 peticiones**, distribuidas en **34 respuestas 200,
10 redirecciones 302 y 8 rechazos 403 esperados**. Cero respuestas 404 o 500.
El resultado fue `funcional_aprobado: true`, `errores: []` y
`protegidos_sin_cambios: true`.

Rutas comprobadas:

- `/usuarios/` → `usuarios:lista`.
- `/usuarios/nuevo/` → `usuarios:usuario_crear`.
- `/usuarios/<pk>/editar/` → `usuarios:usuario_editar`.
- `/usuarios/roles/` → `usuarios:rol_lista`.

La referencia a AdminLTE está presente en las cuatro páginas. Se sirvieron
AdminLTE, Bootstrap, HTMX, Chart.js, Tom Select, CSS/JS propios y favicon. Las
licencias y bibliotecas no se modificaron. No hay referencias HTTP/HTTPS externas
en el HTML inspeccionado. **Esto no acredita la ejecución de JavaScript ni la
ausencia de solicitudes externas dinámicas**, que requieren un navegador.

No se repitió la suite completa de 106 pruebas en esta revisión: su resultado
corresponde a la implementación anterior. La nueva evidencia es el recorrido
HTTP real del verificador y la comprobación del manifiesto.

## Intentos visuales y limitaciones reales

Se localizaron Edge y Chrome instalados y se intentó iniciar su renderizado
headless con perfiles nuevos y aislados, sin tocar los perfiles habituales:

1. Edge terminó con código 2147483651 y errores de cifrado/acceso del entorno.
2. Chrome terminó con código 2147483651; registró acceso denegado 0x80070005 y
   fallo fatal de inicialización del proceso GPU.
3. Un segundo intento de Chrome con GPU en el propio proceso agotó 20 segundos
   sin devolver un documento.

Ningún intento consiguió cargar siquiera la página de prueba `about:blank`.
**No se abrió ni inspeccionó ninguna pantalla de usuarios/roles en el navegador;
no se generaron ni revisaron capturas.** No se evaluaron visualmente ni escritorio
ni móvil y no se ejecutó el JavaScript del frontend. Estos errores ocurrieron
antes de acceder a la aplicación y no demuestran un defecto de sus plantillas.

No se identificó una corrección funcional necesaria en el recorrido HTTP. No se
modificó CSS ni HTML basándose en una apariencia que no pudo observarse. Quedan
por comprobar el ajuste del menú, las tablas, los formularios, los mensajes y
los recursos dinámicos en escritorio y móvil.

## Repetición manual segura en PowerShell

Desde la raíz del proyecto:

```powershell
$salidaFase2 = Join-Path $env:TEMP ("RevisionFase2_" + [guid]::NewGuid().ToString("N"))
.\venv\Scripts\python.exe .\scripts\verificar_usuarios_fase2.py --salida $salidaFase2 --abrir
```

El script primero repite las comprobaciones HTTP. Después abre el navegador y
muestra la URL local, las cuentas **dueno_visual** y **vendedor_visual**, y una
contraseña temporal compartida generada para esa ejecución. Son cuentas de la
base temporal, no credenciales del negocio. El servidor permanece activo hasta
Ctrl+C; al cerrarlo se guarda `resultado_http_fase2.json` en `$salidaFase2`.

Para repetir únicamente HTTP, omitir `--abrir`. Cada ejecución debe usar una
carpeta de salida distinta; no se sobrescriben resultados anteriores.

Revisión requerida antes de aprobar la parte visual:

1. Ingresar como dueno_visual. Abrir listado, alta, edición de `alta_visual` y
   matriz. Revisar las cuatro pantallas a **1280 × 800** y **390 × 844** mediante
   la barra de dispositivos de DevTools. Comprobar legibilidad, botones accesibles,
   ausencia de superposición y que el desplazamiento horizontal de tablas, si lo
   necesitan, quede dentro de su contenedor.
2. Crear otro usuario temporal, editarlo, cambiar su rol y desactivarlo/reactivarlo.
   Revisar mensajes de éxito y validación, sin usar cuentas del negocio.
3. Salir e ingresar como vendedor_visual. No deben aparecer usuarios/roles en
   el menú; escribir sus URLs directamente debe mostrar acceso restringido.
4. Abrir Console y Network en DevTools, limpiar el registro y recargar cada
   pantalla. No debe haber errores JavaScript, 404/500 ni recursos externos de
   aplicación. Los 403 deliberados de Vendedor son correctos. Las solicitudes
   propias deben corresponder al mismo origen 127.0.0.1 y puerto temporal.
5. Verificar en Console que `typeof bootstrap`, `typeof adminlte`, `typeof htmx`,
   `typeof Chart` y `typeof TomSelect` no devuelvan `"undefined"`.
6. Repetir la navegación con Internet desconectado manteniendo localhost disponible.
   Guardar capturas de las cuatro pantallas en ambos tamaños y registrar errores
   o aprobación humana por separado. El JSON nunca marca por sí solo aprobación visual.

Evidencia de esta ejecución:

`C:\Users\Jose\AppData\Local\Temp\Inventarios_visual_fase2__pj5elrg\resultado_http_fase2.json`

En la misma carpeta se conservan los registros de los intentos de Chrome. Al
estar en Temp, no constituye archivo permanente; este informe conserva los
resultados esenciales.
