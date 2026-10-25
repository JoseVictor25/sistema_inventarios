# Resumen de Auditoría y Verificación Técnica — Fase 4: Compras y Lotes



**Proyecto:** `sistema_inventarios`

**Fecha:** 2026-10-25

**Rama:** `main`

**Estado:** Auditoría completada con 170 pruebas automatizadas aprobadas. Sin inconsistencias detectadas.



---



## 1. Objetivo de la Actividad



Realizar una auditoría técnica final y exhaustiva sobre la implementación del módulo de **Compras y Lotes (Fase 4)** antes de su cierre y versionado, evaluando:

1. La consistencia del cálculo del stock y la prevención de doble contabilización.

2. El comportamiento de idempotencia y concurrencia ante envíos simultáneos y manejo de excepciones.

3. La ejecución de la suite de pruebas en un entorno SQLite temporal y aislado.

4. El respeto estricto de las restricciones del proyecto (preservación de base real, `.env` y sin modificaciones de esquema no autorizadas).



---



## 2. Consistencia del Stock y Prevención de Doble Contabilización



### Análisis de la Especificación vs. Modelos

Se contrastó [ESPECIFICACION_SISTEMA.md](file:///c:/Users/Jose/Desktop/GROVER/sistema_inventarios/ESPECIFICACION_SISTEMA.md) con el código implementado:

- **Especificación (§1, RN-05, §7.10):**

  - El stock siempre se cuenta en unidades (**RN-01**).

  - Cada compra genera un lote por línea de detalle (**RN-05**).

  - El stock de un producto es la suma de `cantidad_actual` de sus lotes.

  - En §7.10, `stock_actual` está definido como una propiedad: `@property stock_actual -> suma de cantidad_actual de sus lotes`.

- **Implementación en el Modelo:**

  - En [apps/catalogo/models.py](file:///c:/Users/Jose/Desktop/GROVER/sistema_inventarios/backend/apps/catalogo/models.py#L93-L102), el modelo `Producto` **no posee una columna persistida en la base de datos** para el stock.

  - Se calcula dinámicamente mediante `@property`:

    ```python

    @property

    def stock_actual(self):

        resultado = self.lotes.aggregate(total=Sum("cantidad_actual"))

        return resultado["total"] or 0

    ```

- **Conclusión de Integridad:**

  - El stock se mantiene mediante una **única fuente de verdad**: los registros de `Lote.cantidad_actual`.

  - El servicio `registrar_compra` en [apps/compras/services.py](file:///c:/Users/Jose/Desktop/GROVER/sistema_inventarios/backend/apps/compras/services.py#L81) crea por cada línea:

    1. Un `DetalleCompra`.

    2. Un `Lote` (`cantidad_inicial = cantidad`, `cantidad_actual = cantidad`).

    3. Un `MovimientoInventario` inmutable de tipo `ENTRADA` (bitácora histórica).

  - Al no haber una columna redundante en la tabla `Producto`, **no existe riesgo de desincronización ni de doble contabilización**.



---



## 3. Idempotencia y Concurrencia



### Mecanismo Implementado

Para proteger el registro de compras frente a dobles clics o peticiones simultáneas sin modificar el esquema de base de datos:

1. **Token Criptográfico en Sesión (`compra_token`):**

   - Emitido por GET (`uuid.uuid4().hex`) y validado al recibir el POST.

   - Consumido y eliminado tras el registro exitoso (`request.session.pop("compra_token")`).

2. **Cerrojo Atómico en Memoria (`_lock_tokens` y `_tokens_en_proceso`):**

   - Implementado con `threading.Lock()` y un conjunto en [apps/compras/views.py](file:///c:/Users/Jose/Desktop/GROVER/sistema_inventarios/backend/apps/compras/views.py#L21-L23).

   - Bloquea peticiones simultáneas concurrentes que lleguen en el mismo milisegundo antes de que la sesión persista la eliminación del token.

   - La segunda solicitud detecta que el token ya está en proceso y es redirigida con advertencia sin invocar la transacción de compra.



### Evaluación de Límites Operativos

- **Entorno Multihilo (Aplicación de escritorio Windows con pywebview / Waitress / runserver):**

  - **Eficacia del 100%:** Los hilos comparten la memoria RAM del proceso, garantizando exclusión mutua total y evitando cualquier duplicación de compras o stock.

- **Entorno Multiproceso (Riesgo futuro en servidores Web con múltiples workers de Gunicorn/uWSGI):**

  - En despliegues multi-proceso de sistema operativo, la memoria no se comparte entre procesos.

  - **Propuesta de diseño:** Para despliegues distribuidos en fases posteriores, se recomienda incorporar una columna `idempotency_key = models.CharField(max_length=64, unique=True, null=True, blank=True)` en el modelo `Compra` o una tabla dedicada. No se realizaron cambios de esquema en esta fase respetando la directiva de no introducir migraciones.



### Liberación del Token y Manejo de Excepciones

- El bloque crítico está protegido por `try...finally`:

  ```python

  try:

      ...

  finally:

      with _lock_tokens:

          _tokens_en_proceso.discard(token)

  ```

- Ante cualquier error imprevisto (base de datos bloqueada, desconexión o fallo interno), el bloque `finally` se ejecuta **incondicionalmente**, liberando el token mediante `set.discard()` sin lanzar excepciones ni dejar bloqueos residuales en memoria.

- Si el formulario presenta errores de validación esperados o `ErrorDeNegocio`, la vista regenera automáticamente un nuevo token de sesión, permitiendo que el usuario corrija los datos y reenvíe el formulario sin quedar bloqueado.



---



## 4. Pruebas Automatizadas y Verificación Técnica



Todas las validaciones se ejecutaron con `venv/Scripts/python.exe` sobre bases SQLite temporales y aisladas:



| Suite / Verificación | Pruebas | Resultado | Observaciones |

|---|---|---|---|

| `test_fase4.py` (Compras y Concurrencia) | 23 | **OK (1.4s)** | Valida compras 1 y multi-línea, unicidad de lotes, rollback, concurrencia con `threading.Barrier` y visibilidad de costos (`ver_costos`). |

| Catálogo + Compras combinados | 78 | **OK (18.3s)** | Valida productos, categorías, presentaciones, proveedores y compras. |

| Suite General del Sistema | 170 | **OK (68.1s)** | 147 pruebas de fases previas (0 regresiones) + 23 de Fase 4. |

| `manage.py check` | — | **0 incidencias** | Configuración y modelos correctos. |

| `makemigrations --check --dry-run` | — | **No changes** | Esquema 100% consistente con las migraciones existentes. |

| `scripts/verificar_compras_fase4.py --http` | — | **Código 0** | 7 pantallas HTTP validadas, 12 recursos locales verificados y denegación de acceso al Vendedor (403). |



---



## 5. Control de Restricciones e Integridad de Archivos



Se verificaron los hashes criptográficos SHA-256 de los archivos críticos del proyecto:



| Archivo | Hash SHA-256 | Estado |

|---|---|---|

| `backend/.env` | `9BC65E53962E9CD7849EB41F2899DFA29D230DF7DCB217831793CA76BE8FC854` | **Intacto** |

| `backend/datos/db.sqlite3` | `40D61B7947251655E3AF6055FAB58130D29A24586B103AA62FF4D5B847E37F50` | **Intacto** |

| `backend/REPORTE_MIGRACIONES_FASE1.md` | `B5239FC7F134851BF32225F7363604D500449538690C2658A101105C7C257E53` | **Preservado sin cambios** |

| `backend/SOLUCION_ERROR_TERMINAL.md` | `8D907AD4BD5AB07E2F3799033A21E83C9A77AA7095E4C6CF520709D5E1EFAE26` | **Preservado sin cambios** |



- **Rama de trabajo:** `main`.

- **Control de versiones:** No se han realizado `git commit`, `git push` ni creado etiquetas `git tag`.

- **Alcance:** No se implementaron ventas ni funcionalidades de fases posteriores.



---



## 6. Conclusión y Próximos Pasos



El módulo de **Compras y Lotes (Fase 4)** ha superado todos los controles de consistencia, concurrencia y pruebas automatizadas:

- No existen fallas reales de lógica ni inconsistencias en el cálculo de stock.

- Las restricciones impuestas han sido respetadas al 100%.

- El código se encuentra listo para el cierre y posterior commit de la fase cuando lo autorices.
