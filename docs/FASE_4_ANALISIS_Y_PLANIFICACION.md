# Fase 4: Compras y Lotes — Análisis Técnico y Planificación Exhaustiva



**Proyecto:** `sistema_inventarios`

**Fecha:** 2026-10-24

**Rama Git:** `main`

**Estado:** Análisis y planificación completados. Esperando autorización para implementar.

**Suite base:** 147 pruebas automatizadas aprobadas (100% éxito).



---



## 1. Objetivo Exacto de la Fase 4



El objetivo de la Fase 4 es implementar la gestión completa del flujo de compras e ingreso de mercadería al inventario, conforme a lo estipulado en `ESPECIFICACION_SISTEMA.md`:



1. **Servicio de registro de compras (`registrar_compra`)**:

   - Registrar la cabecera de la compra vinculada al proveedor y al usuario autenticado.

   - Registrar cada línea de compra (`DetalleCompra`) con su cantidad, costo unitario y subtotal.

   - Generar automáticamente **un lote por línea** (`Lote`), con código único en formato `L-AAAA-NNNN`, cantidades inicial y actual iguales, costo unitario y fecha de vencimiento opcional (**RN-05**).

   - Generar un movimiento de inventario inmutable de tipo `ENTRADA` por cada lote creado, con cantidad positiva igual a las unidades compradas y autoría del usuario (**RN-21**).

   - Calcular y persistir el monto total de la compra.

   - Ejecutar toda la operación bajo una única transacción atómica (`transaction.atomic()`). Ante cualquier error o inconsistencia, garantizar la reversión total (rollback).

   - Mantener la inmutabilidad de las compras: una compra registrada **no se edita ni se elimina** (**RN-19**).



2. **Módulo de interfaz y navegación (vistas y plantillas de §9.4)**:

   - **Lista de compras (`/compras/`)**: histórico de compras paginado con filtro de fechas (`desde`, `hasta`) y visualización de totales.

   - **Registro de nueva compra (`/compras/nueva/`)**: formulario con selector de proveedor activo, fecha, observación y detalle de líneas dinámicas.

   - **Línea de compra dinámica HTMX (`/compras/nueva/linea/`)**: adición de líneas en tiempo real mediante fragmentos HTMX (`_linea_compra.html`) sin recarga de página.

   - **Detalle de compra (`/compras/<int:pk>/`)**: consulta no editable de la compra, sus líneas, los lotes creados y los movimientos generados.

   - **Menú principal**: activar el enlace de Compras en la barra de navegación para usuarios con permiso `gestionar_compras`.



3. **Seguridad y permisos**:

   - Exigir el permiso `gestionar_compras` tanto en las vistas como en los servicios.

   - Proteger la visualización de costos unitarios y totales con el permiso `ver_costos` (**RN-20**).



---



## 2. Requisitos y Reglas de Negocio Aplicables



| Regla | Descripción | Aplicación en Fase 4 |

|---|---|---|

| **RN-01** | El stock siempre se cuenta en unidades. | En la compra se especifican `cantidad_unidades` (entero positivo ≥ 1). Cada unidad ingresada se suma directamente al stock en unidades. |

| **RN-05** | Cada compra genera **un lote por línea**, con fecha de vencimiento (opcional), cantidad y costo unitario. El stock es la suma de `cantidad_actual` de sus lotes. | Cada `DetalleCompra` se enlaza 1 a 1 con un `Lote`. Al crear el lote con `cantidad_inicial = cantidad_actual = N`, el stock del producto (`producto.stock_actual`) se incrementa automáticamente. |

| **RN-07** | No se venden unidades de lotes vencidos. | En el ingreso de compra no se permiten fechas de vencimiento en el pasado: si se especifica vencimiento, debe ser igual o posterior a la fecha actual (`vencimiento >= date.today()`). |

| **RN-17** | Productos inactivos no deben poder seleccionarse para nuevas compras. | Solo productos con `activo=True` están habilitados para compra. |

| **RN-19** | Las compras ya registradas **no se editan ni se eliminan**. | No existen vistas ni formularios de edición o borrado de `Compra` ni `DetalleCompra`. En el Admin se conserva `SoloLecturaAdminMixin` con `has_delete_permission = False` y `has_change_permission = False`. Los errores se resuelven posteriormente mediante ajustes de inventario (Fase 7). |

| **RN-20** | Solo el rol Dueño ve costos, ganancias y reportes. El Vendedor vende y cuadra su caja. | Las vistas de compras y el menú de compras están restringidos a `gestionar_compras`. Los montos de costo se condicionan a `ver_costos`. |

| **RN-21** | Todo dato importante guarda quién lo creó/modificó y cuándo. | `Compra` registra `usuario` y campos de `EntidadAuditable`. `MovimientoInventario` registra explícitamente `usuario` y `fecha`. |



---



## 3. Estado del Código: Existente vs. Pendiente



### 3.1 Lo que ya existe (Fases 1, 2 y 3)

- **Modelos de datos:**

  - `Proveedor`: implementado y con CRUD completo (Fase 3).

  - `Compra`: modelo creado con restricciones a nivel BD (`total_no_negativo`).

  - `DetalleCompra`: modelo creado con restricciones (`costo_no_negativo`, `subtotal_no_negativo`, `cantidad_minimo_1`).

  - `Lote`: modelo creado con restricciones (`costo_no_negativo`, `cantidad_inicial_minimo_1`, `cantidad_actual_no_supera_inicial`). Relación OneToOne con `DetalleCompra`.

  - `MovimientoInventario`: modelo creado con restricción (`cantidad_distinta_cero`).

- **Migraciones:**

  - Todas las tablas y restricciones ya están migradas (`0001_initial.py` y `0002_integridad_fase1.py` en `compras` e `inventario`). No se requieren nuevas migraciones.

- **Seguridad e infraestructura:**

  - `apps.core.operaciones`: decorador `@operacion(permiso)` que maneja autorización, `transaction.atomic()` y traducción de errores de integridad / bloqueo SQLite.

  - `apps.core.permissions`: decoradores `@permiso_requerido` y `tiene_permiso`.

  - `apps.core.validators`: funciones `validar_dinero` y `validar_cantidad`.

  - `frontend/templates/compras/`: ya contiene `proveedor_lista.html` y `proveedor_form.html`.



### 3.2 Lo que falta implementar en Fase 4

- **Backend:**

  - En `backend/apps/compras/services.py`:

    - Función de generación de código de lote correlativo `generar_codigo_lote(anio=None)`.

    - Función `registrar_compra(usuario, proveedor, lineas, observacion="", fecha=None)`.

  - En `backend/apps/compras/forms.py`:

    - `CompraForm`: cabecera (proveedor, fecha opcional, observación).

    - `DetalleCompraForm` o validación estructurada de líneas de compra recibidas en el POST.

  - En `backend/apps/compras/views.py`:

    - `compra_lista(request)`: vista de historial con paginación y filtros de fecha.

    - `compra_crear(request)`: vista GET/POST de nueva compra.

    - `compra_linea(request)`: endpoint HTMX para entregar parcial `_linea_compra.html`.

    - `compra_detalle(request, pk)`: vista de consulta de compra, detalles y lotes.

  - En `backend/apps/compras/urls.py`:

    - Rutas para las 4 vistas anteriores siguiendo los nombres de §9.4.

- **Frontend:**

  - `frontend/templates/compras/compra_lista.html`: tabla responsiva, buscador/filtro por rango de fechas, insignias de estado y paginador.

  - `frontend/templates/compras/compra_form.html`: selector de proveedor activo, campos de fecha y observación, contenedor `#lineas-compra` dinámico, botón de agregar línea con HTMX, totales calculados en vivo.

  - `frontend/templates/compras/partials/_linea_compra.html`: fila de producto con selector de producto activo, cantidad, costo unitario, fecha de vencimiento y botón de quitar fila.

  - `frontend/templates/compras/compra_detalle.html`: datos de la compra, lista de productos comprados, códigos de lote asignados y trazabilidad de movimientos.

  - `frontend/templates/components/_menu.html`: activar ítem "Compras" con enlace a `compras:compra_lista` condicionado a `gestionar_compras`.

  - `frontend/static/js/compras.js`: script complementario ligero para cálculo en vivo de subtotales y total en la pantalla del cliente y eliminación limpia de filas en el DOM.



---



## 4. Diseño del Flujo de Compras



```

  Usuario (Dueño)

        │

        ▼

  GET /compras/nueva/ ───▶ Presenta formulario (proveedor, fecha, obs)

        │

        ├──▶ Click "Agregar producto" (HTMX GET /compras/nueva/linea/?indice=N)

        │         └──▶ Inserta partial _linea_compra.html en #lineas-compra

        │

        ├──▶ Edita cantidad / costo ──▶ JS local actualiza subtotal y total

        │

        ▼

  POST /compras/nueva/

        │

        ▼

  Vista compra_crear

        │

        ▼

  Servicio registrar_compra (apps/compras/services.py)

        │

        ├─▶ [Paso 1] Validar permiso ("gestionar_compras") y proveedor activo

        ├─▶ [Paso 2] Validar líneas (≥1 línea, producto activo, cantidad ≥1, costo ≥0, vencimiento ≥ hoy)

        │

        ▼ transaction.atomic()

        ├─▶ [Paso 3] Crear Compra (proveedor, fecha, usuario, observacion)

        ├─▶ [Paso 4] Por cada línea:

        │       ├─ Calcular subtotal = cantidad * costo_unitario

        │       ├─ Crear DetalleCompra

        │       ├─ Generar codigo_lote único (ej. L-2026-0001)

        │       ├─ Crear Lote (producto, detalle_compra, cantidad_inicial, cantidad_actual, costo, vencimiento)

        │       └─ Crear MovimientoInventario (tipo=ENTRADA, cantidad=+cantidad, motivo, usuario)

        ├─▶ [Paso 5] Calcular total acumulado y persistir en Compra

        ├─▶ [Paso 6] Retornar Compra

        │

   (Éxito) ────▶ Redirección 302 a /compras/<id>/ con mensaje flash

   (Fallo) ────▶ Rollback total; renderiza compra_form.html con errores y código 200/422

```



---



## 5. Arquitectura de Servicios y Transacciones



### 5.1 Generación de Código de Lote (`generar_codigo_lote`)

- Formato: `L-AAAA-NNNN` (ej. `L-2026-0001`).

- Algoritmo:

  1. Obtener el año actual (o el año de la fecha de la compra).

  2. Filtrar `Lote.objects.filter(codigo_lote__startswith=f"L-{anio}-")`.

  3. Obtener el correlativo máximo persistido y sumar 1 (relleno a 4 dígitos con `zfill(4)`).

  4. Para evitar colisiones en compras concurrentes con múltiples líneas dentro de la misma transacción, el servicio llevará la cuenta de códigos generados en el lote actual y atrapará posibles violaciones de unicidad reintentando o bloqueando adecuadamente.



### 5.2 Estructura del Servicio `registrar_compra`

Siguiendo fielmente §8.3 y la convención `# Paso N`:



```python

@operacion("gestionar_compras")

def registrar_compra(usuario, proveedor, lineas, observacion="", fecha=None):

    """Registra una compra a un proveedor y genera sus lotes y movimientos.



    Pasos:

        1. Validar proveedor activo y que exista al menos una línea.

        2. Validar cada línea: producto activo, cantidad entera >= 1,

           costo >= 0 (validar_dinero) y vencimiento vacío o >= hoy.

        3. Crear la Compra en la base de datos.

        4. Por cada línea: crear DetalleCompra, crear Lote (código L-AAAA-NNNN)

           y crear MovimientoInventario de tipo ENTRADA (+cantidad).

        5. Calcular y guardar el total de la compra.

        6. Devolver la Compra.

    """

```



### 5.3 Manejo de Transacciones e Integridad en SQLite

- **Reversión completa:** La operación se decora con `@operacion("gestionar_compras")`. Si cualquier línea falla (ej. producto inactivo, costo negativo, error de base de datos), Django ejecuta rollback de la transacción atómica. Ningún registro huérfano de `Compra`, `DetalleCompra`, `Lote` o `MovimientoInventario` permanece en la base de datos.

- **Concurrencia en SQLite:** SQLite serializa las escrituras. `@operacion` ya captura `OperationalError` ("database is locked") y lo traduce a `ErrorDeNegocio` con mensaje amigable para reintentar.



---



## 6. Modelos y Relaciones (Sin migraciones nuevas)



```

[Proveedor] 1 ─────── N [Compra] (on_delete=PROTECT)

                          │ 1

                          │

                          ▼ N (on_delete=CASCADE)

[Producto]  1 ─────── N [DetalleCompra] (on_delete=PROTECT)

    │                     │ 1

    │                     │

    │ (PROTECT)           ▼ 1 (on_delete=PROTECT)

    └───────────────▶ [Lote] (OneToOne con DetalleCompra)

                          │ 1

                          │

                          ▼ N (on_delete=PROTECT)

                      [MovimientoInventario] (tipo='ENTRADA', cantidad=+N)

```



- `Compra.total`: `CheckConstraint(total >= 0)`.

- `DetalleCompra.costo_unitario`: `CheckConstraint(costo_unitario >= 0)`.

- `DetalleCompra.subtotal`: `CheckConstraint(subtotal >= 0)`.

- `DetalleCompra.cantidad_unidades`: `CheckConstraint(cantidad_unidades >= 1)`.

- `Lote.codigo_lote`: `unique=True`.

- `Lote.cantidad_inicial`: `CheckConstraint(cantidad_inicial >= 1)`.

- `Lote.cantidad_actual`: `CheckConstraint(cantidad_actual <= cantidad_inicial)`.

- `MovimientoInventario.cantidad`: `CheckConstraint(cantidad != 0)`.



---



## 7. Formularios y Pantallas



### 7.1 Pantallas y Contratos de URL (§9.4)



| Pantalla | URL | `name` | Plantilla / Parcial | Contexto |

|---|---|---|---|---|

| Lista de compras | `/compras/?desde=&hasta=` | `compras:compra_lista` | `compras/compra_lista.html` | `page_obj`, `desde`, `hasta`, `total_filtrado` |

| Nueva compra | `/compras/nueva/` | `compras:compra_crear` | `compras/compra_form.html` | `form`, `proveedores`, `productos` |

| Agregar línea (HTMX) | `GET /compras/nueva/linea/` | `compras:compra_linea` | `compras/partials/_linea_compra.html` | `indice`, `productos` |

| Detalle de compra | `/compras/<int:pk>/` | `compras:compra_detalle` | `compras/compra_detalle.html` | `compra`, `detalles`, `lotes` |



### 7.2 Diseño Responsivo (1280x800 escritorio y 390x844 móvil)

- **Lista de compras:**

  - Escritorio: tabla completa con ID, Fecha, Proveedor, Items, Total, Usuario y botón Detalle.

  - Móvil: tarjetas colapsadas o tabla con `table-responsive`, ocultando columnas secundarias (ej. Usuario) y priorizando Fecha, Proveedor y Total.

- **Formulario de nueva compra:**

  - Controles táctiles amplios, selector de fecha amigable.

  - Botón "Agregar producto" destacado.

  - Cada línea de producto cuenta con un botón "Eliminar línea" accesible.

  - Subtotales y total flotante o visible en cabecera/pie.

- **Detalle de compra:**

  - Tarjeta de resumen con metadatos clave (Proveedor, Fecha, Registrado por, Total).

  - Tabla de detalle con cada producto, cantidad comprada, costo unitario, subtotal, código de lote asignado y fecha de vencimiento.



---



## 8. Permisos y Seguridad



1. **Permiso `gestionar_compras`:**

   - Requerido para acceder a cualquier vista de compras (`compra_lista`, `compra_crear`, `compra_linea`, `compra_detalle`).

   - Verificado mediante `@permiso_requerido("gestionar_compras")` en vistas y `@operacion("gestionar_compras")` en servicios.

   - Si un usuario no autorizado intenta ingresar, recibe HTTP 403 con mensaje de permiso denegado.

2. **Permiso `ver_costos`:**

   - En las plantillas, las columnas de "Costo unitario" y "Total" se condicionan a `{% if "ver_costos" in permisos %}`.

   - Si no tuviera `ver_costos`, se muestran guiones o se oculta la columna monetaria.

3. **Protección CSRF:**

   - Todos los formularios POST y solicitudes HTMX incluyen `{% csrf_token %}` o header `X-CSRFToken`.



---



## 9. Plan de Implementación Paso a Paso



Una vez recibida la autorización del usuario:



1. **Paso 1: Servicios de Compras (`apps/compras/services.py`)**

   - Implementar `generar_codigo_lote(anio=None)`.

   - Implementar `registrar_compra(usuario, proveedor, lineas, observacion="", fecha=None)`.

   - Agregar pruebas unitarias exhaustivas del servicio (casos positivos y casos negativos de validación y rollback).

2. **Paso 2: Formularios de Compras (`apps/compras/forms.py`)**

   - Crear `CompraCabeceraForm` para validar proveedor activo, fecha y observación.

   - Definir esquema de validación de líneas de compra.

3. **Paso 3: Vistas y URLs (`apps/compras/views.py`, `apps/compras/urls.py`)**

   - Implementar `compra_lista`, `compra_crear`, `compra_linea` y `compra_detalle`.

   - Registrar las URLs correspondientes en `compras/urls.py`.

4. **Paso 4: Plantillas y Frontend (`frontend/templates/compras/`)**

   - Crear `compra_lista.html`, `compra_form.html`, `partials/_linea_compra.html`, `compra_detalle.html`.

   - Actualizar `frontend/templates/components/_menu.html` para habilitar el enlace a Compras.

   - Añadir script `compras.js` para manipulación ágil de líneas en el DOM y totales en cliente.

5. **Paso 5: Pruebas Automatizadas y Verificación**

   - Escribir suite `backend/apps/compras/tests/test_fase4.py` cubriendo modelos, servicios, vistas, HTTP, permisos y regresión.

   - Crear script de verificación aislado `scripts/verificar_compras_fase4.py` (siguiendo el estándar de Fase 3).

   - Validar que las 147 pruebas anteriores sigan pasando y que las nuevas pruebas de Fase 4 pasen al 100%.

6. **Paso 6: Verificación Visual e Informe de Cierre**

   - Inspeccionar la interfaz a 1280x800 y 390x844 en entorno aislado.

   - Generar el informe final de Fase 4 sin tocar datos reales ni `.env`.



---



## 10. Plan de Pruebas y Criterios de Aceptación



### 10.1 Casos de Prueba del Servicio `registrar_compra`

- **Caso correcto básico:** Compra con 1 línea, sin vencimiento. Verifica creación de `Compra`, `DetalleCompra`, `Lote` (`L-AAAA-0001`, `cantidad_actual == cantidad_inicial`), `MovimientoInventario` (tipo `ENTRADA`, cantidad positiva) y aumento en `producto.stock_actual`.

- **Caso correcto múltiple:** Compra con 3 líneas distintas, vencimientos futuros, cálculo correcto del total de la compra.

- **Caso correlativo de lotes:** Compras sucesivas generan `L-2026-0001`, `L-2026-0002`, etc.

- **Validación - Proveedor inactivo:** Rechazo con `ErrorDeNegocio`.

- **Validación - Sin líneas:** Lista de líneas vacía rechazada con `ErrorDeNegocio`.

- **Validación - Producto inactivo:** Rechazo con `ErrorDeNegocio`.

- **Validación - Cantidad cero o negativa:** Rechazo con `ErrorDeNegocio`.

- **Validación - Costo negativo:** Rechazo con `ErrorDeNegocio`.

- **Validación - Vencimiento pasado:** Fecha anterior a hoy rechazada con `ErrorDeNegocio`.

- **Prueba de Atomicidad / Rollback:** Si la última línea falla, no se crea `Compra`, ni `DetalleCompra`, ni `Lote`, ni `MovimientoInventario` (comprobación `count() == 0`).

- **Seguridad en servicio:** Llamada directa sin permiso `gestionar_compras` lanza `PermissionDenied`.



### 10.2 Casos de Prueba HTTP y Vistas

- `GET /compras/`: 200 para Dueño, 403 para Vendedor, 302 para usuario anónimo.

- `GET /compras/nueva/`: 200 para Dueño, 403 para Vendedor.

- `GET /compras/nueva/linea/`: 200 y renderiza partial con nuevo índice.

- `POST /compras/nueva/`:

  - Datos válidos: 302 a `compras:compra_detalle` y mensaje de éxito.

  - Datos inválidos: 200 con formulario y errores visibles.

- `GET /compras/<id>/`: 200 para Dueño, 404 para compra inexistente, 403 para Vendedor.

- Filtro por fecha: `/compras/?desde=2026-01-01&hasta=2026-12-31`.



### 10.3 Criterios de Aceptación

1. 100% de pruebas aprobadas (147 de fases anteriores + pruebas nuevas de fase 4).

2. Cero migraciones nuevas requeridas (`makemigrations --check` limpio).

3. `manage.py check` con cero advertencias.

4. Base de datos real y `.env` intactos (hashes SHA-256 inalterados).

5. Trazabilidad completa: Compra -> Detalle -> Lote -> MovimientoInventario.

6. Ninguna pantalla de compras permite modificar o eliminar registros existentes.



---



## 11. Riesgos y Decisiones Técnicas Registradas



1. **Unicidad de `codigo_lote` en concurrencia:**

   - La base de datos tiene `unique=True` en `codigo_lote`.

   - Se utilizará numeración correlativa anual formateada a 4 dígitos (`L-AAAA-0001`). En caso de concurrencia, el bloqueo de transacción SQLite y la verificación de existencia previenen duplicados.

2. **Productos repetidos en la misma compra:**

   - Un usuario puede comprar el mismo producto en dos líneas si tienen lotes/vencimientos distintos o costos distintos. El servicio creará dos `DetalleCompra` y dos `Lote` independientes, lo cual respeta RN-05 ("un lote por línea") y es correcto para el almacén.

3. **Inmutabilidad estricta (RN-19):**

   - No se implementarán vistas ni botones de editar/eliminar compras. En la interfaz se dejará claro que una vez guardada, la compra queda asentada de forma definitiva.



---



*Fin del documento de análisis y planificación de la Fase 4.*
