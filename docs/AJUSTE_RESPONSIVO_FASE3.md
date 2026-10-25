# Ajustes Responsivos — Fase 3 (Catálogo y Proveedores)

Fecha: 2026-10-24
Entorno: Python 3.13.7 (`venv/Scripts/python.exe`), Django 5.x, Bootstrap 5.3.8 local.

---

## 1. Objetivo y contexto

Durante la revisión visual en resolución móvil (**390 × 844 píxeles**), se detectaron dos oportunidades de mejora en la interfaz:
1. **Productos (`/catalogo/productos/`):** El formulario de filtros y búsqueda ocupaba demasiado espacio vertical en la vista móvil, empujando la tabla de productos fuera del área visible inicial.
2. **Proveedores (`/compras/proveedores/`):** La tabla contaba con 7 columnas anchas en una sola fila, requiriendo desplazamiento horizontal para consultar datos y acceder al botón de edición.

El objetivo fue resolver ambos puntos optimizando la experiencia móvil sin alterar la visualización completa en escritorio (**1280 × 800 píxeles**), preservando la lógica de negocio, la seguridad y los recursos locales de Bootstrap y AdminLTE.

---

## 2. Cambios implementados

### 2.1. Plantilla de Productos (`frontend/templates/catalogo/producto_lista.html`)

- **Panel de filtros colapsable en móvil:**
  - Se implementó una cabecera interactiva colapsable visible exclusivamente en pantallas móviles (`d-md-none`) con los atributos Bootstrap `data-bs-toggle="collapse"`, `data-bs-target="#filtros-collapse"` y `aria-controls="filtros-collapse"`.
  - El contenedor `#filtros-collapse` utiliza las clases `collapse d-md-block`. En escritorio (`>= 768px`) permanece siempre visible y abierto gracias a `d-md-block`; en móviles inicia contraído para ahorrar más de 300 px verticales.
  - Si existen filtros aplicados (`request.GET.q`, `categoria`, `atributo` o `valor`), el panel añade automáticamente la clase `show` y muestra un distintivo visual `Activo`, garantizando que el usuario vea los criterios de búsqueda activos y el botón para limpiarlos.
- **Encabezado y acciones:**
  - Reorganización flex mediante `d-flex flex-column flex-sm-row flex-wrap justify-content-between align-items-start align-items-sm-center gap-2 mb-3`.
  - Botones de acción accesibles con IDs unívocos (`btn-ver-categorias`, `btn-crear-producto`, `btn-buscar-productos`, `btn-limpiar-filtros`).
- **Tabla adaptativa:**
  - La columna `Categoría` se oculta en teléfonos (`d-none d-sm-table-cell`) y se presenta como subtítulo estilizado bajo el nombre del producto (`d-sm-none text-muted small`), permitiendo que el listado quepa cómodamente en 390 px de ancho.
  - Distintivos consistentes para el estado (`Activo` en verde sutil, `Inactivo` en gris).

### 2.2. Plantilla de Proveedores (`frontend/templates/compras/proveedor_lista.html`)

- **Tabla responsiva de 7 columnas:**
  - **En escritorio (`>= 992px` / 1280 × 800):** Conserva la tabla completa con sus 7 columnas individuales: `Nombre`, `Tipo`, `Contacto`, `Teléfono`, `Origen`, `Estado` y `Acciones`.
  - **En móviles (`< 768px` / 390 × 844):** Se ocultan selectivamente las columnas secundarias (`d-none d-md-table-cell`, `d-none d-lg-table-cell`, `d-none d-sm-table-cell`).
  - La celda `Nombre` integra en móviles un bloque secundario estilizado (`d-md-none small mt-1`) que incluye:
    - Badges compactos de `Tipo` y `Estado`.
    - Datos de `Contacto` y `Teléfono` con separador legible.
    - Datos de `Origen` si están presentes.
- **Acciones y botones:**
  - Botón `Editar proveedor` siempre visible en su columna de acciones (`text-nowrap btn-sm`) sin requerir desplazamiento horizontal.
  - Botón `Crear proveedor` en la cabecera flex con ID único `#btn-crear-proveedor`.
  - Mensaje de tabla vacía preservado con `colspan="7"`.

---

## 3. Restricciones y reglas respetadas

| Restricción | Estado | Verificación |
|---|---|---|
| No modificar modelos ni migraciones | Cumplido | `git status` y `makemigrations --check` confirman cero cambios en esquemas. |
| No modificar permisos ni reglas de negocio | Cumplido | Decoradores, servicios y validaciones de `catalogo` y `compras` intactos. |
| No modificar `.env` ni la base real | Cumplido | Hashes de base real y `.env` no tocados; pruebas sobre bases temporales en RAM/Temp. |
| Mantener recursos locales (Bootstrap, AdminLTE) | Cumplido | No se añadieron CDNs ni URLs externas; clases estándar de Bootstrap 5. |
| No avanzar a fase 4 | Cumplido | No se crearon modelos, rutas ni vistas de compras/lotes de fase 4. |
| No realizar commits ni push | Cumplido | El árbol de trabajo permanece en desarrollo local sin commits. |

---

## 4. Resultados de validación técnica

### 4.1. Chequeo del sistema Django
```powershell
.\venv\Scripts\python.exe backend/manage.py check
```
- **Resultado:** Código 0. `System check identified no issues (0 silenced).`

### 4.2. Suite completa de pruebas automatizadas (147 pruebas)
```powershell
.\venv\Scripts\python.exe backend/manage.py test --noinput
```
- **Resultado:** Código 0. **Ran 147 tests in 71.773s — OK**.
- 100% de las pruebas anteriores (Fase 0, Fase 1, Fase 2 y Fase 3) continúan pasando satisfactoriamente.

### 4.3. Verificación HTTP aislada sobre SQLite temporal
```powershell
.\venv\Scripts\python.exe .\scripts\verificar_catalogo_fase3.py --http
```
- **Resultado:** Código 0.
- 11 pantallas comprobadas con HTTP 200 para Dueño.
- 11 recursos estáticos locales comprobados con integridad de bytes.
- Denegación estricta (HTTP 403) comprobada para Vendedor en todas las rutas administrativas de catálogo y proveedores.

---

## 5. Diferenciación de inspección visual vs. automatizada

- **Comprobación automatizada:** Certifica la sintaxis de plantillas, las respuestas HTTP, el renderizado de etiquetas, los contratos de permisos y la compatibilidad con los tests de Django.
- **Inspección visual real:** Debe validarse en el navegador con la bandera `--abrir`:
  ```powershell
  .\venv\Scripts\python.exe .\scripts\verificar_catalogo_fase3.py --abrir
  ```
  - Probar a **390 × 844**: desplegar el panel de filtros en productos, realizar búsquedas y consultar la tabla de proveedores sin scroll horizontal.
  - Probar a **1280 × 800**: confirmar que los filtros de productos se muestren abiertos por defecto y que la tabla de proveedores muestre sus 7 columnas completas.
