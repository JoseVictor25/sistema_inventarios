# Fase 6 — Ventas / POS: Resultados de Implementación

**Fecha:** 2026-10-25
**Estado:** Correcciones implementadas y verificadas en entorno temporal. **Fase abierta a la espera de la revisión visual del usuario.**
**Rama:** `main`
**Entorno:** Windows 11, Python 3.13.7, Django 5.x, SQLite.

---

## 1. Diagnóstico y corrección de las observaciones del usuario

Durante la inspección visual inicial, el usuario reportó tres observaciones que fueron diagnosticadas y resueltas:

### 1.1 Corrección del cálculo de cambio o vuelto
- **Diagnóstico:** En la plantilla anterior, el total se renderizaba formateado con el locale español (`Bs 540,00`). En `pos.js`, la expresión regular `replace(/[^0-9.]/g, "")` eliminaba la coma decimal, convirtiendo el texto en `"54000"` (cincuenta y cuatro mil bolivianos). Al ingresar recibido 600,00 Bs, la operación `Math.max(0, 600 - 54000)` arrojaba `0,00` Bs.
- **Solución implementada:**
  1. Se agregó el atributo explícito `data-total="{{ carrito.total|stringformat:'.2f' }}"` en el DOM para desacoplar el cálculo matemático del formato visual.
  2. Se estandarizó la aritmética monetaria en `pos.js` trabajando con números enteros de centavos (`centavos()` y `formatoMoneda()`), eliminando cualquier error de punto flotante.
  3. Se incorporó soporte para comas y puntos en el campo `recv` y montos de pago.
  4. El cambio se actualiza inmediatamente en el evento `input` y `change`.
  5. Caso verificado: Total 540,00 Bs, Efectivo recibido 600,00 Bs $\rightarrow$ **Cambio Bs 60,00**.

### 1.2 Interfaz de pagos mixtos (QR + Efectivo)
- **Diagnóstico:** El backend ya admitía pagos mixtos (`registrar_venta` procesa listas de pagos), pero la interfaz web solo presentaba un único selector de método.
- **Solución implementada:**
  1. Se implementó un contenedor dinámico `#lista-pagos` con soporte para añadir (`+ Añadir método`) y retirar filas de pago individuales.
  2. Cada fila permite seleccionar el método (`Efectivo`, `QR`, `Transferencia`), introducir el importe aplicado y agregar referencia de transacción para métodos electrónicos.
  3. Se agregó un bloque de resumen en tiempo real:
     - **Total cubierto:** Suma de montos asignados.
     - **Saldo pendiente:** Diferencia contra el total de la venta (muestra si falta cubrir o si excede el total).
  4. **Cálculo de vuelto restringido al efectivo:** Cuando hay un pago en efectivo involucrado, el vuelto se calcula estrictamente como:
     $$\text{Vuelto} = \max(0, \text{Efectivo recibido} - \text{Efectivo aplicado})$$
     Si el efectivo recibido es menor al aplicado, se muestra una alerta visual y el cambio queda en Bs 0,00.
  5. **Impedir métodos duplicados:** Se previene la selección del mismo método más de una vez tanto en el cliente como en `forms.leer_pagos` y `services.registrar_venta`.
  6. **Persistencia exacta:** El modelo `Pago` registra únicamente el importe aplicado a la venta (por ejemplo QR: 300 Bs y Efectivo: 240 Bs). El vuelto (10 Bs) no se persiste como pago ni afecta la caja negativamente.

### 1.3 Diagnóstico y verificación del aislamiento de Caja por usuario
- **Diagnóstico del caso observado:**
  1. Al iniciar el script `scripts/verificar_ventas_fase6.py`, la rutina de configuración previa ejecutaba:
     `caja_s.abrir_caja(vendedor, "100.00", "Turno Mañana", clave=uuid4())` para que la prueba automatizada de venta pudiera efectuarse.
  2. Cuando el usuario inició sesión como `dueno_fase6` y abrió una caja, abrió la caja perteneciente al Dueño.
  3. Al cerrar sesión e ingresar como `vendedor_fase6`, el POS mostró una caja abierta porque `vendedor_fase6` ya tenía su propio turno abierto por el script de prueba.
- **Comprobación de aislamiento:**
  1. La consulta en `views.pos` y `views._contexto_carrito` es estrictamente:
     `Caja.objects.filter(usuario=request.user, estado=Caja.EstadoCaja.ABIERTA).first()`.
  2. En `services.registrar_venta`:
     `caja = Caja.objects.filter(usuario=usuario, estado=Caja.EstadoCaja.ABIERTA).first()`.
  3. No se almacena ninguna referencia de caja en la sesión (`request.session`).
  4. Se movió la verificación de caja abierta al inicio de `registrar_venta` (Paso 2), garantizando que no se procesen líneas ni descuentos si el usuario no tiene su propio turno abierto.
  5. Se incorporó a las pruebas automatizadas y al script un usuario específico `cajero_sin_caja`:
     - Al entrar al POS, ve el aviso destacado `"⚠ Sin turno de caja abierto"` y el botón `"Confirmar venta"` deshabilitado.
     - Cualquier intento de POST directo a `/ventas/confirmar/` es rechazado con HTTP 422 y `ErrorDeNegocio: "Abre tu turno de caja antes de vender."`.
     - Se comprobó mediante prueba de regresión que teniendo el Dueño caja abierta y el Vendedor ninguna, el Vendedor no puede registrar ventas ni descontar inventario.

---

## 2. Funcionalidades implementadas y contratos vigentes

1. **Carrito en sesión (`carrito.py`):** Operaciones desacopladas con cálculo dinámico de equivalencias en unidades base y claves UUID de idempotencia.
2. **Búsqueda e interfaz POS:** Búsqueda en tiempo real con HTMX, distintivos visibles de stock (`Sin stock`, `Stock bajo`, `Vence pronto`) y asignación predeterminada a la primera presentación activa (D3).
3. **Cálculo monetario estricto:** Precisión con `Decimal` a dos decimales y centavos en Javascript. Ventas con total igual a cero rechazadas con `ErrorDeNegocio` (D4).
4. **Confirmación y FEFO:** Deducción en unidades base priorizando lotes con vencimiento más próximo y excluyendo vencidos (RN-06, RN-07). Registro inmutable de `DetalleVenta`, `DetalleVentaLote` y movimientos `SALIDA`.
5. **Pagos simples y mixtos:** Validación estricta de que la suma de pagos sea igual al total de venta (RN-14). Métodos duplicados rechazados.
6. **Asociación con Caja abierta:** Venta y pagos vinculados obligatoriamente al turno abierto del vendedor autenticado (RN-10).
7. **Consulta e inmutabilidad:** Historial de ventas paginado y detalle inmutable con protección de costos históricos (`ver_costos`).

---

## 3. Modelo y migración de idempotencia

### Modelo `OperacionVenta` (`backend/apps/ventas/models.py`)
- `clave`: UUID único.
- `usuario`: ForeignKey a Usuario (`PROTECT`).
- `huella`: Hash SHA-256 canónico de la solicitud (usuario, carrito normalizado, pagos y caja).
- `venta`: ForeignKey a Venta (`null=True, blank=True, PROTECT`).
- `creado_en`: DateTimeField auto_now_add.
- Restricciones: Índice compuesto `[usuario, -creado_en]`, unicidad en `clave`.

### Migración `0003_operacion_venta.py`
- Depende de `0002_integridad_fase1`.
- Creada y validada exclusivamente en bases SQLite temporales.
- **La base real `backend/datos/db.sqlite3` permanece intacta y sin migrar** (cumpliendo D1).

---

## 4. Pruebas automatizadas

Se ejecutó la suite completa sobre SQLite temporal:

```
Ran 243 tests in 152.701s
OK
```

- **211 pruebas de regresión (Fases 0 a 5):** Aprobadas al 100%.
- **32 pruebas de Fase 6:**
  - FEFO (ordenamiento, lotes sin vencimiento, exclusión de vencidos, stock insuficiente, rollback y concurrencia).
  - Aislamiento de Caja (Dueño con caja abierta y Vendedor sin caja: venta rechazada sin alterar stock ni pagos).
  - Pagos mixtos (QR + Efectivo, cálculo de vuelto exacto sin persistirlo en la base de datos).
  - Métodos de pago duplicados (rechazados en formulario y servicio).
  - Montos inválidos o negativos (rechazados).
  - Entradas con comas decimales (sanitizadas a `Decimal` exacto).
  - Idempotencia (misma clave con mismos datos, datos alterados, reintento con carrito vacío).
  - Seguridad, permisos (`vender`), protección CSRF e inmutabilidad.

---

## 5. Verificación HTTP aislada

Ejecutada mediante `scripts/verificar_ventas_fase6.py --pruebas --http`:

```
check: código 0
makemigrations: código 0
test: código 0 (243 pruebas aprobadas)
frontend: código 0
HTTP aislado aprobado: ciclo POS, carrito, confirmación, idempotencia, permisos y recursos locales.
Base real, .env y reportes intactos: True
```

Comprobaciones HTTP certificadas:
1. Ciclo completo de POS con `vendedor_fase6`.
2. Confirmación de venta simple e idempotencia.
3. Bloqueo y respuesta 422 para `cajero_sin_caja` al intentar vender sin turno abierto.
4. Rechazo con HTTP 403 para usuarios sin permiso `vender`.
5. Recursos frontend (CSS, JS, iconos) 100% locales sin dependencias externas.

---

## 6. Comando de verificación visual

Para iniciar el servidor de demostración temporal para la revisión manual:

```powershell
.\venv\Scripts\python.exe scripts/verificar_ventas_fase6.py --abrir
```

### Cuentas temporales disponibles para la prueba:
- **`dueno_fase6`** (Rol Dueño): Puede abrir su propia caja, ver historial de todas las cajas y consultar costos históricos de los lotes.
- **`vendedor_fase6`** (Rol Vendedor): Tiene su turno de caja abierto por el script. Permite probar inmediatamente ventas en efectivo, QR y pagos mixtos.
- **`cajero_sin_caja`** (Rol Vendedor): **SIN caja abierta**. Permite comprobar el distintivo `"⚠ Sin turno de caja abierto"`, el botón de confirmación deshabilitado y el rechazo en caso de intento de confirmación.

### Casos de prueba sugeridos en navegador:
1. **Verificar vuelto en efectivo:**
   - Iniciar sesión con `vendedor_fase6`.
   - Agregar "Colágeno hidrolizado 300g" (ej. 540,00 Bs).
   - En Efectivo recibido, ingresar `600` o `600,00`.
   - Comprobar que el vuelto indica inmediatamente **Bs 60.00**.
2. **Verificar pagos mixtos (QR + Efectivo):**
   - Con total de 540,00 Bs, cambiar el método de la primera fila a QR e ingresar 300,00 Bs.
   - Observar que el Saldo pendiente indica `Bs 240.00 (Falta)`.
   - Pulsar `+ Añadir método`; se creará una fila con Efectivo y monto pre-llenado en 240,00 Bs.
   - En Efectivo recibido, ingresar `250,00`.
   - Comprobar que el vuelto indica **Bs 10.00** (calculado únicamente sobre el efectivo aplicado).
   - Confirmar la venta y revisar en el detalle que se registraron los pagos QR=300 y Efectivo=240, sin registrar el vuelto como pago.
3. **Verificar aislamiento de Caja:**
   - Iniciar sesión como `cajero_sin_caja`.
   - Comprobar que en el encabezado se muestra `"⚠ Sin turno de caja abierto"` y no es posible confirmar ventas.

---

## 7. Archivos modificados en esta corrección

- `backend/apps/ventas/services.py`: Verificación de turno de caja antes de líneas, sanitización de comas y rechazo de métodos de pago duplicados.
- `backend/apps/ventas/forms.py`: Soporte de comas decimales, validación de montos positivos y rechazo de métodos duplicados en `leer_pagos`.
- `backend/apps/ventas/views.py`: Helper `_contexto_carrito` para garantizar la presencia de `caja` en todas las respuestas parciales HTMX.
- `frontend/templates/ventas/partials/_carrito.html`: Interfaz dinámica de pagos mixtos, resumen de cobertura, `data-total` exacto y aviso de caja cerrada.
- `frontend/static/js/pos.js`: Aritmética monetaria exacta en centavos, adición/eliminación de métodos de pago, cálculo de vuelto sobre efectivo aplicado y sincronización HTMX.
- `backend/apps/ventas/tests/test_fase6.py`: 5 nuevas pruebas automatizadas (aislamiento de caja, pagos mixtos sin guardar vuelto, métodos duplicados y sanitización de montos).
- `scripts/verificar_ventas_fase6.py`: Usuario `cajero_sin_caja` para comprobación automatizada de aislamiento y mensajes explicativos en `--abrir`.
