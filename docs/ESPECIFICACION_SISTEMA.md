# Sistema de inventarios y ventas — Especificación completa

Tienda de productos naturales (Bolivia). Programa de escritorio hecho con Django (backend) y HTML con plantilla (frontend), empaquetado en un instalador de Windows.

> Este documento es la guía única del proyecto: qué contiene el sistema, qué reglas cumple, cómo se escribe el código y **en qué archivo vive cada cosa**, para que backend y frontend se conecten sin perder tiempo buscando.

## Cómo usar este documento (instrucciones para el agente de IA)

Este documento es la **fuente de verdad** del proyecto. Debe bastar para construir el sistema sin hacer preguntas básicas.

**Punto de partida.** Ya existe un esqueleto probado (`sistema_inventarios_esqueleto.zip`): proyecto Django en `backend/`, plantillas en `frontend/`, configuración con `.env`, usuario personalizado y las 9 apps vacías. Lo marcado con ✔ en la sección 4 ya existe; lo marcado con ☐ hay que crearlo.

**Cómo arrancar el proyecto (Windows):**

```
python -m venv venv
venv\Scripts\activate
pip install -r backend\requirements.txt
cd backend
copy .env.example .env          (completar SECRET_KEY en .env)
python manage.py migrate
python manage.py runserver
```

**Reglas de trabajo**

1. **Una fase a la vez**, en el orden de la sección 14. Al terminar cada una: `python manage.py check`, `python manage.py test` y revisar que todo pase antes de seguir.
2. **No inventar reglas de negocio.** Si algo que afecta al negocio no está en este documento, se pregunta o se propone una opción y se anota en la sección 15 como decisión pendiente.
3. **No salirse del alcance** (secciones 1 y 15): nada de facturas, clientes, anulaciones, devoluciones ni versión móvil.
4. **Seguir los estándares de la sección 6:** capas separadas, validación en tres niveles, `ErrorDeNegocio`, docstring con `Pasos:` y comentarios `# Paso N`.
5. **Los nombres de la sección 9 son un contrato:** URLs, `name`, archivos de plantilla, IDs HTML y variables de contexto no se renombran sin actualizar el documento en el mismo cambio.
6. **Toda configuración en el `.env`** (sección 5). Ningún secreto ni ruta fija en el código.
7. **Dinero siempre con `Decimal`**, nunca `float`. Fechas con zona horaria.
8. **Sin CDN:** todas las librerías del frontend se guardan en `frontend/static/vendor/` (el sistema funciona sin internet).
9. **Idioma:** nombres del dominio (modelos, campos, funciones, URLs) en español sin tildes ni eñes; textos de pantalla y mensajes en español de Bolivia, moneda `Bs`.
10. **Pruebas** para cada servicio, con los casos mínimos de la sección 12.
11. **Mantener este documento al día:** cada modelo, pantalla o variable nueva se refleja en la sección correspondiente (4, 5, 7, 8 o 9) en el mismo cambio.

**Valores por defecto para lo que sigue pendiente** (para no frenar el trabajo; el usuario puede cambiarlos después):

| Pendiente | Valor por defecto |
|---|---|
| Lotes vencidos | No se venden (RN-07) |
| Cierre de caja | No es "a ciegas": el efectivo esperado se muestra siempre |
| Plantilla del frontend | AdminLTE (versión basada en Bootstrap 5) hasta que el usuario elija otra. La integración sigue la sección 9.12 |
| Moneda y valores del negocio | `Bs`, 30 días de alerta, stock mínimo 5 |

**Qué entregar al terminar cada fase:** lista de archivos creados o modificados, cómo probar lo hecho y qué pruebas pasaron. Después se espera la confirmación del usuario antes de pasar a la siguiente fase.

**Primer mensaje sugerido para el agente:**

> Lee completo `docs/ESPECIFICACION_SISTEMA.md`, el diagrama `docs/diagrama_clases_inventario_v4.mermaid` y abre los mockups de `docs/mockups/`. Trabaja una fase del plan (sección 14) a la vez, empezando por la Fase 0 y la Fase 1: crear `core/exceptions.py`, `core/validators.py` y `core/permissions.py`, los `models.py` de todas las apps según la sección 7 (con los tipos exactos de 7.10), las migraciones, el `admin.py` y el comando `cargar_datos_iniciales`. Sigue los estándares de la sección 6 y no agregues funciones fuera de alcance. Al terminar, muestra los archivos creados, cómo probarlo y qué pruebas pasaron, y espera mi confirmación antes de pasar a la siguiente fase.

---

## Índice

1. [Resumen y alcance](#1-resumen-y-alcance)
2. [Reglas de negocio](#2-reglas-de-negocio)
3. [Tecnología y versiones](#3-tecnología-y-versiones)
4. [Estructura de carpetas](#4-estructura-de-carpetas)
5. [Variables de entorno (.env)](#5-variables-de-entorno-env)
6. [Estándares de código del backend](#6-estándares-de-código-del-backend)
7. [Modelos (datos) por app](#7-modelos-datos-por-app)
8. [Servicios paso a paso](#8-servicios-paso-a-paso)
9. [Mapa backend ↔ frontend](#9-mapa-backend--frontend)
10. [Roles y permisos](#10-roles-y-permisos)
11. [Reportes y exportación](#11-reportes-y-exportación)
12. [Respaldos, registros y pruebas](#12-respaldos-registros-y-pruebas)
13. [Empaquetado y entrega](#13-empaquetado-y-entrega)
14. [Plan de trabajo](#14-plan-de-trabajo)
15. [Decisiones pendientes y fuera de alcance](#15-decisiones-pendientes-y-fuera-de-alcance)

---

## 1. Resumen y alcance

**Cliente:** tienda que vende productos naturales: pomadas, jarabes (riñones, hígado graso, etc.), aceites vegetales y animales, suplementos (colágeno, espirulina), velas aromáticas, nuez moscada y más. Muchos productos, con categorías y subcategorías.

**Objetivo:** saber con exactitud cuántas unidades hay de cada producto, a qué precio se compró y a qué precio se vende, controlar vencimientos, cuadrar la caja cada día y ver las ventas por día, semana y mes.

### El sistema incluye

| Módulo | Qué hace |
|---|---|
| Catálogo | Categorías con subcategorías, productos, presentaciones con precio, atributos para filtrar (origen, aroma, etc.) |
| Compras | Proveedores (empresas y compras propias a otro departamento), compras con lotes y vencimiento |
| Inventario | Stock por producto (suma de lotes), alertas de stock bajo y de productos por vencer, ajustes y mermas, historial de movimientos |
| Ventas | Pantalla de venta rápida (POS): buscar producto, elegir presentación, cobrar con uno o varios métodos de pago |
| Caja | Apertura de turno, movimientos de efectivo, cierre con diferencia (sobra / falta / cuadra) |
| Reportes | Ventas, compras, inventario valorizado y ganancias, con filtros y exportación a Excel y PDF |
| Usuarios | Usuarios con roles (dueño, vendedor) y permisos |
| Auditoría | Registro de quién creó o modificó cada dato y bitácora de cambios sensibles |
| Sistema | Respaldo automático y manual de la base de datos |

### Fuera de alcance (por ahora)

Facturas y recibos (el negocio vende sin comprobante), clientes registrados y crédito/fiado, anulaciones y devoluciones, flete en el costo de compra, versión móvil o en la nube. Pueden agregarse después sin romper lo existente (ver sección 15).

---

## 2. Reglas de negocio

Cada regla tiene un código (RN-xx). Los servicios del backend y las pruebas hacen referencia a ellos.

| Código | Regla |
|---|---|
| RN-01 | **El stock siempre se cuenta en unidades.** Una venta de 2 docenas descuenta 24 unidades. |
| RN-02 | Un producto tiene **una o más presentaciones** (unidad, cuarta = 3, media docena = 6, docena = 12, caja = N). Cada una tiene sus unidades equivalentes y su precio de venta propio. El nombre de la presentación no se repite dentro de un mismo producto. |
| RN-03 | Todo producto tiene al menos una presentación (normalmente "Unidad", equivalencia 1). |
| RN-04 | La cantidad de unidades de una "caja" **es distinta por producto**; por eso se guarda en cada presentación, no es un valor global. |
| RN-05 | Cada compra genera **un lote por línea**, con fecha de vencimiento (opcional), cantidad y costo unitario. El stock de un producto es la suma de `cantidad_actual` de sus lotes. |
| RN-06 | Las ventas descuentan primero del lote que **vence antes** (FEFO). Los lotes sin vencimiento se usan al final. |
| RN-07 | **No se venden unidades de lotes vencidos.** Se retiran con un ajuste de tipo MERMA. *(Confirmar con el cliente.)* |
| RN-08 | El **precio de venta aplicado** se guarda en cada línea de venta; si el precio cambia después, las ventas pasadas no se alteran. |
| RN-09 | El **costo** de lo vendido se obtiene del lote del que salió cada unidad (tabla `DetalleVentaLote`). Ganancia = precio aplicado − costo del lote. |
| RN-10 | **No se puede vender sin una caja abierta** por el usuario que vende. |
| RN-11 | Cada usuario tiene **una sola caja abierta** a la vez. |
| RN-12 | Efectivo esperado en caja = monto inicial + ventas en efectivo + ingresos − egresos. QR y transferencias **no** entran al conteo de efectivo. |
| RN-13 | Diferencia de caja = efectivo contado − efectivo esperado (0 = cuadra, positiva = sobra, negativa = falta). Una caja cerrada no se puede reabrir ni editar. |
| RN-14 | Una venta puede pagarse con **uno o varios métodos**; la suma de los pagos debe ser igual al total. Solo el efectivo admite vuelto. |
| RN-15 | Las ventas son **al paso**: no hay clientes registrados ni comprobantes. |
| RN-16 | Alerta de **stock bajo** cuando el stock del producto es menor o igual a su stock mínimo. Alerta de **por vencer** cuando un lote con stock vence dentro de `DIAS_ALERTA_VENCIMIENTO` días. |
| RN-17 | Un producto con historial **no se elimina**: se desactiva (`activo = False`) y deja de aparecer en la venta. |
| RN-18 | Una categoría no puede ser su propia ancestra (no se permiten ciclos en la jerarquía). |
| RN-19 | Las compras y ventas ya registradas **no se editan**. Los errores se corrigen con un ajuste de inventario (queda en la bitácora). |
| RN-20 | Solo el rol **dueño** ve costos, ganancias, reportes y bitácora. El **vendedor** vende y cuadra su caja. |
| RN-21 | Todo dato importante guarda quién lo creó/modificó y cuándo (`EntidadAuditable`). Los cambios de precio, ajustes de stock y cierres de caja además quedan en `LogAuditoria` con el valor anterior y el nuevo. |

---

## 3. Tecnología y versiones

**Estado de preparación (2026-10-22):** fase 0 pendiente únicamente de cierre
visual y verificación de ejecución de escritorio. Todas las comprobaciones de
esta revisión usaron `venv/Scripts/python.exe`: Python 3.13.7, Django 5.2.18,
pywebview 6.2.1, pythonnet 3.2.1 y PyInstaller 6.22.3. `pip check`, imports,
`manage.py check` y 31 pruebas pasaron. El usuario confirmó apertura
básica de WebView2 en su equipo. El verificador corregido usa solo APIs públicas
y prepara un archivo SQLite temporal migrado, con usuario y autenticación reales.
Login/inicio/logout y diez recursos HTTP pasaron; el recorrido WebView2 aún no
se completó en la sesión del agente (timeout sin documento inspeccionable).
La revisión visual y JavaScript del frontend sigue pendiente. Ver `docs/FASE_0_RESULTADOS.md`.
No se ha iniciado la fase 1.

Recursos locales instalados y verificados contra su manifiesto: AdminLTE 4.0.2,
Bootstrap 5.3.8, HTMX 2.0.8, Chart.js 4.5.1 y Tom Select 2.4.3. Licencias locales
conservadas: MIT, 0BSD y Apache-2.0 según cada distribución. El registro de fuentes
e integridad está en `frontend/static/vendor/manifest.json`. La validación visual
y de JavaScript sin internet continúa pendiente; no se marca fase 0 como terminada.

| Pieza | Elección | Nota |
|---|---|---|
| Lenguaje | Python 3.12 (recomendado), 3.11 o 3.13 | Windows 10 y 11 de 64 bits. Con 3.13, probar `pip install -r backend\requirements-desktop.txt` desde la Fase 0, porque `pywebview` depende de `pythonnet` y conviene confirmar temprano que instala bien |
| Framework | Django 5.2 LTS | Soporte largo; compatible con Python 3.10–3.13 |
| Base de datos | SQLite | Una sola laptop; archivo en `ProgramData` |
| Variables de entorno | `python-dotenv` | Lee el archivo `.env` |
| Archivos estáticos | `whitenoise` | Sirve CSS/JS sin servidor aparte |
| Servidor en el programa | `waitress` | En lugar de `runserver` |
| Excel | `openpyxl` | Exportación de reportes |
| PDF | `reportlab` | Exportación de reportes |
| Ventana de escritorio | `pywebview` | Con el navegador como plan de respaldo |
| Empaquetado | PyInstaller (`--onedir`) + Inno Setup | Instalador `.exe` |
| Frontend | Plantilla Bootstrap (AdminLTE o Tabler) + HTMX + Chart.js + Tom Select | Todo guardado en `frontend/static/vendor/`, **sin CDN** (debe funcionar sin internet) |

**Plantilla del frontend (registro).** Completar cuando se confirme. Pasos de integración en la sección 9.12.

| Dato | Valor |
|---|---|
| Nombre y versión | AdminLTE 4.0.2, basado en Bootstrap 5.3.8 |
| Carpeta en el proyecto | `frontend/static/vendor/adminlte/` |
| Licencia verificada para uso comercial | MIT; texto original conservado en `frontend/static/vendor/adminlte/LICENSE` |
| Estado | Recursos locales verificados; validación visual pendiente |

---

## 4. Estructura de carpetas

Leyenda: ✔ ya existe en el esqueleto · ☐ por crear.

```
sistema_inventarios/
├── README.md                            ✔ pasos para arrancar
├── .gitignore                           ✔ excluye .env, bases de datos y datos locales
├── backend/                             CÓDIGO PYTHON (Django)
│   ├── manage.py                        ✔
│   ├── requirements.txt                 ✔ dependencias del sistema
│   ├── requirements-desktop.txt         ✔ + pywebview y pyinstaller (empaquetado)
│   ├── .env.example                     ✔ modelo del archivo .env (sí va a git)
│   ├── .env                             ☐ valores reales (NO va a git)
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py                  ✔ configuración común, lee el .env
│   │   │   ├── desarrollo.py            ✔
│   │   │   └── produccion.py            ✔ programa instalado
│   │   ├── urls.py                      ✔ incluye las urls de cada app
│   │   ├── wsgi.py / asgi.py            ✔
│   └── apps/                            UN APP POR ÁREA DEL NEGOCIO
│       ├── core/
│       │   ├── models.py                ✔ EntidadAuditable (clase base abstracta)
│       │   ├── exceptions.py            ☐ ErrorDeNegocio
│       │   ├── validators.py            ☐ validadores reutilizables (dinero, cantidades)
│       │   ├── permissions.py           ☐ decorador @permiso_requerido
│       │   ├── context_processors.py    ✔ NOMBRE_NEGOCIO y MONEDA_SIMBOLO en todo el HTML
│       │   ├── views.py / urls.py       ✔ inicio (dashboard)
│       │   ├── services.py              ☐ respaldo manual, datos del dashboard
│       │   └── management/commands/cargar_datos_iniciales.py   ☐ roles, permisos, métodos de pago
│       ├── usuarios/                    models: Usuario, Rol, Permiso
│       ├── catalogo/                    models: Categoria, Producto, AtributoProducto, Presentacion
│       ├── compras/                     models: Proveedor, Compra, DetalleCompra
│       ├── inventario/                  models: Lote, MovimientoInventario  (+ alertas)
│       ├── ventas/                      models: Venta, DetalleVenta, DetalleVentaLote, MetodoPago, Pago
│       │                                carrito.py ☐ carrito guardado en la sesión
│       ├── caja/                        models: Caja, MovimientoCaja
│       ├── reportes/                    sin modelos: consultas (services.py) y exportadores.py ☐ Excel/PDF
│       └── auditoria/                   models: LogAuditoria
│           (cada app: models.py, forms.py ☐, services.py ✔, views.py ✔,
│            urls.py ✔, admin.py ✔, tests/ ✔)
├── frontend/                            HTML, CSS y JS (Django los lee desde aquí)
│   ├── templates/
│   │   ├── base.html                    ✔ esqueleto donde se integra la plantilla (ver 9.12)
│   │   ├── inicio.html                  ✔
│   │   ├── components/                  ✔ _menu.html, _mensajes.html  (☐ _modal.html, _paginacion.html)
│   │   ├── registration/login.html      ✔
│   │   ├── catalogo/  compras/  inventario/  caja/  reportes/   ☐ pantallas de cada área
│   │   └── ventas/                      ☐ pos.html y partials/ (_carrito.html, _lista_productos.html)
│   └── static/
│       ├── css/app.css                  ✔ estilos propios
│       ├── js/app.js                    ✔ JS general (config de HTMX)
│       ├── js/pos.js                    ☐ atajos de teclado y lector de código de barras
│       ├── vendor/                      ✔ plantilla, HTMX, Chart.js, Tom Select (guardados aquí)
│       └── img/
├── desktop/                             EMPAQUETADO (al final)
│   ├── launcher.py                      ☐ migra, inicia waitress y abre la ventana
│   ├── sistema.spec                     ☐ configuración de PyInstaller
│   └── installer/                       ☐ setup.iss, politicas.txt, icono.ico
├── scripts/
│   └── respaldo.py                      ✔ copia de seguridad de la base (lee el .env)
└── docs/
    ├── diagrama_clases_inventario_v4.mermaid   ✔
    ├── mockups/                         ✔ pantalla_venta.html y pantalla_caja.html (referencia visual)
    └── ESPECIFICACION_SISTEMA.md        este documento
```

### Archivos de preparación añadidos en fase 0

- `backend/apps/core/exceptions.py`: `ErrorDeNegocio`.
- `backend/apps/core/validators.py`: `validar_dinero` (Decimal finito, no negativo,
  hasta dos decimales efectivos) y `validar_cantidad` (entero positivo).
- `backend/apps/core/permissions.py`: decorador inicial; sin modelos ni roles,
  permite únicamente superusuario autenticado y activo; resto denegado.
  La conexión con roles y permisos corresponde a la fase 2.
- `backend/apps/core/frontend.py`: inventario de recursos frontend locales.
- `backend/apps/core/tests/test_fase0.py`: pruebas sin acceso a la base de datos.
- `frontend/templates/403.html`: mensaje de acceso restringido.
- `scripts/preparar_frontend.py`: descarga de desarrollo con versiones fijas,
  comprobación de integridad, licencias y verificación local mediante
  `--verificar`. No se ejecuta al abrir el sistema.
- `frontend/static/vendor/manifest.json`: versiones, licencias e integridad de recursos descargados.
- `scripts/verificar_interfaz_fase0.py`: prueba aislada de WebView2 y plantillas,
  con CSP para recursos externos y salida JSON. Usa APIs públicas, no genera
  capturas nativas y no es el launcher.
- `docs/verificacion_fase0/resultado.json`: resultado real de la prueba de escritorio.
- `frontend/static/img/favicon.svg`: icono local enlazado desde la base HTML.
- `docs/FASE_0_RESULTADOS.md`: resultados reales, limitaciones y verificación manual.

### Qué busco → dónde está

| Si necesito... | Voy a... |
|---|---|
| Cambiar una regla de negocio (ej. cómo se descuenta el stock) | `backend/apps/<app>/services.py` |
| Agregar o cambiar un campo de la base | `backend/apps/<app>/models.py` y luego `makemigrations` |
| Validar el formato de un formulario | `backend/apps/<app>/forms.py` o `core/validators.py` |
| Ver qué URL abre qué pantalla | `backend/apps/<app>/urls.py` y la sección 9 de este documento |
| Cambiar el HTML de una pantalla | `frontend/templates/<app>/<pantalla>.html` |
| Cambiar un fragmento que se actualiza sin recargar | `frontend/templates/<app>/partials/_<nombre>.html` |
| Cambiar colores o estilos | `frontend/static/css/app.css` |
| Cambiar un valor de configuración (moneda, días de alerta, rutas) | `backend/.env` |
| Programar el respaldo | `scripts/respaldo.py` |

---

## 5. Variables de entorno (.env)

Todo lo que cambia según el equipo o es secreto vive en el archivo `.env`, **nunca** escrito directamente en el código. El archivo `.env` no se sube a git ni se incluye en el instalador; en su lugar se versiona `backend/.env.example` (sin valores secretos).

### Dónde está el archivo

| Entorno | Ubicación del `.env` |
|---|---|
| Desarrollo | `backend/.env` |
| Programa instalado | `C:\ProgramData\SistemaInventarios\.env` (el `launcher.py` define la variable `ENV_FILE` apuntando ahí y lo crea en la primera ejecución, generando una `SECRET_KEY` nueva) |

### Variables

| Variable | Obligatoria | Por defecto | Para qué sirve |
|---|---|---|---|
| `SECRET_KEY` | **Sí** | — | Clave secreta de Django. Si falta, el sistema se detiene con un mensaje claro |
| `DEBUG` | No | `False` | `True` solo en desarrollo; nunca en el programa instalado |
| `ALLOWED_HOSTS` | No | `localhost,127.0.0.1` | Direcciones desde las que se puede abrir el sistema |
| `HOST` | No | `127.0.0.1` | Dirección donde escucha el servidor (programa empaquetado) |
| `PORT` | No | `8000` | Puerto del servidor |
| `DATA_DIR` | No | `backend/datos` | Carpeta de datos (base, respaldos, logs) |
| `DB_PATH` | No | `DATA_DIR/db.sqlite3` | Ruta de la base de datos |
| `BACKUP_DIR` | No | `DATA_DIR/respaldos` | Carpeta de las copias de seguridad |
| `BACKUP_CONSERVAR` | No | `30` | Cuántas copias se guardan |
| `LOG_DIR` | No | `DATA_DIR/logs` | Carpeta de los registros |
| `LOG_LEVEL` | No | `INFO` | Detalle de los registros |
| `NOMBRE_NEGOCIO` | No | `Mi tienda` | Se muestra en pantallas y reportes |
| `MONEDA_SIMBOLO` | No | `Bs` | Símbolo de moneda en pantallas y reportes |
| `DIAS_ALERTA_VENCIMIENTO` | No | `30` | Días de anticipación para la alerta "por vencer" |
| `STOCK_MINIMO_DEFECTO` | No | `5` | Stock mínimo sugerido al crear un producto |
| `LANGUAGE_CODE` | No | `es` | Idioma |
| `TIME_ZONE` | No | `America/La_Paz` | Zona horaria |
| `SESSION_COOKIE_AGE` | No | `28800` | Segundos que dura la sesión (8 horas) |

### Cómo se leen (ya implementado en `config/settings/base.py`)

```python
load_dotenv(ENV_FILE)                  # carga el archivo .env

SECRET_KEY = env_str("SECRET_KEY")     # sin valor por defecto: obligatoria
DEBUG = env_bool("DEBUG", False)       # acepta true / 1 / si / yes
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 28800)   # avisa si no es un número
ALLOWED_HOSTS = env_lista("ALLOWED_HOSTS", "localhost,127.0.0.1")
```

Las cuatro funciones (`env_str`, `env_bool`, `env_int`, `env_lista`) interpretan el valor con el tipo correcto. `env_str` (cuando falta una variable obligatoria) y `env_int` (cuando el valor no es un número) detienen el sistema con un mensaje que dice **qué variable** y **en qué archivo** corregir. `HOST` y `PORT` los lee `desktop/launcher.py`, no `base.py`.

### Validaciones de configuración de fase 0

Los valores de texto declarados vacíos se rechazan; para usar un valor por defecto
se omite la variable. Los booleanos aceptan true/1/si/sí/yes y false/0/no,
sin distinguir mayúsculas; otras entradas se rechazan. Los errores identifican
variable y archivo sin imprimir su contenido. Los días de alerta y stock mínimo
son enteros >= 0; retención de respaldos y duración de sesión son enteros >= 1.
LOG_LEVEL admite DEBUG, INFO, WARNING, ERROR y CRITICAL. La rotación conserva
un archivo activo y cuatro históricos (cinco archivos en total).
Estas validaciones de settings no corrigen aún el script independiente de respaldo.

### Reglas

1. **Ningún secreto ni ruta fija en el código.** Si un valor puede cambiar por equipo, va al `.env`.
2. Todo valor nuevo se agrega a `.env.example` en el mismo cambio, con un comentario.
3. En el código se lee con `django.conf.settings` (ej. `settings.DIAS_ALERTA_VENCIMIENTO`), nunca con `os.environ` directo fuera de `base.py`.
4. Generar una `SECRET_KEY`:
   `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`

---

## 6. Estándares de código del backend

Objetivo: código **legible, ordenado y fácil de conectar con el frontend**. Cualquier persona debe poder abrir un archivo y entender qué hace sin adivinar.

### 6.1 Capas y responsabilidades

Cada capa hace una sola cosa. Si una función hace dos cosas de capas distintas, se divide.

| Capa | Archivo | Responsabilidad | Lo que NO hace |
|---|---|---|---|
| Datos | `models.py` | Define las tablas y sus restricciones de integridad | No contiene lógica de pantallas |
| Entrada | `forms.py`, `core/validators.py` | Valida **el formato** de lo que escribe el usuario (tipos, rangos, obligatorios) | No decide reglas de negocio |
| Negocio | `services.py` | Aplica las reglas de negocio (RN-xx) y escribe en la base | No conoce `request` ni HTML |
| Vista | `views.py` | Recibe la petición, llama al servicio, devuelve HTML | No hace cálculos ni consultas complejas |
| Ruta | `urls.py` | Asocia una URL con una vista y le da un nombre | — |
| Pantalla | `frontend/templates/` | Muestra los datos que recibe | No calcula nada |

**Flujo de una acción** (ejemplo: confirmar una venta):

```
Navegador (HTMX)  →  urls.py  →  views.confirmar_venta  →  services.registrar_venta  →  models
                                         ↑                          |
                                         └── ErrorDeNegocio ────────┘   (si algo no cumple)
Respuesta: fragmento HTML (partial) con el resultado o con el mensaje de error
```

### 6.2 Validación en tres niveles

Los datos se validan **tres veces**, cada una con un propósito distinto:

| Nivel | Dónde | Qué comprueba | Ejemplo |
|---|---|---|---|
| 1. Formato | `forms.py` / `validators.py` | Que el dato tenga forma válida | El precio es un número mayor o igual a 0 |
| 2. Negocio | `services.py` | Que la operación cumpla las reglas | Hay stock suficiente; hay caja abierta |
| 3. Base de datos | `models.py` (`Meta.constraints`) | Que nada inconsistente se guarde, aunque falle lo anterior | La equivalencia de una presentación es ≥ 1 |

**Validador reutilizable** (`apps/core/validators.py`):

```python
from decimal import Decimal
from django.core.exceptions import ValidationError


def validar_dinero(valor):
    """El dinero no puede ser negativo ni tener más de 2 decimales."""
    if valor is None or valor < 0:
        raise ValidationError("El monto no puede ser negativo.")
    if valor != valor.quantize(Decimal("0.01")):
        raise ValidationError("El monto admite como máximo 2 decimales.")
```

**Restricción en el modelo** (`apps/catalogo/models.py`):

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=["producto", "nombre"],
            name="presentacion_nombre_unico_por_producto",   # RN-02
        ),
        models.CheckConstraint(
            condition=models.Q(unidades_equivalentes__gte=1),
            name="presentacion_unidades_minimo_1",
        ),
    ]
```

### 6.3 Errores de negocio

Las reglas de negocio que no se cumplen lanzan una excepción propia, con un mensaje **claro y en español**, pensado para que el usuario lo lea tal cual (`apps/core/exceptions.py`):

```python
class ErrorDeNegocio(Exception):
    """Se lanza cuando una operación no cumple una regla del negocio.
    El mensaje se muestra directamente al usuario."""

    def __init__(self, mensaje, campo=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.campo = campo    # campo del formulario relacionado (opcional)
```

Mensajes: dicen **qué pasó y qué hacer**. Ejemplo: `"No alcanza el stock de Colágeno 300 g: quedan 9 unidades."`, no `"Error 400"`.

### 6.4 Servicios: forma estándar

Todas las funciones de `services.py` siguen esta forma:

1. **Nombre** de verbo + objeto en español: `registrar_venta`, `abrir_caja`, `descontar_stock_fefo`.
2. **Docstring** con: qué hace, `Pasos:` numerados, `Lanza:` los errores posibles.
3. **Validar primero**: los datos de entrada se comprueban al inicio, antes de tocar la base.
4. Una función que escribe en varias tablas va dentro de `transaction.atomic()` (si algo falla, no se guarda nada).
5. Cada paso lleva un comentario `# Paso N: ...` que coincide con el docstring.
6. Reciben objetos o datos simples (nunca `request`) y devuelven un objeto o lanzan `ErrorDeNegocio`.
7. Funciones cortas: si pasa de unas 40 líneas, se divide en funciones auxiliares (con prefijo `_`).

**Ejemplo completo del estilo** (`apps/inventario/services.py`):

```python
from django.db.models import F
from django.utils import timezone

from apps.core.exceptions import ErrorDeNegocio
from .models import Lote


def descontar_stock_fefo(producto, unidades):
    """Descuenta `unidades` del producto, empezando por el lote que vence primero.

    Pasos:
        1. Validar que `unidades` sea un entero mayor que cero.
        2. Bloquear los lotes con stock y no vencidos (evita que dos ventas
           simultáneas tomen las mismas unidades).
        3. Comprobar que el stock total alcance.
        4. Recorrer los lotes por fecha de vencimiento y descontar de cada uno.
        5. Devolver de qué lote salió cada cantidad (para calcular costo y ganancia).

    Lanza:
        ErrorDeNegocio: si las unidades no son válidas o el stock no alcanza.

    Debe llamarse dentro de `transaction.atomic()`.
    """
    # Paso 1: validar la entrada
    if not isinstance(unidades, int) or isinstance(unidades, bool) or unidades <= 0:
        raise ErrorDeNegocio("La cantidad a descontar debe ser un número entero mayor que cero.")

    # Paso 2: lotes disponibles, el que vence antes primero (RN-06 y RN-07)
    lotes = list(
        Lote.objects.select_for_update()
        .filter(producto=producto, cantidad_actual__gt=0)
        .exclude(fecha_vencimiento__lt=timezone.localdate())
        .order_by(F("fecha_vencimiento").asc(nulls_last=True), "id")
    )

    # Paso 3: comprobar el stock
    disponible = sum(lote.cantidad_actual for lote in lotes)
    if disponible < unidades:
        raise ErrorDeNegocio(
            f"No alcanza el stock de {producto.nombre}: quedan {disponible} unidades."
        )

    # Paso 4: descontar lote por lote
    restante = unidades
    salidas = []
    for lote in lotes:
        tomar = min(lote.cantidad_actual, restante)
        lote.cantidad_actual -= tomar
        lote.save(update_fields=["cantidad_actual"])
        salidas.append((lote, tomar))
        restante -= tomar
        if restante == 0:
            break

    # Paso 5: informar de dónde salió cada cantidad
    return salidas
```

### 6.5 Vistas: delgadas

Una vista hace solo cuatro cosas: **leer** la petición, **llamar** al servicio, **capturar** `ErrorDeNegocio`, **devolver** HTML. Si un error de negocio ocurre en una petición HTMX, se responde con estado **422** y el mismo fragmento con el mensaje.

```python
@login_required
@permiso_requerido("vender")
@require_POST
def confirmar_venta(request):
    """Confirma la venta del carrito. Devuelve el resumen, o el carrito con el error."""
    carrito = obtener_carrito(request.session)            # leer
    try:
        venta = services.registrar_venta(                  # llamar
            usuario=request.user,
            lineas=carrito["lineas"],
            pagos=leer_pagos(request.POST),
        )
    except ErrorDeNegocio as error:                        # capturar
        contexto = {"carrito": carrito, "error": error.mensaje}
        return render(request, "ventas/partials/_carrito.html", contexto, status=422)
    vaciar_carrito(request.session)                        # devolver
    return render(request, "ventas/partials/_venta_confirmada.html", {"venta": venta})
```

### 6.6 Nombres y convenciones

| Elemento | Convención | Ejemplo |
|---|---|---|
| Modelos | `PascalCase` en singular, español | `DetalleVenta` |
| Campos y funciones | `snake_case` en español | `unidades_equivalentes`, `registrar_compra` |
| Constantes | `MAYUSCULAS` | `TIPO_EGRESO` |
| Funciones auxiliares internas | prefijo `_` | `_calcular_subtotal` |
| URLs (name) | `app:entidad_accion` | `ventas:pos`, `catalogo:producto_lista` |
| Plantillas | `snake_case.html`; los fragmentos empiezan con `_` | `producto_lista.html`, `partials/_carrito.html` |
| IDs HTML para HTMX | `kebab-case`, descriptivos | `#carrito`, `#lista-productos`, `#movimientos-caja` |
| Textos en pantalla sobre la caja | decir "turno de caja" (abrir turno, cerrar turno), no "caja" a secas | "Abre tu turno de caja antes de vender." |
| Dinero | siempre `Decimal` / `DecimalField(max_digits=12, decimal_places=2)`, **nunca** `float` | — |
| Fechas | `DateTimeField` con zona horaria (`USE_TZ = True`) | — |

Sin "números mágicos": un valor que puede cambiar (días de alerta, stock mínimo) sale de `settings` / `.env`. Los textos de estado se definen como `TextChoices` dentro del modelo:

```python
class TipoMovimiento(models.TextChoices):
    ENTRADA = "ENTRADA", "Entrada"
    SALIDA = "SALIDA", "Salida"
    AJUSTE = "AJUSTE", "Ajuste"
    MERMA = "MERMA", "Merma"
```

### 6.7 Lista de revisión antes de dar por terminada una función

- [ ] ¿Tiene docstring con `Pasos:` y `Lanza:`?
- [ ] ¿Valida los datos de entrada antes de escribir en la base?
- [ ] ¿Usa `transaction.atomic()` si toca más de una tabla?
- [ ] ¿Los mensajes de error le dicen al usuario qué hacer?
- [ ] ¿El dinero usa `Decimal`?
- [ ] ¿Tiene al menos una prueba del caso correcto y una del caso que falla?
- [ ] ¿El archivo y la URL están anotados en la sección 9 de este documento?

---

## 7. Modelos (datos) por app

Leyenda: **PK** = clave primaria · **FK** = relación · ≥0 = valor mínimo (se valida en formulario, servicio **y** base de datos). Los modelos marcados con ◆ heredan de `EntidadAuditable` (campos `creado_en`, `modificado_en`, `creado_por`, `modificado_por`). El diagrama completo está en `docs/diagrama_clases_inventario_v4.mermaid`.

### `usuarios` — `backend/apps/usuarios/models.py`

| Modelo | Campos | Restricciones |
|---|---|---|
| `Usuario` (hereda de `AbstractUser`) | username, password, `first_name`, `last_name`, `is_active` (estos cinco ya vienen de `AbstractUser`; **no** crear campos `nombre` ni `activo`), `rol` (FK → Rol) | username único |
| `Rol` | nombre, descripcion, `permisos` (varios → Permiso) | nombre único |
| `Permiso` | codigo, descripcion | codigo único (ver sección 10) |

### `catalogo` — `backend/apps/catalogo/models.py`

| Modelo | Campos | Restricciones |
|---|---|---|
| `Categoria` | nombre, `padre` (FK → Categoria, opcional), activa | nombre único dentro del mismo padre; sin ciclos (RN-18) |
| `Producto` ◆ | codigo, nombre, descripcion, `categoria` (FK), stock_minimo, activo | codigo único; stock_minimo ≥ 0; propiedad `stock_actual` (suma de lotes) |
| `AtributoProducto` | `producto` (FK), nombre, valor | (producto, nombre) único |
| `Presentacion` ◆ | `producto` (FK), nombre, unidades_equivalentes, precio_venta, activa | (producto, nombre) único; unidades_equivalentes ≥ 1; precio_venta ≥ 0 |

### `compras` — `backend/apps/compras/models.py`

| Modelo | Campos | Restricciones |
|---|---|---|
| `Proveedor` ◆ | nombre, tipo (EMPRESA / COMPRA_PROPIA), contacto, telefono, origen, activo | nombre único |
| `Compra` ◆ | `proveedor` (FK), fecha, total, observacion, `usuario` (FK) | total ≥ 0 |
| `DetalleCompra` | `compra` (FK), `producto` (FK), cantidad_unidades, costo_unitario, subtotal | cantidad ≥ 1; costo ≥ 0 |

### `inventario` — `backend/apps/inventario/models.py`

| Modelo | Campos | Restricciones |
|---|---|---|
| `Lote` | `producto` (FK), `detalle_compra` (uno a uno), codigo_lote, fecha_vencimiento (opcional), cantidad_inicial, cantidad_actual, costo_unitario | 0 ≤ cantidad_actual ≤ cantidad_inicial; costo ≥ 0 |
| `MovimientoInventario` | `lote` (FK), tipo (ENTRADA / SALIDA / AJUSTE / MERMA), cantidad, fecha, motivo, `usuario` (FK) | cantidad ≠ 0; solo se crean, nunca se editan |

### `ventas` — `backend/apps/ventas/models.py`

| Modelo | Campos | Restricciones |
|---|---|---|
| `MetodoPago` | nombre, es_efectivo, activo | nombre único. Datos iniciales: Efectivo, QR, Transferencia |
| `Venta` ◆ | `caja` (FK), `usuario` (FK), fecha, total | total ≥ 0 |
| `DetalleVenta` | `venta` (FK), `presentacion` (FK), cantidad_presentaciones, unidades_totales, precio_aplicado, subtotal | cantidades ≥ 1; precio ≥ 0 |
| `DetalleVentaLote` | `detalle_venta` (FK), `lote` (FK), cantidad_unidades | cantidad ≥ 1 |
| `Pago` | `venta` (FK), `metodo` (FK), monto, referencia (opcional) | monto > 0 |

### `caja` — `backend/apps/caja/models.py`

| Modelo | Campos | Restricciones |
|---|---|---|
| `Caja` ◆ | `usuario` (FK, quien abre), `cerrada_por` (FK, opcional), fecha_apertura, fecha_cierre, monto_inicial, monto_contado, estado (ABIERTA / CERRADA), `turno` (opcional, texto corto: "Mañana", "Tarde"), observacion | **una sola caja ABIERTA por usuario** (RN-11); monto_inicial ≥ 0; turno de máximo 30 caracteres. Métodos: `monto_esperado()`, `diferencia()` |
| `MovimientoCaja` | `caja` (FK), tipo (INGRESO / EGRESO), monto, concepto, fecha, `usuario` (FK) | monto > 0; concepto obligatorio |

### `auditoria` — `backend/apps/auditoria/models.py`

| Modelo | Campos | Restricciones |
|---|---|---|
| `LogAuditoria` | `usuario` (FK), fecha, accion, entidad, entidad_id, valor_anterior, valor_nuevo | solo lectura: no se edita ni se borra |

> **Decisión sobre la clase `Caja`:** se mantiene **una sola clase `Caja`**, que representa **un turno de caja** (apertura y cierre), con el campo opcional `turno`. El negocio tiene una sola vendedora y la regla RN-11 (una caja abierta por usuario) ya permite que cada empleado nuevo tenga su propio turno. En pantallas y mensajes se habla de "turno de caja" para no confundirla con la presentación "caja" de un producto. Si el negocio crece a varias cajas físicas, se renombra la clase actual a `TurnoCaja` y se crea una clase `Caja` (la registradora), enlazando los turnos existentes a una "Caja principal" con una migración de datos.

### 7.10 Definición exacta de campos (tipos, relaciones y restricciones)

Referencia para escribir los `models.py` sin ambigüedad. Sintaxis abreviada: `Char(n)` = `CharField(max_length=n)`; `Dinero` = `DecimalField(max_digits=12, decimal_places=2)`; `Entero+` = `PositiveIntegerField`; `FK(Modelo, política)` con `related_name` entre corchetes.

**Reglas generales**

- **Claves primarias:** automáticas (`BigAutoField`).
- **Política `on_delete`:** `PROTECT` en toda relación hacia datos con historial (producto, presentación, lote, proveedor, método de pago, caja, usuario); `CASCADE` solo de una línea de detalle hacia su cabecera (compra → detalles, venta → detalles y pagos, caja → movimientos, producto → atributos y presentaciones); `SET_NULL` en los campos de auditoría.
- **Dinero:** `Dinero` con validador `validar_dinero`. **Cantidades:** `Entero+` con mínimo indicado.
- **Textos de estado:** `TextChoices` dentro del modelo (ver 6.6).
- Los modelos marcados ◆ en la sección 7 heredan de `EntidadAuditable`. Los campos `creado_por` y `modificado_por` **los asigna el servicio** (ayudante `asignar_auditoria(instancia, usuario)` en `core/utils.py`); no dependen de middleware.
- Cada `Meta` define `ordering` y las restricciones listadas; los nombres de las restricciones son descriptivos y únicos.

```
# ---------- usuarios ----------
Usuario(AbstractUser)
  rol            FK(Rol, PROTECT, null, blank)            [usuarios]
Rol
  nombre         Char(60, unique)
  descripcion    Char(200, blank)
  permisos       ManyToMany(Permiso, blank)               [roles]
Permiso
  codigo         Char(50, unique)
  descripcion    Char(200)

# ---------- catalogo ----------
Categoria
  nombre         Char(80)
  padre          FK('self', PROTECT, null, blank)         [hijos]
  activa         Boolean(default=True)
  Meta: UniqueConstraint(padre, nombre)
        UniqueConstraint(nombre, condition=Q(padre__isnull=True))   # evita raíces repetidas
Producto ◆
  codigo         Char(30, unique)
  nombre         Char(120)
  descripcion    Text(blank)
  categoria      FK(Categoria, PROTECT)                   [productos]
  stock_minimo   Entero+(default=settings.STOCK_MINIMO_DEFECTO)
  activo         Boolean(default=True)
  @property stock_actual  -> suma de cantidad_actual de sus lotes
AtributoProducto
  producto       FK(Producto, CASCADE)                    [atributos]
  nombre         Char(60)
  valor          Char(120)
  Meta: UniqueConstraint(producto, nombre)
Presentacion ◆
  producto       FK(Producto, CASCADE)                    [presentaciones]
  nombre         Char(40)
  unidades_equivalentes  Entero+   (>= 1)
  precio_venta   Dinero
  activa         Boolean(default=True)
  Meta: UniqueConstraint(producto, nombre); CheckConstraint(unidades_equivalentes >= 1)

# ---------- compras ----------
Proveedor ◆
  nombre         Char(120, unique)
  tipo           Char(20, choices=EMPRESA | COMPRA_PROPIA)
  contacto       Char(120, blank)
  telefono       Char(30, blank)
  origen         Char(80, blank)                          # ciudad o departamento
  activo         Boolean(default=True)
Compra ◆
  proveedor      FK(Proveedor, PROTECT)                   [compras]
  fecha          DateField(default=fecha de hoy)
  total          Dinero(default=0)
  observacion    Char(200, blank)
  usuario        FK(AUTH_USER_MODEL, PROTECT)             [compras_registradas]
DetalleCompra
  compra         FK(Compra, CASCADE)                      [detalles]
  producto       FK(Producto, PROTECT)                    [detalles_compra]
  cantidad_unidades  Entero+   (>= 1)
  costo_unitario Dinero
  subtotal       Dinero

# ---------- inventario ----------
Lote
  producto       FK(Producto, PROTECT)                    [lotes]
  detalle_compra OneToOne(DetalleCompra, PROTECT, null, blank)   [lote]
  codigo_lote    Char(30, unique)                         # formato L-AAAA-NNNN
  fecha_vencimiento  DateField(null, blank)
  cantidad_inicial   Entero+   (>= 1)
  cantidad_actual    Entero+
  costo_unitario Dinero
  Meta: CheckConstraint(cantidad_actual <= cantidad_inicial)
MovimientoInventario
  lote           FK(Lote, PROTECT)                        [movimientos]
  tipo           Char(10, choices=ENTRADA | SALIDA | AJUSTE | MERMA)
  cantidad       IntegerField con signo (distinta de 0):
                 ENTRADA positiva; SALIDA y MERMA negativas; AJUSTE de cualquier signo
  fecha          DateTimeField(auto_now_add)
  motivo         Char(200, blank)                         # ej. "Venta #123", "Producto dañado"
  usuario        FK(AUTH_USER_MODEL, PROTECT)             [movimientos_inventario]
  Meta: CheckConstraint(cantidad != 0). Solo se crean; nunca se editan ni se borran

# ---------- ventas ----------
MetodoPago
  nombre         Char(40, unique)
  es_efectivo    Boolean(default=False)
  activo         Boolean(default=True)
Venta ◆
  caja           FK(Caja, PROTECT)                        [ventas]
  usuario        FK(AUTH_USER_MODEL, PROTECT)             [ventas_realizadas]
  fecha          DateTimeField(default=ahora)
  total          Dinero
DetalleVenta
  venta          FK(Venta, CASCADE)                       [detalles]
  presentacion   FK(Presentacion, PROTECT)                [detalles_venta]
  cantidad_presentaciones  Entero+  (>= 1)
  unidades_totales         Entero+  (>= 1)                # cantidad x unidades_equivalentes
  precio_aplicado Dinero                                  # precio de la presentación al vender
  subtotal       Dinero
DetalleVentaLote
  detalle_venta  FK(DetalleVenta, CASCADE)                [salidas_lote]
  lote           FK(Lote, PROTECT)                        [salidas_venta]
  cantidad_unidades  Entero+   (>= 1)
Pago
  venta          FK(Venta, CASCADE)                       [pagos]
  metodo         FK(MetodoPago, PROTECT)                  [pagos]
  monto          Dinero   (> 0)                           # lo aplicado al total; el vuelto no se guarda
  referencia     Char(60, blank)                          # ej. número de transacción QR

# ---------- caja ----------
Caja ◆                                                    # = un turno de caja
  usuario        FK(AUTH_USER_MODEL, PROTECT)             [cajas]       # quien abre
  cerrada_por    FK(AUTH_USER_MODEL, PROTECT, null, blank) [cajas_cerradas]
  fecha_apertura DateTimeField(default=ahora)
  fecha_cierre   DateTimeField(null, blank)
  monto_inicial  Dinero
  monto_contado  Dinero(null, blank)
  estado         Char(10, choices=ABIERTA | CERRADA, default=ABIERTA)
  turno          Char(30, blank)                          # ej. "Mañana", "Tarde"
  observacion    Char(200, blank)
  Meta: UniqueConstraint(usuario, condition=Q(estado="ABIERTA"),
                         name="una_caja_abierta_por_usuario")           # RN-11
  métodos: monto_esperado(), diferencia()
MovimientoCaja
  caja           FK(Caja, CASCADE)                        [movimientos]
  tipo           Char(10, choices=INGRESO | EGRESO)
  monto          Dinero   (> 0)
  concepto       Char(120)
  fecha          DateTimeField(default=ahora)
  usuario        FK(AUTH_USER_MODEL, PROTECT)             [movimientos_caja]

# ---------- auditoria ----------
LogAuditoria                                              # solo lectura
  usuario        FK(AUTH_USER_MODEL, SET_NULL, null, blank)   related_name="+"
  fecha          DateTimeField(auto_now_add, db_index=True)
  accion         Char(40)                                 # ej. CAMBIO_PRECIO, CIERRE_CAJA
  entidad        Char(60)                                 # ej. "Presentacion"
  entidad_id     Entero+
  valor_anterior JSONField(null, blank)
  valor_nuevo    JSONField(null, blank)
  Meta: ordering = ["-fecha"]; en el admin: sin agregar, editar ni borrar
```

---

## 8. Servicios paso a paso

Aquí se describe **qué hace cada función de negocio y en qué orden**. Es la guía para escribir `services.py`; el código final debe seguir estos pasos y comentarlos con `# Paso N`. Todas lanzan `ErrorDeNegocio` con un mensaje claro.

### 8.1 `ventas/services.py`

**`registrar_venta(usuario, lineas, pagos)`** — línea: `{presentacion_id, cantidad}`; pago: `{metodo_id, monto, referencia}`

1. Validar que haya al menos una línea y que cada una tenga una presentación activa y una cantidad entera ≥ 1.
2. Buscar la caja abierta del usuario. Si no hay, error: *"Abre tu turno de caja antes de vender."* (RN-10)
3. Validar los pagos: al menos uno, cada monto > 0 y método activo.
4. Abrir `transaction.atomic()`.
5. Por cada línea: calcular `unidades = cantidad × unidades_equivalentes`, tomar `precio_aplicado` de la presentación y `subtotal = precio × cantidad` (RN-01, RN-08).
6. Calcular el `total` y comprobar que la **suma de los pagos sea igual al total** (RN-14).
7. Crear la `Venta`.
8. Por cada línea: crear el `DetalleVenta` y llamar a `descontar_stock_fefo(producto, unidades)`.
9. Por cada salida de lote: crear `DetalleVentaLote` y un `MovimientoInventario` de tipo SALIDA.
10. Crear los `Pago`. *(El vuelto se calcula solo en pantalla; no se guarda: los pagos guardan lo aplicado al total.)*
11. Devolver la `Venta`. Si algo falla en cualquier paso, no se guarda nada.

Errores típicos: sin caja abierta · presentación inactiva · stock insuficiente · pagos que no suman el total.

**Carrito** (`ventas/carrito.py`, guardado en la **sesión**, no en la base): `obtener_carrito(session)`, `agregar_linea(session, presentacion_id)`, `cambiar_cantidad(...)`, `cambiar_presentacion(...)`, `quitar_linea(...)`, `vaciar_carrito(session)`, `calcular_totales(carrito)`. Cada una valida que la presentación exista y esté activa y que la cantidad sea un entero ≥ 1.

### 8.2 `inventario/services.py`

**`descontar_stock_fefo(producto, unidades)`** — ver código completo en 6.4.

**`ajustar_inventario(usuario, lote, tipo, cantidad, motivo)`**

1. Validar que `tipo` sea AJUSTE o MERMA y que `cantidad` sea un entero distinto de cero.
2. Validar que el `motivo` tenga al menos 5 caracteres (RN-19, RN-21).
3. Abrir `transaction.atomic()` y bloquear el lote.
4. Calcular la nueva `cantidad_actual`; si queda negativa o mayor que la inicial, error.
5. Guardar el lote, crear el `MovimientoInventario` y registrar en `LogAuditoria` (valor anterior y nuevo).

**`obtener_alertas()`** devuelve tres listas: *stock bajo* (stock ≤ mínimo), *por vencer* (lotes con stock que vencen en `DIAS_ALERTA_VENCIMIENTO` días o menos) y *vencidos con stock* (RN-16, RN-07).

### 8.3 `compras/services.py`

**`registrar_compra(usuario, proveedor, lineas)`** — línea: `{producto_id, cantidad, costo_unitario, fecha_vencimiento}`

1. Validar proveedor activo y al menos una línea.
2. Validar cada línea: producto activo, cantidad entera ≥ 1, costo ≥ 0 con `validar_dinero`, vencimiento vacío o de hoy en adelante.
3. Abrir `transaction.atomic()` y crear la `Compra`.
4. Por cada línea: crear `DetalleCompra` (subtotal = cantidad × costo), crear el `Lote` (cantidad_inicial = cantidad_actual = cantidad, costo, vencimiento, código tipo `L-2026-0001`) y un `MovimientoInventario` ENTRADA (RN-05).
5. Calcular y guardar el `total` de la compra.
6. Devolver la `Compra`.

### 8.4 `caja/services.py`

**`abrir_caja(usuario, monto_inicial, turno="")`**

1. Validar el monto con `validar_dinero`.
2. Limpiar el `turno` (quitar espacios sobrantes) y validar que no pase de 30 caracteres. Es opcional: si viene vacío se guarda vacío.
3. Verificar que el usuario no tenga otra caja abierta (RN-11).
4. Crear la `Caja` con estado ABIERTA, el turno y la hora actual.

**`registrar_movimiento_caja(usuario, tipo, monto, concepto)`**

1. Buscar la caja abierta del usuario; si no hay, error.
2. Validar que `tipo` sea INGRESO o EGRESO, que el monto sea > 0 y que el concepto no esté vacío (máximo 120 caracteres, sin espacios sobrantes).
3. Crear el `MovimientoCaja`.

**`calcular_resumen_caja(caja)`** devuelve: monto inicial, ventas en efectivo, ventas por cada otro método, ingresos, egresos y **efectivo esperado** (RN-12). Lo usan la pantalla de caja y el cierre.

**`cerrar_caja(usuario, caja, monto_contado)`**

1. Validar que la caja esté ABIERTA y pertenezca al usuario (o que sea el dueño quien cierra).
2. Validar `monto_contado` con `validar_dinero`.
3. Calcular el resumen con `calcular_resumen_caja`.
4. Guardar `monto_contado`, `fecha_cierre`, `cerrada_por` y estado CERRADA.
5. Registrar el cierre en `LogAuditoria` con esperado, contado y diferencia (RN-13, RN-21).
6. Devolver el resumen con la diferencia.

### 8.5 `catalogo/services.py`

- **`crear_producto(usuario, datos, presentaciones)`**: valida código único, categoría activa y que haya al menos una presentación (RN-03); crea el producto y sus presentaciones en una transacción.
- **`cambiar_precio(usuario, presentacion, nuevo_precio)`**: valida con `validar_dinero`, guarda y registra el valor anterior y el nuevo en `LogAuditoria` (RN-21).
- **`mover_categoria(categoria, nuevo_padre)`**: valida que el nuevo padre no sea la misma categoría ni una de sus descendientes (RN-18).
- **`desactivar_producto(usuario, producto)`**: marca `activo = False`; nunca borra si tiene historial (RN-17).

### 8.6 `reportes/services.py`

- **`ventas_agrupadas(desde, hasta, agrupar)`**: `agrupar` es `dia`, `semana` o `mes`. Valida que `desde ≤ hasta`; agrupa con `TruncDate / TruncWeek / TruncMonth` y suma totales.
- **`ganancias(desde, hasta)`**: precio aplicado − costo del lote, usando `DetalleVentaLote` (RN-09).
- **`inventario_valorizado()`**: stock actual × costo de cada lote.
- **`compras_por_periodo(desde, hasta)`** y **`productos_mas_vendidos(desde, hasta)`**.
- **`exportar_excel(nombre, columnas, filas)`** y **`exportar_pdf(titulo, columnas, filas)`**: reciben los mismos datos que muestra la pantalla y devuelven el archivo. Así lo exportado coincide siempre con lo que se ve.

### 8.7 `core/services.py` y `auditoria/services.py`

- **`crear_respaldo()`**: copia la base con la API de respaldo de SQLite, la guarda en `BACKUP_DIR` con fecha y hora, y borra las más antiguas según `BACKUP_CONSERVAR`.
- **`registrar_cambio(usuario, accion, entidad, entidad_id, anterior, nuevo)`**: crea un `LogAuditoria`. Lo llaman los demás servicios; nadie lo edita.

---

## 9. Mapa backend ↔ frontend

Esta sección es **el contrato entre las dos carpetas**: para cada pantalla dice qué URL la abre, qué vista la sirve, en qué archivo está el HTML y qué datos recibe. Quien haga el frontend solo necesita esta tabla.

Reglas generales:

- Las plantillas están en `frontend/templates/<app>/`; los fragmentos que HTMX actualiza están en `frontend/templates/<app>/partials/` y empiezan con `_`.
- Todas las plantillas reciben automáticamente `user`, `messages`, `request`, `NOMBRE_NEGOCIO`, `MONEDA_SIMBOLO` y `permisos` (lista de códigos del usuario).
- Las vistas con listas paginadas entregan `page_obj` (con `paginator`) y los filtros usados.
- Los formularios entregan `form` (con `form.errors`).
- El dinero se muestra con `{{ MONEDA_SIMBOLO }} {{ valor|floatformat:2 }}`.

**Contexto de fase 0:** `recursos_frontend_listos` indica que todos los archivos
CSS/JS del inventario local existen; actualmente se cumple y se sirven localmente.
Si faltaran, se omiten enlaces vendor para evitar 404, sin carga remota alternativa.
Este mecanismo no sustituye la validación del manifiesto y la revisión visual.
`permisos` continúa pendiente de la fase 2. Las entradas de módulos aún vacíos
se conservan deshabilitadas, sin inventar rutas.

### 9.1 Inicio y sistema (`core`)

| Pantalla | URL | `name` | Plantilla | Datos que recibe |
|---|---|---|---|---|
| Inicio (panel) | `/` | `core:inicio` | `inicio.html` ✔ | `ventas_hoy`, `cantidad_ventas_hoy`, `caja` (o `None`), `stock_bajo`, `por_vencer`, `vencidos` |
| Respaldos | `/sistema/respaldos/` | `core:respaldos` | `core/respaldos.html` | `respaldos` (lista con fecha y tamaño) |
| Crear respaldo | `POST /sistema/respaldos/crear/` | `core:respaldo_crear` | redirige a respaldos | — |
| Primer uso | `/configuracion-inicial/` | `core:primer_uso` | `core/primer_uso.html` | `form` (crear usuario dueño; solo si no existen usuarios) |

### 9.2 Usuarios (`usuarios`)

| Pantalla | URL | `name` | Plantilla | Datos |
|---|---|---|---|---|
| Ingresar | `/login/` ✔ | `usuarios:login` | `registration/login.html` ✔ | `form` |
| Salir | `POST /logout/` ✔ | `usuarios:logout` | — | — |
| Lista de usuarios | `/usuarios/` | `usuarios:lista` | `usuarios/usuario_lista.html` | `usuarios` |
| Crear / editar usuario | `/usuarios/nuevo/`, `/usuarios/<int:pk>/editar/` | `usuarios:usuario_crear`, `usuarios:usuario_editar` | `usuarios/usuario_form.html` | `form`, `roles` |
| Roles y permisos | `/usuarios/roles/` | `usuarios:rol_lista` | `usuarios/rol_lista.html` | `roles`, `permisos` |

### 9.3 Catálogo (`catalogo`)

| Pantalla | URL | `name` | Plantilla / parcial | Datos |
|---|---|---|---|---|
| Categorías (árbol) | `/catalogo/categorias/` | `catalogo:categoria_lista` | `catalogo/categoria_lista.html` | `categorias` (con `hijos`) |
| Crear / editar categoría | `/catalogo/categorias/nueva/`, `.../<int:pk>/editar/` | `catalogo:categoria_crear`, `catalogo:categoria_editar` | `catalogo/categoria_form.html` | `form` |
| Productos | `/catalogo/productos/?q=&categoria=` | `catalogo:producto_lista` | `catalogo/producto_lista.html` | `page_obj`, `categorias`, `q` |
| Crear / editar producto | `/catalogo/productos/nuevo/`, `.../<int:pk>/editar/` | `catalogo:producto_crear`, `catalogo:producto_editar` | `catalogo/producto_form.html` | `form`, `formset_presentaciones` |
| Detalle de producto | `/catalogo/productos/<int:pk>/` | `catalogo:producto_detalle` | `catalogo/producto_detalle.html` | `producto`, `presentaciones`, `atributos`, `lotes`, `stock_actual` |
| Desactivar producto | `POST .../<int:pk>/desactivar/` | `catalogo:producto_desactivar` | redirige al detalle | — |
| Agregar presentación (HTMX) | `POST /catalogo/productos/<int:pk>/presentaciones/nueva/` | `catalogo:presentacion_crear` | `catalogo/partials/_presentaciones.html` → `#presentaciones` | `presentaciones`, `form` |
| Cambiar precio (HTMX) | `POST /catalogo/presentaciones/<int:pk>/precio/` | `catalogo:presentacion_precio` | `catalogo/partials/_presentaciones.html` → `#presentaciones` | `presentaciones`, `error` |
| Agregar atributo (HTMX) | `POST /catalogo/productos/<int:pk>/atributos/nuevo/` | `catalogo:atributo_crear` | `catalogo/partials/_atributos.html` → `#atributos` | `atributos`, `form` |

### 9.4 Compras (`compras`)

| Pantalla | URL | `name` | Plantilla / parcial | Datos |
|---|---|---|---|---|
| Proveedores | `/compras/proveedores/` | `compras:proveedor_lista` | `compras/proveedor_lista.html` | `proveedores` |
| Crear / editar proveedor | `/compras/proveedores/nuevo/`, `.../<int:pk>/editar/` | `compras:proveedor_crear`, `compras:proveedor_editar` | `compras/proveedor_form.html` | `form` |
| Lista de compras | `/compras/?desde=&hasta=` | `compras:compra_lista` | `compras/compra_lista.html` | `page_obj`, `desde`, `hasta` |
| Nueva compra | `/compras/nueva/` | `compras:compra_crear` | `compras/compra_form.html` | `form`, `proveedores` |
| Agregar línea (HTMX) | `GET /compras/nueva/linea/` | `compras:compra_linea` | `compras/partials/_linea_compra.html` → `#lineas-compra` | `indice`, `productos` |
| Detalle de compra | `/compras/<int:pk>/` | `compras:compra_detalle` | `compras/compra_detalle.html` | `compra`, `detalles`, `lotes` |

### 9.5 Inventario (`inventario`)

| Pantalla | URL | `name` | Plantilla | Datos |
|---|---|---|---|---|
| Stock por producto | `/inventario/?q=&solo_bajo=1` | `inventario:stock_lista` | `inventario/stock_lista.html` | `page_obj` (cada producto con `stock_actual`), `q` |
| Lotes | `/inventario/lotes/` | `inventario:lote_lista` | `inventario/lote_lista.html` | `page_obj` |
| Alertas | `/inventario/alertas/` | `inventario:alertas` | `inventario/alertas.html` | `stock_bajo`, `por_vencer`, `vencidos`, `dias_alerta` |
| Ajuste / merma | `/inventario/ajuste/` | `inventario:ajuste_crear` | `inventario/ajuste_form.html` | `form`, `lotes` |
| Movimientos | `/inventario/movimientos/` | `inventario:movimiento_lista` | `inventario/movimiento_lista.html` | `page_obj`, filtros |

### 9.6 Ventas (`ventas`) — pantalla principal

| Pantalla / acción | URL | `name` | Plantilla / parcial | Datos |
|---|---|---|---|---|
| Venta (POS) | `/ventas/nueva/` | `ventas:pos` | `ventas/pos.html` | `caja`, `carrito`, `metodos_pago` |
| Buscar productos (HTMX) | `GET /ventas/buscar/?q=` | `ventas:buscar` | `ventas/partials/_lista_productos.html` → `#lista-productos` | `productos` (cada uno con `presentaciones` y `stock_actual`) |
| Agregar al carrito (HTMX) | `POST /ventas/carrito/agregar/` | `ventas:carrito_agregar` | `ventas/partials/_carrito.html` → `#carrito` | `carrito` |
| Cambiar cantidad o presentación | `POST /ventas/carrito/actualizar/` | `ventas:carrito_actualizar` | `_carrito.html` → `#carrito` | `carrito`, `error` |
| Quitar línea / vaciar | `POST /ventas/carrito/quitar/`, `.../vaciar/` | `ventas:carrito_quitar`, `ventas:carrito_vaciar` | `_carrito.html` → `#carrito` | `carrito` |
| Confirmar venta | `POST /ventas/confirmar/` | `ventas:confirmar` | **200:** `_venta_confirmada.html` · **422:** `_carrito.html` con `error` | `venta` · `carrito`, `error` |
| Ventas del día | `/ventas/` | `ventas:lista` | `ventas/venta_lista.html` | `page_obj`, `total_dia` |
| Detalle de venta | `/ventas/<int:pk>/` | `ventas:detalle` | `ventas/venta_detalle.html` | `venta`, `detalles`, `pagos` |

Forma del objeto `carrito` que recibe `_carrito.html`:

```
carrito = {
  "lineas": [ {"indice": 0, "presentacion": <obj>, "producto": <obj>,
               "cantidad": 2, "unidades": 24, "precio": 480.00, "subtotal": 960.00} ],
  "total": 960.00,
  "unidades_totales": 24,
}
```

El **vuelto** se calcula en pantalla con JavaScript (`monto recibido − total`); no se envía ni se guarda.

### 9.7 Caja (`caja`)

| Pantalla / acción | URL | `name` | Plantilla / parcial | Datos |
|---|---|---|---|---|
| Estado de caja (abre o muestra el turno) | `/caja/` | `caja:estado` | `caja/estado.html` | `caja` (o `None`), `resumen`, `movimientos`, `form_abrir` (campos `monto_inicial` y `turno` opcional), `form_movimiento` |
| Abrir caja | `POST /caja/abrir/` | `caja:abrir` | redirige a `caja:estado` | — |
| Agregar movimiento (HTMX) | `POST /caja/movimientos/nuevo/` | `caja:movimiento_crear` | `caja/partials/_movimientos.html` → `#movimientos-caja` | `movimientos`, `resumen`, `error` |
| Cerrar caja | `POST /caja/cerrar/` | `caja:cerrar` | `caja/cierre.html` | `resumen` (con `esperado`, `contado`, `diferencia`, totales por método) |
| Historial de cierres | `/caja/historial/` | `caja:historial` | `caja/historial.html` | `page_obj` |

### 9.8 Reportes (`reportes`)

| Pantalla | URL | `name` | Plantilla | Datos |
|---|---|---|---|---|
| Menú de reportes | `/reportes/` | `reportes:inicio` | `reportes/inicio.html` | — |
| Ventas | `/reportes/ventas/?desde=&hasta=&agrupar=dia\|semana\|mes` | `reportes:ventas` | `reportes/ventas.html` | `filas`, `totales`, `grafico` (`etiquetas`, `valores`), `form_filtros` |
| Exportar ventas | `/reportes/ventas/exportar/?formato=xlsx\|pdf&...` | `reportes:ventas_exportar` | descarga de archivo | — |
| Compras, inventario valorizado, ganancias, vencimientos, productos más vendidos | `/reportes/<nombre>/` y `/reportes/<nombre>/exportar/` | `reportes:<nombre>`, `reportes:<nombre>_exportar` | `reportes/<nombre>.html` | `filas`, `totales`, `form_filtros` |

### 9.9 Auditoría (`auditoria`)

| Pantalla | URL | `name` | Plantilla | Datos |
|---|---|---|---|---|
| Bitácora | `/auditoria/?usuario=&entidad=&desde=&hasta=` | `auditoria:lista` | `auditoria/lista.html` | `page_obj`, filtros |

### 9.10 Convenciones HTMX para el frontend

- **Token CSRF:** en `base.html`, `<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>`. Con eso todas las peticiones HTMX POST quedan protegidas.
- **Errores de negocio:** el servidor responde **422** con el mismo fragmento más el mensaje en `error`. HTMX por defecto no reemplaza respuestas 4xx; se habilita una vez en `frontend/static/js/app.js`:

```javascript
document.body.addEventListener("htmx:beforeSwap", (e) => {
  if (e.detail.xhr.status === 422) {   // error de negocio: mostrar el fragmento
    e.detail.shouldSwap = true;
    e.detail.isError = false;
  }
});
```

- **Buscador de productos** en la venta: `hx-get="{% url 'ventas:buscar' %}" hx-trigger="keyup changed delay:200ms" hx-target="#lista-productos"`.
- **IDs de destino fijos:** `#carrito`, `#lista-productos`, `#presentaciones`, `#atributos`, `#lineas-compra`, `#movimientos-caja`, `#mensajes`. No renombrarlos sin avisar al backend.
- Los fragmentos (`_*.html`) deben poder dibujarse **solos**: reciben todo por contexto, sin depender de la página que los contiene.
- Los botones de acciones que solo puede ver el dueño se ocultan con `{% if "ver_costos" in permisos %}...{% endif %}` (el backend igual los bloquea).

### 9.11 Pantallas clave: comportamiento esperado

Los **mockups interactivos** están en `docs/mockups/` (`pantalla_venta.html` y `pantalla_caja.html`). Se abren con doble clic en el navegador y funcionan solos. No son código final (no usan Django ni la plantilla elegida), pero fijan la distribución y el comportamiento que debe respetar el frontend. Los datos que muestran son de ejemplo.

**Venta (POS)** — `frontend/templates/ventas/pos.html`

- Dos columnas: **productos** a la izquierda y **venta actual** a la derecha. En pantalla angosta pasa a una sola columna.
- Menú superior con las secciones y, a la derecha, el estado del turno de caja (*"Caja abierta desde las 08:00"* o *"Sin turno abierto"*).
- Lista de productos: buscador por nombre o categoría; cada producto muestra categoría, stock en unidades y el precio "desde" de su primera presentación; insignias **"Stock bajo"** y **"Vence pronto"**.
- Tocar un producto agrega una línea con la presentación "Unidad"; si esa línea ya existe, aumenta su cantidad.
- Cada línea muestra: nombre, subtotal, **lote que se descontará** (código y vencimiento), cuántas unidades descuenta, selector de presentación (con su precio), cantidad (entero ≥ 1) y botón para quitarla.
- Pie de la venta: unidades a descontar, **total** destacado, método de pago, monto recibido y vuelto (solo si es efectivo), y los botones **"Confirmar venta"** y **"Vaciar"**.
- Mensajes de error visibles: carrito vacío · stock insuficiente (con las unidades que quedan) · monto recibido menor al total.
- Al confirmar: mensaje de éxito con el total y las unidades descontadas; el carrito se vacía y el stock mostrado se actualiza.
- El mockup usa un solo método de pago; el sistema real admite **varios por venta** (RN-14).
- Recomendado: el foco inicia en el buscador; `Enter` agrega el primer resultado; un lector de código de barras actúa como teclado y busca por `codigo`.

**Caja** — `frontend/templates/caja/estado.html` y `caja/cierre.html`

- **Sin turno abierto:** formulario "Abrir caja" con el monto inicial en efectivo (y el turno, opcional).
- **Con turno abierto:** tarjetas de resumen (monto inicial, ventas en efectivo, ventas con QR, transferencias, ingresos extra, egresos); el **efectivo esperado** destacado con su fórmula; lista de movimientos con hora, concepto y monto (ingreso en verde con "+", egreso en rojo con "−"); formulario para agregar movimiento (tipo, monto, concepto); sección **"Cerrar caja"** con el monto contado.
- **Cierre:** resumen con efectivo esperado, contado y **diferencia** con insignia (*Cuadra* en verde, *Sobra* en amarillo, *Falta* en rojo), totales por método de pago y botón "Abrir nuevo turno".
- Mensajes de error visibles: monto inicial vacío o negativo · monto de movimiento ≤ 0 · concepto vacío · monto contado vacío o negativo.

**Guía visual común**

- Textos en español, primera letra en mayúscula solo al inicio de la frase, sin emojis.
- Color con significado: verde = correcto, amarillo = advertencia, rojo = error o falta.
- Botones con verbo: "Confirmar venta", "Cerrar caja", "Agregar movimiento".
- El dinero siempre con `{{ MONEDA_SIMBOLO }}` y dos decimales.

### 9.12 Integración de la plantilla del frontend

Se aplica una sola vez, cuando se confirma la plantilla (por defecto AdminLTE). Hacerlo **antes** de construir las pantallas de las demás fases evita reescribir clases después, porque cada plantilla nombra sus piezas de forma distinta.

**Criterios para elegir una plantilla**

1. HTML con **Bootstrap** (mejor Bootstrap 5). Las hechas para React, Angular o Vue no sirven en este proyecto.
2. **Licencia que permita uso comercial** y entregarla al cliente. Confirmarlo en la página de descarga y marcarlo en el registro de la sección 3.
3. Debe traer menú (lateral o superior), tarjetas, tablas, formularios, alertas y una pantalla de login.
4. Todos sus archivos deben poder guardarse **dentro del proyecto**: el sistema funciona sin internet.
5. Liviana: sin cientos de páginas de demostración.

**Qué se copia y qué no**

| Se copia a `frontend/static/vendor/<nombre>/` | No se copia |
|---|---|
| Carpetas de CSS, JS, fuentes e imágenes que realmente se usan | Páginas de demostración (`.html` de ejemplo), documentación y archivos de desarrollo |

**Pasos**

1. Descargar la plantilla y revisar qué trae.
2. Copiar solo sus recursos (CSS, JS, fuentes, imágenes) a `frontend/static/vendor/<nombre>/`.
3. **Quitar las dependencias de internet.** Buscar `http://` y `https://` dentro de los archivos usados (Google Fonts, iconos y librerías cargadas por CDN), descargar esos recursos y enlazarlos de forma local. Probar con el internet desconectado.
4. Convertir la página en blanco o inicial de la plantilla ("starter") en `frontend/templates/base.html`. Se conserva su estructura (cabecera, menú, zona de contenido) y se hacen tres cambios: las rutas de CSS y JS pasan a `{% static %}`, el título a un bloque y la zona central a otro bloque:

```html
{% load static %}
<link rel="stylesheet" href="{% static 'vendor/adminlte/css/adminlte.min.css' %}">
<link rel="stylesheet" href="{% static 'css/app.css' %}">
...
<title>{% block titulo %}{{ NOMBRE_NEGOCIO }}{% endblock %}</title>
...
{% block contenido %}{% endblock %}
...
<script src="{% static 'vendor/adminlte/js/adminlte.min.js' %}"></script>
<script src="{% static 'js/app.js' %}"></script>
```

5. Pasar el menú de la plantilla a `frontend/templates/components/_menu.html`, con los enlaces escritos como `{% url 'ventas:pos' %}` y la opción activa marcada según la app actual:

```html
<a class="nav-link {% if request.resolver_match.app_name == 'ventas' %}active{% endif %}"
   href="{% url 'ventas:pos' %}">Venta</a>
```

6. Mostrar los mensajes (éxito, error, aviso) en `components/_mensajes.html` con las alertas de la plantilla, manteniendo el contenedor con `id="mensajes"`.
7. Reemplazar `registration/login.html` con la pantalla de login de la plantilla (sigue extendiendo de `base.html` o de una base mínima sin menú).
8. Guardar **HTMX, Chart.js y Tom Select** en `frontend/static/vendor/`, junto a la plantilla. Si la plantilla incluye jQuery, no hay conflicto.
9. Mantener `frontend/static/css/app.css` solo para estilos propios; no se editan los archivos de la plantilla.
10. Registrar en la sección 3 el nombre, la versión y la carpeta, y marcar como resuelta la decisión pendiente de la sección 15.

**Reglas**

- Una sola plantilla y una sola versión de Bootstrap en todo el proyecto.
- Los **nombres del contrato** (URLs, `name`, archivos de plantilla, IDs HTML como `#carrito` y `#lista-productos`, variables de contexto) **no cambian** por usar la plantilla: la plantilla solo cambia el aspecto.
- Nada se carga desde internet; si algo se rompe sin conexión, es un error de integración.

**Adaptar los mockups** (`docs/mockups/`)

Los mockups usan estilos propios y no la plantilla. Al construir las pantallas reales se debe:

1. Reconstruir la distribución con las piezas de la plantilla (tarjetas, tablas, botones, formularios), respetando el orden, los textos y los mensajes del mockup.
2. Cambiar los datos y cálculos de ejemplo por datos reales del backend, y las acciones (agregar al carrito, confirmar venta, agregar movimiento) por llamadas HTMX según la sección 9.
3. Conservar el comportamiento fijado en 9.11: mensajes de error, lote que se descuenta, vuelto y diferencia de caja.

**Lista de verificación al terminar la integración**

- [ ] El login y la pantalla de inicio se ven bien con el **internet desconectado**.
- [ ] La consola del navegador no muestra archivos faltantes (404) ni errores de JavaScript.
- [ ] El menú marca la opción activa y todos sus enlaces usan `{% url %}`.
- [ ] Los mensajes de éxito y error se muestran con el estilo de la plantilla.
- [ ] La página se ve bien en pantalla ancha y en pantalla angosta.
- [ ] `base.html`, `_menu.html`, `_mensajes.html` y `login.html` están adaptados y el resto de pantallas heredan de `base.html`.

**Errores comunes**

- Mezclar dos plantillas o dos versiones de Bootstrap.
- Dejar enlaces a CDN, de modo que sin internet el sistema se ve roto.
- Copiar la plantilla completa, con todas sus demos, dentro del proyecto: el instalador pesa más y se confunde qué se usa.
- Elegir una plantilla de pago cuya licencia no permita entregarla al cliente.

**Mensaje sugerido para el agente**

> La plantilla elegida es **[nombre y versión]** y está en `frontend/static/vendor/[carpeta]/`. Intégrala siguiendo la sección 9.12: convierte su página inicial en `base.html`, adapta `_menu.html`, `_mensajes.html` y `registration/login.html`, verifica que no cargue nada desde internet y que no cambie ningún nombre del contrato de la sección 9. Después sigue el plan de trabajo.

---

## 10. Roles y permisos

Hay dos roles iniciales. Cada rol es un conjunto de permisos, y cada pantalla o acción exige un permiso concreto.

### Permisos

| Código | Qué permite |
|---|---|
| `vender` | Usar la pantalla de venta |
| `gestionar_caja` | Abrir, mover y cerrar **su propia** caja |
| `ver_stock` | Ver el stock, los lotes y las alertas |
| `gestionar_catalogo` | Crear y editar categorías, productos, presentaciones y atributos; cambiar precios |
| `gestionar_compras` | Registrar compras y proveedores |
| `ajustar_inventario` | Registrar ajustes y mermas |
| `ver_costos` | Ver costos de compra y ganancias |
| `ver_reportes` | Ver y exportar reportes |
| `ver_historial_caja` | Ver el historial de cierres de todos los usuarios |
| `gestionar_usuarios` | Crear usuarios y asignar roles |
| `ver_auditoria` | Ver la bitácora |
| `respaldar` | Crear y ver respaldos |

### Matriz de roles

| Permiso | Dueño | Vendedor |
|---|:---:|:---:|
| `vender` | ✔ | ✔ |
| `gestionar_caja` | ✔ | ✔ |
| `ver_stock` | ✔ | ✔ |
| `gestionar_catalogo` | ✔ | |
| `gestionar_compras` | ✔ | |
| `ajustar_inventario` | ✔ | |
| `ver_costos` | ✔ | |
| `ver_reportes` | ✔ | |
| `ver_historial_caja` | ✔ | |
| `gestionar_usuarios` | ✔ | |
| `ver_auditoria` | ✔ | |
| `respaldar` | ✔ | |

Los roles y permisos iniciales se crean en la primera ejecución con un comando idempotente (`cargar_datos_iniciales`), que usa `get_or_create` para que correrlo dos veces no duplique nada.

### Cómo se aplican

**En el backend** (`apps/core/permissions.py`, por crear): un decorador que revisa el permiso antes de ejecutar la vista. El superusuario siempre pasa.

```python
@login_required
@permiso_requerido("gestionar_compras")
def compra_crear(request):
    ...
```

Si el usuario no tiene el permiso, recibe una página 403 con un mensaje claro: *"No tienes permiso para esta acción."*

**En el frontend:** el context processor de `core` agrega la variable `permisos` (lista de códigos del usuario; se añade a `context_processors.py` cuando exista el modelo `Rol`). Las plantillas ocultan lo que no corresponde:

```html
{% if "ver_costos" in permisos %}
  <td>{{ MONEDA_SIMBOLO }} {{ lote.costo_unitario|floatformat:2 }}</td>
{% endif %}
```

Ocultar en pantalla **no es seguridad**: el backend siempre vuelve a comprobar el permiso.

### Otras medidas de seguridad

- Todas las pantallas exigen inicio de sesión, excepto el login y el primer uso.
- Protección CSRF activa en todos los formularios y peticiones HTMX.
- Contraseñas con validadores de Django (largo mínimo y contraseñas comunes) y almacenadas con hash.
- `DEBUG = False` en el programa instalado; `SECRET_KEY` única por instalación.
- La sesión expira según `SESSION_COOKIE_AGE`.
- Las operaciones sensibles (cambio de precio, ajuste, cierre de caja) quedan en la bitácora con el usuario.

---

## 11. Reportes y exportación

### Reportes

| Reporte | Filtros | Columnas | Permiso |
|---|---|---|---|
| Ventas por período | desde, hasta, agrupar por día / semana / mes | período, cantidad de ventas, total | `ver_reportes` |
| Ventas por método de pago | desde, hasta | método, cantidad, total | `ver_reportes` |
| Productos más vendidos | desde, hasta, categoría | producto, unidades, total | `ver_reportes` |
| Compras | desde, hasta, proveedor | fecha, proveedor, total | `ver_reportes` + `ver_costos` |
| Inventario valorizado | categoría | producto, stock, costo, valor | `ver_reportes` + `ver_costos` |
| Ganancias | desde, hasta, categoría | producto, ventas, costo, ganancia | `ver_reportes` + `ver_costos` |
| Vencimientos | días | producto, lote, vence, stock | `ver_stock` |
| Cierres de caja | desde, hasta, usuario | fecha, turno, usuario, esperado, contado, diferencia | `ver_historial_caja` |

### Reglas de exportación

1. **Lo exportado es exactamente lo que se ve en pantalla.** La vista de pantalla y la de exportación llaman a la misma función de `reportes/services.py`; solo cambia cómo se entrega el resultado.
2. **Excel** (`openpyxl`): encabezado en negritas, ancho de columnas ajustado, formato de moneda con 2 decimales y fila de totales al final.
3. **PDF** (`reportlab`): encabezado con `NOMBRE_NEGOCIO`, título del reporte, rango de fechas, tabla y número de página.
4. Nombre del archivo con el rango: `ventas_2026-10-01_a_2026-10-31.xlsx`.
5. Los filtros se validan: `desde` no puede ser posterior a `hasta`, y el rango máximo es de 366 días.
6. Los archivos se generan en memoria y se descargan; no se guardan en el servidor.
7. Subir a Google Drive u otra nube es un paso manual del usuario. **Los reportes sirven para consultar, no como respaldo** (ver sección 12).

Ubicación del código: lógica en `backend/apps/reportes/services.py`, exportadores en `backend/apps/reportes/exportadores.py`, vistas en `views.py` y pantallas en `frontend/templates/reportes/`.

---

## 12. Respaldos, registros y pruebas

### Respaldos

Exportar a Excel o PDF **no reemplaza** un respaldo: de un reporte no se puede reconstruir el stock, los lotes ni los precios. Lo que protege al negocio es la copia de la base de datos.

| Medida | Cómo |
|---|---|
| Copia automática diaria | Tarea programada de Windows que ejecuta el programa con `--respaldo` |
| Segunda copia fuera del equipo | Apuntar `BACKUP_DIR` a una carpeta sincronizada con Google Drive y copiar también a un pendrive |
| Cantidad guardada | Las últimas `BACKUP_CONSERVAR` copias (30 por defecto) |
| Respaldo manual | Botón "Respaldar ahora" en `/sistema/respaldos/` |
| Prueba de restauración | Restaurar una copia en otro equipo **antes de entregar** y al menos una vez al mes |

Tarea programada (se crea una vez al instalar):

```
schtasks /Create /SC DAILY /ST 21:00 /TN "Respaldo Sistema Inventarios" /TR "\"C:\Program Files\SistemaInventarios\SistemaInventarios.exe\" --respaldo"
```

Mientras se desarrolla, `scripts/respaldo.py` hace lo mismo desde la línea de comandos.

**Cómo restaurar:** cerrar el programa, copiar el archivo de respaldo elegido sobre `db.sqlite3` en la carpeta de datos (`C:\ProgramData\SistemaInventarios\`) y abrir el programa.

### Registros (logs)

- Archivo `sistema.log` en `LOG_DIR`, con rotación automática (máximo 5 archivos de 1 MB).
- Nivel configurable con `LOG_LEVEL`.
- Se registran los errores inesperados con su detalle técnico. Al usuario solo se le muestra un mensaje claro, nunca el error técnico.
- Los errores de negocio (`ErrorDeNegocio`) **no** son fallos del sistema: se muestran al usuario y no se registran como error.

### Pruebas

Se ejecutan con `python manage.py test`. Cada servicio tiene como mínimo una prueba del caso correcto y una por cada error posible. Archivos en `backend/apps/<app>/tests/`.

| Servicio | Casos mínimos a probar |
|---|---|
| `registrar_venta` | venta correcta · sin caja abierta · stock insuficiente · pagos que no suman el total · presentación inactiva · descuenta unidades = cantidad × equivalencia |
| `descontar_stock_fefo` | sale primero el lote que vence antes · usa varios lotes si hace falta · no toca lotes vencidos · cantidad cero o negativa |
| `registrar_compra` | crea un lote por línea · costo negativo · cantidad cero · vencimiento en el pasado |
| `abrir_caja` | abre correctamente · segunda caja abierta del mismo usuario |
| `cerrar_caja` | cuadra · sobra · falta · caja ya cerrada · efectivo esperado correcto con ingresos y egresos |
| `ajustar_inventario` | ajuste válido · motivo vacío · deja cantidad negativa |
| `mover_categoria` | movimiento válido · se pone a sí misma como padre · se pone a un descendiente |
| Reportes | totales coinciden con las ventas · rango de fechas inválido |

---

## 13. Empaquetado y entrega

### Qué hace `desktop/launcher.py` al abrir el programa

1. Define `ENV_FILE` (`C:\ProgramData\SistemaInventarios\.env`) y `DJANGO_SETTINGS_MODULE=config.settings.produccion`.
2. Si no existe el `.env`, lo crea con una `SECRET_KEY` nueva y los valores por defecto.
3. Crea las carpetas de datos, respaldos y logs.
4. Aplica las migraciones pendientes (`migrate`).
5. Ejecuta `cargar_datos_iniciales` (roles, permisos, métodos de pago). Es idempotente.
6. Si no hay usuarios, el sistema abre la pantalla de primer uso para crear al dueño.
7. Inicia `waitress` en `HOST:PORT` en un hilo aparte.
8. Abre la ventana (`pywebview`). Si no puede, abre el navegador predeterminado en la misma dirección.
9. Si se ejecutó con `--respaldo`, solo crea la copia de seguridad y termina, sin abrir ventana.

### Construcción

1. En un equipo Windows de 64 bits, con la misma versión de Python usada en el desarrollo (3.11, 3.12 o 3.13) y `requirements-desktop.txt` instalado.
2. `python manage.py collectstatic` (junta los archivos de `frontend/static/` en `staticfiles/`).
3. `pyinstaller desktop/sistema.spec` en modo carpeta (`--onedir`), incluyendo como datos las carpetas `frontend/` y `staticfiles/`.
4. Compilar `desktop/installer/setup.iss` con Inno Setup para generar `Instalador_Sistema_Inventarios.exe`.

### Reglas del instalador

- Muestra las políticas o términos de uso (`politicas.txt`) para aceptar.
- Instala el programa en `Archivos de programa` y crea el ícono en el escritorio.
- **Los datos no van en la carpeta del programa.** La base, los respaldos, los logs y el `.env` viven en `C:\ProgramData\SistemaInventarios\`, para que sobrevivan a las actualizaciones.
- **El desinstalador no borra los datos** (salvo que el usuario lo pida expresamente).
- Crea la tarea programada del respaldo diario.
- Una actualización es instalar la versión nueva encima: los datos se conservan y las migraciones se aplican al abrir.

### Compatibilidad

Windows 10 y 11 de 64 bits (Windows 11 recomendado). No requiere Python instalado. La ventana usa WebView2; si falta, abre el navegador.

### Antes de entregar

- [ ] Probar el instalador en máquinas virtuales limpias de Windows 10 y de Windows 11.
- [ ] Probar en la laptop real del cliente, con el antivirus activo.
- [ ] Explicar al cliente el aviso "Windows protegió su equipo" (el instalador no está firmado): *Más información → Ejecutar de todas formas*.
- [ ] Verificar el respaldo automático y restaurar una copia de prueba.
- [ ] Capacitar: venta, cierre de caja, compra con lote y lectura de reportes.
- [ ] Entregar una guía corta de uso con capturas y el contrato firmado en dos ejemplares.

---

## 14. Plan de trabajo

Orden recomendado. La **caja va antes de la venta** porque no se puede vender sin caja abierta (RN-10).

### Definición de "terminado" para cada función

1. Modelo y migración creados.
2. Servicio con docstring de `Pasos:` y validaciones, siguiendo la sección 6.
3. Pruebas del caso correcto y de cada error.
4. Vista y URL con el nombre acordado en la sección 9.
5. Plantilla en el archivo indicado en la sección 9.
6. La entrada correspondiente en la sección 9 está actualizada.

### Fases

- [ ] **Fase 0 — Preparación:** elegir la plantilla Bootstrap e integrarla siguiendo la sección 9.12 (queda lista en `frontend/templates/base.html`); crear `backend/.env`; iniciar git; crear `core/exceptions.py`, `core/validators.py` y `core/permissions.py`.
- [ ] **Fase 1 — Base de datos:** `models.py` de todas las apps, migraciones, `admin.py`, comando `cargar_datos_iniciales` (roles, permisos, métodos de pago).
- [ ] **Fase 2 — Usuarios y roles:** pantallas de usuarios y roles, decorador `permiso_requerido`, variable `permisos` en las plantillas.
- [ ] **Fase 3 — Catálogo:** categorías (árbol), productos, presentaciones, atributos y proveedores.
- [ ] **Fase 4 — Compras y lotes:** registrar compra, generar lotes y movimientos de entrada.
- [ ] **Fase 5 — Caja:** abrir, movimientos y cerrar con diferencia.
- [ ] **Fase 6 — Venta (POS):** carrito, búsqueda, presentaciones, pagos, descuento por lotes (FEFO) y confirmar.
- [ ] **Fase 7 — Inventario y alertas:** stock, lotes, ajustes, mermas, stock bajo y por vencer.
- [ ] **Fase 8 — Reportes y exportación:** reportes de la sección 11 con Excel y PDF.
- [ ] **Fase 9 — Auditoría, respaldo y panel de inicio.**
- [ ] **Fase 10 — Empaquetado:** `launcher.py`, PyInstaller e instalador; pruebas en máquinas limpias.
- [ ] **Fase 11 — Entrega:** pruebas con datos reales del cliente, capacitación, contrato y respaldo verificado.

### Si el tiempo aprieta

El núcleo mínimo para empezar a usarlo es: fases 0 a 6 más los reportes de ventas (fase 8) y el respaldo. La auditoría detallada, los reportes secundarios y el instalador pulido pueden entregarse en una segunda versión. Plan B de entrega: instalar Python y el proyecto en la laptop del cliente con un acceso directo (`.bat`) que inicie el sistema, y hacer el instalador después.

---

## 15. Decisiones pendientes y fuera de alcance

### Decisiones ya tomadas

| Decisión | Resultado |
|---|---|
| Clase `Caja` | Se mantiene una sola clase `Caja` (un turno de caja) con campo opcional `turno`. No se crea `TurnoCaja` porque hay una sola vendedora; se separa más adelante si aparecen varias cajas físicas |

### Por decidir antes de programar

| # | Decisión | Opciones | Efecto |
|---|---|---|---|
| 1 | RN-07: lotes vencidos | No se venden (propuesta) o se permite venderlos con advertencia | Confirmar con el cliente |
| 2 | Cierre de caja "a ciegas" | El vendedor no ve el efectivo esperado hasta ingresar lo contado | Más control; cambio pequeño en `caja/estado.html` |
| 3 | Plantilla del frontend | AdminLTE, Tabler u otra basada en Bootstrap | Define el diseño de `base.html`. Pasos de integración en la sección 9.12 |
| 4 | Moneda y formato | `Bs` con 2 decimales (por defecto) | Se cambia en el `.env` |
| 5 | Stock mínimo por defecto y días de alerta de vencimiento | 5 unidades y 30 días (por defecto) | Se cambia en el `.env` |

### Ambigüedades registradas durante fase 0 (sin decisiones de negocio nuevas)

1. La presentación «Unidad» es la entrada predeterminada del POS, pero no es
   obligatoria en todos los productos: definir qué hacer si falta o está inactiva.
2. Se permite precio cero y se exigen pagos positivos: definir el tratamiento de
   una venta cuyo total sea cero.
3. Distinguir el carrito serializable de sesión, el contexto enriquecido para HTML
   y las líneas con identificadores que recibe `registrar_venta`.
4. Completar contratos de rutas/exportación para ventas por método y cierres;
   alinear filtros de reportes con las firmas de los servicios.
5. Aclarar la excepción de acceso del vendedor al reporte de vencimientos mediante
   `ver_stock` frente a RN-20.
6. El registro mínimo de auditoría debe estar disponible para cambios de precio
   y cierres antes de la pantalla de bitácora de fase 9.
7. Definir si fecha y observación se reciben al registrar una compra; la firma
   documentada del servicio no las incluye.
8. El diagrama conserva `nombre` y `activo` para Usuario: prevalece 7.10,
   sin agregar esos campos. Diagrama pendiente de sincronizar en fase 1.
9. El ejemplo FEFO requiere comprobar concurrencia real sobre SQLite;
   no dar por garantizado bloqueo por fila solo por usar `select_for_update`.

La especificación de la raíz es la referencia solicitada. Su copia en `docs/`
se mantiene idéntica en este cambio para no dejar instrucciones contradictorias.
Los valores por defecto ya autorizados al inicio de este documento se mantienen.

### Fuera de alcance y cómo se agregarían después

| Funcionalidad | Cómo se agregaría sin rehacer el sistema |
|---|---|
| Anulaciones y devoluciones | Estado en `Venta` (ACTIVA / ANULADA) y un movimiento de ENTRADA que devuelva las unidades al lote; queda en bitácora |
| Flete y costo real de compra | Campo `costo_adicional` en `Compra`, repartido entre los lotes |
| Clientes y crédito (fiado) | Modelo `Cliente`, relación opcional en `Venta` y un método de pago "Crédito" |
| Facturas o recibos | Módulo aparte que se apoya en `Venta` y `Pago` |
| Varias cajas físicas o relevos entre empleados sobre una misma caja | Renombrar la clase `Caja` actual a `TurnoCaja`, crear la clase `Caja` (registradora) y enlazar los turnos existentes a una "Caja principal" con una migración de datos |
| Uso desde el celular o en la nube | Mantener la lógica en `services.py` y mover la base a PostgreSQL; la separación en capas ya lo permite |
| Historial de precios | Consulta sobre `LogAuditoria` o una tabla `HistorialPrecio` |

---

*Fin del documento. Cada vez que se agregue una pantalla, un modelo o una variable de entorno, se actualiza la sección correspondiente (4, 5, 7, 8 o 9) en el mismo cambio.*
