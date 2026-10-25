# Fase 3 — Catálogo

Fecha: 2026-10-24. Funcionalidades implementadas; cierre visual pendiente.
Las comprobaciones finales se registran abajo. No se inició la fase 4.

## Decisiones de implementación y riesgos registrados antes de los cambios

- Catálogo administrativo exige `gestionar_catalogo`; proveedores exige
  `gestionar_compras`. No se modifica la matriz del Vendedor. Los costos requieren
  además `ver_costos`, incluso cuando se accede al detalle del producto.
- El Admin actual permite cambios de precio sin bitácora y altas de productos sin
  presentaciones. Para mantener un único camino transaccional, catálogo y proveedores
  quedarán de consulta en el Admin técnico; sus altas y cambios se realizan en las
  pantallas ordinarias. Se reutiliza la protección de consulta de fase 1. Es un
  cambio de acceso administrativo, no de datos ni del esquema. Se conservará la
  consulta técnica y se probarán POST directos e inlines.
- Edición de atributos: se añade GET/POST
  `/catalogo/productos/<pk>/atributos/<atributo_pk>/editar/`, nombre
  `catalogo:atributo_editar`, formulario propio. La relación producto se comprueba
  en servidor y no es editable. No se ofrecen borrados.
- Filtro por atributo: una pareja opcional `atributo`/`valor`, ambos exactos y
  aplicados al mismo atributo. Complementa `q` (código/nombre) y `categoria`
  (categoría exacta, sin expansión implícita a descendientes). No se añade un
  lenguaje de filtros ni una nueva dependencia.
- Se conserva una categoría inactiva al editar un producto ya asociado; para
  crear o cambiar de categoría se exige destino activo. Desactivar una categoría
  no modifica descendientes ni productos. Se permite que las presentaciones
  existentes estén inactivas: RN-03 exige existencia, no una presentación activa.
- Presentaciones se editan en el formset del producto, sin borrar ni trasladar.
  Todo cambio de precio pasa por `cambiar_precio`, incluido el formset.
- `mover_categoria` añade el argumento obligatorio por nombre `usuario`, necesario
  para comprobar autorización también en servicios. No existe consumidor anterior.
- `Categoria.clean()` se endurecerá con nodos visitados para detectar ciclos
  preexistentes sin bucles; no cambia campos ni requiere migración.
- La auditoría mínima de precios es dependencia explícita de §15, no implementa
  la pantalla de bitácora de fase 9 ni operaciones de fase 4.

## Funcionalidades implementadas

- Árbol de categorías con una consulta, alta, edición, cambio de padre, validación
  de ciclos y unicidad. Categorías inactivas sin cambios en cascada.
- Productos con búsqueda por código/nombre, categoría exacta, atributo/valor,
  paginación, alta atómica con presentaciones, edición, detalle y desactivación.
- Presentaciones con equivalencia y precio propios, alta HTMX y edición mediante
  formset. No se permite omitir, borrar, duplicar IDs ni trasladar presentaciones.
- Cambio de precio centralizado, auditado y transaccional; valor anterior releído
  de la base. El mismo precio no produce un cambio ficticio. Ventas intactas.
- Atributos: alta HTMX, edición ordinaria, unicidad por producto y relación fija.
- Proveedores: lista, alta y edición con ambos tipos y estado activo/inactivo;
  autoría conservada y actualizada. No se registran compras.
- Detalle con stock calculado y lotes existentes; costos solo con `ver_costos`.
- Formularios y servicios con campos permitidos; autorización en vistas y servicios,
  CSRF, errores de negocio y respuesta HTMX 422. Los destinos HTML se conservan.
- Navegación de catálogo/proveedores según permisos, recursos locales, tarjetas,
  tablas desplazables y formularios con Bootstrap/AdminLTE.

## Archivos nuevos

- `backend/apps/core/operaciones.py`: autorización, transacciones, traducción de
  errores de integridad y bloqueo SQLite, asignación explícita de campos.
- `backend/apps/catalogo/forms.py`.
- `backend/apps/catalogo/tests/test_fase3.py`.
- `backend/apps/compras/forms.py`.
- `frontend/templates/catalogo/categoria_lista.html` y `categoria_form.html`.
- `frontend/templates/catalogo/producto_lista.html`, `producto_form.html` y
  `producto_detalle.html`.
- `frontend/templates/catalogo/atributo_form.html`.
- `frontend/templates/catalogo/partials/_arbol.html`, `_presentaciones.html` y
  `_atributos.html`.
- `frontend/templates/compras/proveedor_lista.html` y `proveedor_form.html`.
- `frontend/templates/components/_paginacion.html`.
- `frontend/static/js/catalogo.js`: añadir filas al formset sin calcular dinero.
- `scripts/verificar_catalogo_fase3.py`: suite, HTTP y servidor manual aislados.
- Este informe.

## Archivos modificados

- `backend/apps/catalogo/models.py`: únicamente defensa de `Categoria.clean()`
  ante ciclos y relaciones cacheadas; sin cambios de campos o esquema.
- `backend/apps/catalogo/services.py`, `views.py`, `urls.py`, `admin.py`.
- `backend/apps/compras/services.py`, `views.py`, `urls.py`, `admin.py`.
- `backend/apps/auditoria/services.py`: registro mínimo de cambios sensibles.
- `frontend/templates/components/_menu.html`.
- `ESPECIFICACION_SISTEMA.md` y su copia idéntica `docs/ESPECIFICACION_SISTEMA.md`:
  contratos de atributos, filtros, servicios, contextos y protección administrativa.
- `docs/FASE_2_RESULTADOS.md`: nota de cierre confirmado por el usuario, conservando
  resultados y límites históricos.

## Integridad, permisos y migraciones

RN-02/03/04: presentaciones únicas, cantidades positivas y alta conjunta; no se
impone «Unidad». RN-08/17: precios aplicados y relaciones históricas conservados,
desactivación sin eliminación. RN-18: ancestros persistidos y detección de nodos
visitados, también ante un ciclo preexistente ajeno. RN-21: autoría de producto,
presentación y proveedor; bitácora de precio con usuario, fecha y valores.

No se modificó la matriz inicial ni los 12 permisos. Dueño y superusuario activo
pueden gestionar; Vendedor y usuarios sin rol reciben 403. Anónimos y sesiones de
usuarios inactivos van al login. La autorización se prueba también invocando los
servicios directamente. Admin conserva consulta y deniega altas/cambios/borrados.

No se generaron migraciones ni se modificaron migraciones anteriores. Las
migraciones usadas para pruebas y recorrido HTTP se aplican solo a archivos
temporales creados por el verificador. No se ejecutó migrate sobre la base real.

## Resultados reales de comprobaciones automatizadas

Todas las ejecuciones usaron `venv/Scripts/python.exe`. Configuración y SQLite
de pruebas fuera del repositorio; ningún comando utilizó la base del negocio.

| Comprobación final | Resultado |
|---|---|
| `manage.py check` | Código 0, sin incidencias |
| `manage.py makemigrations --check --dry-run` | Código 0, `No changes detected` |
| `manage.py test --noinput`, desde `backend` | **147 pruebas en 101,302 s, OK** |
| `scripts/preparar_frontend.py --verificar` | Código 0, integridad local correcta |
| Recorrido HTTP real sobre SQLite temporal | 39 solicitudes: 26 HTTP 200, 2 HTTP 302, 11 HTTP 403 esperados |
| Pantallas de consulta/edición | Once páginas cargadas por Dueño y denegadas al Vendedor |
| Recursos locales HTTP | Once archivos, contenido idéntico al origen; incluye `js/catalogo.js` |
| HTTP 404/500 en recorrido real | Ninguno |
| `git diff --check` | Sin errores; advertencias LF/CRLF |

La suite incluye las 106 pruebas anteriores y 41 nuevas. Cubre categorías y ciclos,
alta atómica, rechazo de precios/equivalencias inválidos, integridad SQL, formsets
manipulados, auditoría y rollback, historial de ventas, atributos, proveedores,
permisos en servicios/GET/POST, CSRF, HTTP/HTMX, paginación, costos restringidos,
Admin solo consulta y dos pruebas con conexiones SQLite independientes:
actualizaciones concurrentes con cadena de auditoría coherente y bloqueo real sin
cambios parciales. Los 403/404/405/422 de los casos negativos son deliberados.

Durante el desarrollo, una prueba detectó que `Categoria.clean()` usaba relaciones
cacheadas: se corrigió para recorrer IDs persistidos. Una primera invocación de
la suite desde la raíz descubrió cero pruebas: se descartó como evidencia y el
verificador se corrigió para trabajar desde `backend` y rechazar ese resultado.
La ejecución final de 147 pruebas es la válida; no hay pruebas fallidas pendientes.

Evidencia final:
`C:\Users\Jose\AppData\Local\Temp\Inventarios_verificacion_fase3_08642vtb`
(`check.txt`, `makemigrations.txt`, `test.txt`, `frontend.txt`, `resultados.json`,
`http.json`). Los archivos temporales pueden ser limpiados por Windows; este
informe conserva el resumen.

## Conservación de datos y Git

Se compararon SHA-256 de `backend/.env`, `backend/datos/db.sqlite3` y los reportes
`backend/REPORTE_MIGRACIONES_FASE1.md` y `backend/SOLUCION_ERROR_TERMINAL.md`:
todos permanecen iguales. No se imprimieron contenidos de `.env` ni datos reales.
Los reportes siguen sin seguimiento. Rama `main`; no se hicieron commits ni push.
Se comprobaron exclusiones Git de `.env`, SQLite, `venv`, respaldos y logs.

Hashes y sonda de navegador conservados en:
`C:\Users\Jose\AppData\Local\Temp\Inventarios_fase3_cecb59cf501b4cd385c9e5c6b42c948a`.

## Comprobaciones visuales y límites

No se aprobaron inspecciones visuales. La sonda de Edge sobre `about:blank`, con
perfil temporal y captura a 1280x800, terminó con código 2147483651, sin imagen.
El registro contiene fallos de acceso al registro/cifrado y del proceso GPU.
No se pudo revisar ninguna pantalla renderizada ni comprobar ejecución JavaScript
en escritorio o móvil. No se afirma ausencia de solicitudes dinámicas externas.

El HTML servido no incluye referencias HTTP/HTTPS externas y los recursos locales
se verifican byte a byte. Esto no sustituye la inspección del navegador.

## Repetición segura desde PowerShell

Desde la raíz, usando exclusivamente el entorno virtual:

```powershell
.\venv\Scripts\python.exe .\scripts\verificar_catalogo_fase3.py --pruebas --http
.\venv\Scripts\python.exe .\scripts\verificar_catalogo_fase3.py --abrir
```

Cada ejecución crea una carpeta nueva en TEMP y muestra su ubicación. Nunca lee
`.env`. Define explícitamente DB_PATH y, para la suite, TEST.NAME hacia archivos
SQLite de esa carpeta. La suite se ejecuta desde `backend` para descubrir todas
las aplicaciones. La ejecución con cero pruebas se considera fallo.

`--abrir` prepara datos sintéticos, comprueba HTTP y abre el navegador. Muestra
la URL, los usuarios temporales `dueno_fase3`/`vendedor_fase3` y su contraseña
aleatoria; no son cuentas reales. Ctrl+C detiene el servidor. La carpeta temporal
se conserva como evidencia y no se sobrescriben ejecuciones anteriores.

Revisión manual pendiente:

1. Ingresar como Dueño; comprobar listado y árbol, crear/mover categorías.
2. Crear producto con varias presentaciones, editarlo y probar rechazo de precio
   negativo, equivalencia cero y datos duplicados.
3. Abrir detalle, agregar presentación/atributo, editar atributo y cambiar precio.
   Confirmar actualizaciones HTMX y mensajes de error visibles sin perder el panel.
4. Buscar por código/nombre, categoría y atributo/valor. Revisar paginación.
5. Desactivar el producto y verificar que detalle, presentaciones e historial
   permanezcan disponibles. Probar alta/edición de proveedores.
6. Repetir las pantallas a 1280x800 y 390x844; comprobar menú, etiquetas, botones,
   errores, desplazamiento de tablas y ausencia de contenido cortado.
7. En DevTools revisar Console/Network con internet desconectado: ningún recurso
   local faltante, HTTP 500, error JavaScript ni solicitud remota de la interfaz.
8. Salir e ingresar como Vendedor: menú administrativo oculto y 403 en URL directa
   de catálogo/proveedores. No usar la base ni cuentas del negocio para estas pruebas.

## Estado de aceptación

Implementación funcional preparada para revisión. El cierre completo de fase 3
queda pendiente de la inspección visual y de JavaScript en un navegador operativo.
No se declara aprobada esa inspección ni se habilita trabajo de fase 4.
