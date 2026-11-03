# Fase 10 — Bloque A experimental

Actualización posterior: Bloque A versionado en `7e848e8`. La infraestructura
preliminar del Bloque B, etapa B2, se documenta en `FASE_10_B2_RESULTADOS.md`.
B3 y B4 no están implementadas; el instalador B2 bloquea toda instalación.

Actualización de referencia definitiva: ver `FASE_10_REFERENCIA_VISUAL.md`.
La navegación ahora es lateral, permanente en escritorio y Offcanvas en móvil;
el detalle de auditoría es un panel derecho. Esta actualización sustituye la
propuesta horizontal anterior. El usuario aprobó visualmente navegación, Inicio,
Bitácora y el ajuste final del POS el 01/11/2026.

Revisión posterior de navegación y bitácora (28/10/2026): ver
`FASE_10_NAVEGACION_BITACORA.md`. El intento automatizado histórico de WebView2
terminó por timeout; la aprobación visual posterior procede del usuario, no de
ese intento automatizado.

Base: `main`, commit `42cb939`. Sin instalación, tareas programadas, migraciones
de datos reales, commits ni push. La aprobación visual no acredita por sí sola
descargas Excel/PDF desde WebView2 ni ejecución en un Windows limpio.

## Implementación

El cierre técnico actualizado del 01/11/2026 y el inventario Git están al final
de este documento. Los resultados de compilaciones anteriores se conservan como
historial; no identifican el paquete vigente.

- `desktop/rutas.py`: recursos separados de datos; rutas absolutas en subcarpetas
  de TEMP, rechazo de ProgramData, repositorio y enlaces de directorio.
- `desktop/inicializacion.py`: configuración exclusiva, SECRET_KEY aleatoria,
  SQLite nueva solo con autorización, migraciones y datos iniciales exclusivamente
  en instalación nueva. Existentes incompletas o con esquema pendiente no arrancan.
- `backend/config/settings/escritorio.py`: producción, templates y estáticos del
  paquete, WhiteNoise sin depender de los finders de desarrollo.
- `core/primer_uso.py`, ruta en `core/urls.py` y plantilla: código local aleatorio,
  CSRF, validación en formulario y servicio, transacción, Dueño sin privilegios
  técnicos. Código invalidado después del alta. La exclusión de instancia del
  launcher y el cerrojo de peticiones protegen el alta concurrente; no se pretende
  que ese cerrojo sustituya un bloqueo entre procesos independientes no autorizados.
- `desktop/servidor.py`: socket ligado a 127.0.0.1 antes de entregarlo a Waitress;
  alternativa reservada cuando el puerto está ocupado. Espera HTTP acotada,
  cierre de trabajadores, canales y socket.
- `desktop/launcher.py`: instancia única por instalación, modo gráfico por API
  pública en hilo principal, navegador alternativo y cierre por ENTER en consola.
  `--respaldo` invoca el motor de fase 9 sin servidor ni ventana; puede respaldar
  un esquema pendiente sin aplicar migraciones. `--diagnostico` prueba HTTP y
  recursos del paquete sin interfaz gráfica.
- `desktop/sistema.spec`: onedir, recursos explícitos, módulos dinámicos de apps,
  migraciones y dependencias; sin carpetas de datos ni documentos privados.
- `scripts/compilar_fase10.py`: collectstatic aislado y compilación en TEMP.
  Se incorporó construcción limpia y caché propia para impedir código congelado
  obsoleto y separar las futuras cachés de compilación.
- `scripts/verificar_fase10.py`, `prueba_desktop_fase10.py` y pruebas Django:
  regresión, HTTP, dos procesos consecutivos, persistencia, puertos, respaldos,
  primer Dueño concurrente e inspección del paquete.
- `desktop/README.md` y ambas especificaciones documentan los contratos aprobados.

## Política de datos y seguridad

Todo uso experimental exige `--datos-temporales RUTA_ABSOLUTA`. No se habilita
automáticamente ProgramData. Una identidad Windows y herencia de permisos del
perfil temporal; ACL de instalación definitiva quedan para Bloque B. No se
concedieron permisos a todos los usuarios ni se modificaron ACL reales.

La SQLite, `.env`, respaldos y logs se mantienen fuera del ejecutable. No se
incluyen contraseñas predeterminadas. El código de primer uso se muestra solo
en la consola local; no viaja en URL ni se escribe en los logs de arranque.
Una base existente sin configuración no se trata como instalación nueva.
Las actualizaciones de bases existentes requieren un procedimiento separado.

## Pruebas y evidencias

Primera suite: 350 pruebas aprobadas en 332,398 segundos, check y migraciones sin
incidencias, HTTP de reportes/exportaciones y auditoría/respaldos aprobados.
Evidencia: `Inventarios_fase10_eu_j3ula` en TEMP.

Waitress y producción: dos procesos consecutivos aprobaron inicialización,
conservación de SECRET_KEY, Dueño, login, pantallas, recursos y respaldos; puerto
ocupado resuelto, hilo terminado y puerto liberado. Repetición con dos solicitudes
simultáneas de primer Dueño: una aceptada, otra 403, segundo arranque sin habilitar
de nuevo el alta. Evidencia: `Inventarios_fase10_lvtsv86w`.

Instalación ficticia con migraciones pendientes: arranque rechazado y hash de la
SQLite conservado (`Inventarios_esquema_fase10_jlslimtu`). Base ficticia sin `.env`:
rechazada sin sobrescribir ni generar configuración (`Inventarios_incompleta_fase10_jcfzi6tj`).

El primer paquete fue construido pero no aprobado: una modificación durante la
compilación dejó versiones mezcladas de módulos. La reconstrucción incremental
no corrigió ese artefacto. Se preparó construcción limpia con fuentes estabilizadas;
no distribuir el paquete inicial `Inventarios_build_fase10__7rpwmkm`.

### Resultado histórico anterior a las correcciones visuales

- **352 pruebas aprobadas en 226,690 segundos**, check sin incidencias y
  `makemigrations --check --dry-run` sin cambios. Evidencia final:
  `C:\Users\Jose\AppData\Local\Temp\Inventarios_fase10_960swnc0`.
- La ejecución intermedia de 352 pruebas tuvo un error de importación en la prueba
  de rutas de escritorio; se corrigió y se repitió la suite completa indicada arriba.
- HTTP de reportes: ocho reportes y dieciséis exportaciones, utilizando el recorrido
  de fase 8. HTTP de fase 9: 30 solicitudes y recuperación íntegra de 33 tablas.
- Integridad de recursos locales comprobada mediante `preparar_frontend.py --verificar`.
- El ejecutable limpio necesitó declarar WhiteNoise como import dinámico. Después
  de corregir el `.spec`, la construcción final pasó sus tres pruebas: instalación
  temporal nueva, segundo arranque y modo respaldo. **Esto valida únicamente el
  diagnóstico HTTP y respaldo del ejecutable, no su interfaz WebView2.**
- Paquete final experimental:
  `C:\Users\Jose\AppData\Local\Temp\Inventarios_build_fase10_i_w9afln\dist\SistemaInventarios`.
- Inspección: 4661 archivos, 74165457 bytes. Sin SQLite, `.env`, logs ni nombres
  de los informes privados. Evidencias del ejecutable:
  `C:\Users\Jose\AppData\Local\Temp\Inventarios_fase10_zs9fpkf2`.
- Los cuatro hashes finales coinciden con los iniciales de la tabla de este informe.
  No se abrió la base real para operaciones de datos.
- Las primeras compilaciones usaron la caché predeterminada de PyInstaller; el
  script final y la última compilación sitúan también la caché en TEMP.

El inventario Git de esa ejecución quedó superado por las correcciones visuales.
Los dos reportes privados anteriores permanecen sin seguimiento.

## Revisión reproducible

Desde la raíz del proyecto:

```powershell
.\venv\Scripts\python.exe scripts/verificar_fase10.py --pruebas --http --escritorio
.\venv\Scripts\python.exe scripts/verificar_fase10.py --abrir
.\venv\Scripts\python.exe scripts/compilar_fase10.py
.\venv\Scripts\python.exe scripts/verificar_fase10.py --paquete "RUTA_TEMP\dist\SistemaInventarios"
```

En `--abrir`, introducir el código impreso en consola y elegir credenciales.
Comprobar login/logout, pantallas principales y guardar Excel/PDF en una carpeta
temporal. Revisar 1280×800 y 390×844, sin internet. Cerrar la ventana y comprobar
la salida del proceso. Si se usa el navegador, ENTER en la consola cierra el
servidor; cerrar una pestaña no lo apaga. No hay controles HTTP de apagado.

## Límites y Bloque B

- La validación HTTP no acredita renderizado, WebView2 ni descarga mediante la GUI.
- Pendiente prueba en Windows limpio sin Python, antivirus y fallos de WebView2.
- Consola deliberadamente visible para autorización inicial y salida local.
- Falta endurecer/documentar el comportamiento de cierre ante solicitudes que
  excedan el plazo de drenaje y verificar descargas en la ventana. La navegación
  fue aprobada visualmente por el usuario el 01/11/2026.
- No hay cambios de modelos ni migraciones nuevas. Las migraciones previas de la
  base real siguen sin aplicar.
- Bloque B requiere autorización: Inno Setup, identidad/icono/términos aprobados,
  ACL de ProgramData para una identidad, accesos directos, WebView2 offline,
  tarea diaria, actualización y desinstalación conservando datos; pruebas en VM.
- No instalar ni distribuir los paquetes experimentales al cliente.

## Archivos protegidos

Hashes iniciales registrados sin abrir datos del negocio:

| Archivo | SHA-256 |
|---|---|
| `backend/datos/db.sqlite3` | `40D61B7947251655E3AF6055FAB58130D29A24586B103AA62FF4D5B847E37F50` |
| `backend/.env` | `9BC65E53962E9CD7849EB41F2899DFA29D230DF7DCB217831793CA76BE8FC854` |
| `backend/REPORTE_MIGRACIONES_FASE1.md` | `B5239FC7F134851BF32225F7363604D500449538690C2658A101105C7C257E53` |
| `backend/SOLUCION_ERROR_TERMINAL.md` | `8D907AD4BD5AB07E2F3799033A21E83C9A77AA7095E4C6CF520709D5E1EFAE26` |

## Cierre técnico actualizado — 01/11/2026

**Resultado: cierre técnico solicitado del Bloque A aprobado; pendiente de revisión
de resultados por el usuario y autorización de versionado. Bloque B no iniciado.**

- Suite completa: **359 pruebas aprobadas en 361,945 segundos**, una sola ejecución.
- Django `check`: sin incidencias.
- `makemigrations --check --dry-run`: `No changes detected`.
- Dos ejecuciones del launcher desde fuente: correctas, con persistencia de
  configuración/usuario, autenticación, recursos, pantallas, respaldo, puerto
  alternativo y cierre del servidor. La denegación 403 de la segunda solicitud
  concurrente de primer Dueño es el resultado esperado de esa prueba.
- Comando ejecutado: `venv/Scripts/python.exe scripts/verificar_fase10.py --pruebas --escritorio`.
- Evidencia: `%TEMP%\Inventarios_fase10_0j4twcgy` (`test.txt`, `check.txt`,
  `migraciones.txt`, `resultados.json`).

El usuario aprobó visualmente navegación lateral, Inicio, Bitácora y POS con
desplazamiento natural. Este cierre no cambia código funcional: actualiza
evidencias y documentación y reconstruye el artefacto con los cambios aprobados.
No se inició el Bloque B; no hay instalador, tareas Windows ni operaciones sobre
la SQLite real. Las descargas desde WebView2 y Windows limpio no se deducen de
la aprobación visual de esas pantallas ni del diagnóstico HTTP.

### Paquete vigente y persistencia

- Construcción limpia PyInstaller 6.22.3, Python 3.13.7, modalidad onedir:
  `C:\Users\Jose\AppData\Local\Temp\Inventarios_build_fase10_zk0de9fg\dist\SistemaInventarios`.
- Inspección: 4662 archivos, 74184934 bytes. Sin SQLite, `.env`, logs ni los dos
  documentos privados. No se instaló ni distribuyó al cliente.
- SHA-256 de `SistemaInventarios.exe`:
  `123dd9ca292c22cdeddf42ebbb9aa5634e61fb4bb68441f93a1a3dd8476c29f3`.
- Primer arranque nuevo, segundo arranque y `--respaldo`: código 0.
  Evidencia: `%TEMP%\Inventarios_fase10_uarm0hjf\resultados.json`.
- Dos ejecuciones adicionales del ejecutable sobre la instalación ficticia que
  ya contiene un Dueño: hashes de SQLite y configuración conservados, registros
  de las 34 tablas idénticos. El respaldo generado desde el EXE coincide con
  todas esas tablas, incluidos registros internos de SQLite; `integrity_check`
  correcto y `foreign_key_check` sin incidencias.
  Evidencia: `%TEMP%\Inventarios_fase10_0j4twcgy\instalacion\cierre_persistencia.json`.
- SHA-256 del respaldo ficticio de persistencia:
  `8de85a5b2cae81b6b7b6f0934e95eca8c3864f4db030b609698c51410eb7c436`.
- Avisos de hooks: raíz Django no inferida automáticamente e imports opcionales
  de pycparser/Oracle no encontrados. El spec explicita aplicaciones y recursos;
  las pruebas del paquete SQLite terminaron correctamente. No se modificaron
  dependencias para eliminar avisos de componentes no utilizados.

### Recursos actualizados y protección

- `preparar_frontend.py --verificar`: integridad correcta.
- 22 archivos de `frontend/static`, 21 recursos servibles en la copia recopilada
  y 66 plantillas coinciden byte por byte con el código fuente final. El marcador
  `.gitkeep` se omite por collectstatic; no es un recurso servido.
- CSS SHA-256: `2d6406238f7efb0c5e6c427ff9e68ae85f611cf01e21c8931041dc7556c7c215`.
- JS compartido SHA-256: `a3160691a9369f3a66eb086842443a42b1498adb3444cdf94523677a0b16c2b2`.
- Manifiesto de comparación: `%TEMP%\Inventarios_build_fase10_zk0de9fg\recursos_verificados.json`.
- Los cuatro hashes protegidos coinciden antes/después con la tabla anterior.
  No se abrió la base real para operaciones de datos ni se aplicaron migraciones.
- Ambas especificaciones son idénticas. Git ignora SQLite, `.env` y venv;
  los dos documentos privados siguen sin seguimiento y no deben incluirse.

### Repetir el diagnóstico del paquete

```powershell
.\venv\Scripts\python.exe scripts/verificar_fase10.py --paquete "$env:TEMP\Inventarios_build_fase10_zk0de9fg\dist\SistemaInventarios"
```

Este comando crea datos ficticios nuevos en TEMP. La carpeta onedir completa es
necesaria; no se debe copiar únicamente el EXE. TEMP puede limpiarse por Windows:
no es una ubicación de distribución o conservación definitiva del artefacto.


## Inventario Git al cierre

Rama `main`, HEAD `42cb939`. 36 archivos con seguimiento modificados y 23 sin seguimiento.
Los dos informes privados de fase 1 estan incluidos en ese recuento, pero deben permanecer sin seguimiento.
Sin staging, commit, push, ramas ni etiquetas nuevas. No se alteraron archivos funcionales en este cierre; solo estos tres informes de fase 10.

```text
 M ESPECIFICACION_SISTEMA.md
 M backend/apps/auditoria/services.py
 M backend/apps/core/context_processors.py
 M backend/apps/core/frontend.py
 M backend/apps/core/tests/test_fase0.py
 M backend/apps/core/tests/test_verificacion_interfaz.py
 M backend/apps/core/urls.py
 M desktop/README.md
 M docs/ESPECIFICACION_SISTEMA.md
 M frontend/static/css/app.css
 M frontend/static/js/app.js
 M frontend/templates/auditoria/lista.html
 M frontend/templates/base.html
 M frontend/templates/catalogo/partials/_presentaciones.html
 M frontend/templates/components/_mensajes.html
 M frontend/templates/components/_menu.html
 M frontend/templates/compras/compra_detalle.html
 M frontend/templates/compras/compra_form.html
 M frontend/templates/compras/compra_lista.html
 M frontend/templates/core/respaldos.html
 M frontend/templates/inicio.html
 M frontend/templates/inventario/_lotes_tabla.html
 M frontend/templates/inventario/_stock_tabla.html
 M frontend/templates/inventario/movimiento_lista.html
 M frontend/templates/reportes/_reporte.html
 M frontend/templates/ventas/partials/_carrito.html
 M frontend/templates/ventas/partials/_lista_productos.html
 M frontend/templates/ventas/pos.html
 M frontend/templates/ventas/venta_detalle.html
 M frontend/templates/ventas/venta_lista.html
 M scripts/verificar_caja_fase5.py
 M scripts/verificar_catalogo_fase3.py
 M scripts/verificar_compras_fase4.py
 M scripts/verificar_interfaz_fase0.py
 M scripts/verificar_usuarios_fase2.py
 M scripts/verificar_ventas_fase6.py
?? backend/REPORTE_MIGRACIONES_FASE1.md
?? backend/SOLUCION_ERROR_TERMINAL.md
?? backend/apps/auditoria/presentacion.py
?? backend/apps/core/primer_uso.py
?? backend/apps/core/tests/test_fase10.py
?? backend/apps/core/tests/test_navegacion_lateral.py
?? backend/apps/core/tests/test_presentacion_auditoria.py
?? backend/config/settings/escritorio.py
?? desktop/inicializacion.py
?? desktop/launcher.py
?? desktop/rutas.py
?? desktop/servidor.py
?? desktop/sistema.spec
?? docs/FASE_10_NAVEGACION_BITACORA.md
?? docs/FASE_10_REFERENCIA_VISUAL.md
?? docs/FASE_10_RESULTADOS.md
?? "docs/referencias/Panel de inventario Mi Tienda.png"
?? frontend/templates/components/_icono.html
?? frontend/templates/core/primer_uso.html
?? scripts/compilar_fase10.py
?? scripts/prueba_desktop_fase10.py
?? scripts/revisar_navegacion_fase10.py
?? scripts/verificar_fase10.py
```
