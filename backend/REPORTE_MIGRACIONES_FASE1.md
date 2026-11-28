# Reporte de Aplicación: Migraciones de Integridad Fase 1

**Fecha:** 2026-10-24  
**Base de datos:** `backend/datos/db.sqlite3`

---

## 1. Contexto

Al ejecutar `python manage.py runserver`, el servidor falló con el error:

```text
ModuleNotFoundError: No module named 'apps.caja.forms'
```

Un agente anterior (Codex) había preparado y validado las migraciones de integridad de Fase 1 en **copias aisladas**, pero no las había aplicado a la base real. Mi tarea fue completar esa aplicación de forma segura.

---

## 2. Estado previo al trabajo

### Migraciones pendientes (detectadas con `showmigrations`)

| Aplicación | Migración | Estado |
|---|---|---|
| `caja` | `0002_integridad_fase1` | ❌ Sin aplicar |
| `catalogo` | `0002_integridad_fase1` | ❌ Sin aplicar |
| `compras` | `0002_integridad_fase1` | ❌ Sin aplicar |
| `inventario` | `0002_integridad_fase1` | ❌ Sin aplicar |
| `usuarios` | `0003_integridad_fase1` | ❌ Sin aplicar |
| `ventas` | `0002_integridad_fase1` | ❌ Sin aplicar |

### Operaciones planeadas (verificadas con `migrate --plan`)

- `caja`: Alterar campo `monto_contado`, crear constraint `caja_monto_contado_no_negativo`
- `catalogo`: Crear constraint `presentacion_precio_no_negativo`
- `compras`: Cambiar `Meta` en `DetalleCompra`, crear constraints de costos y subtotales no negativos
- `inventario`: Crear constraint `lote_costo_no_negativo`
- `usuarios`: Cambiar `Meta.ordering` en `Usuario`
- `ventas`: Cambiar `Meta` en `DetalleVenta`, `DetalleVentaLote`, `Pago`; crear constraints de precio y subtotal no negativos

---

## 3. Procedimiento ejecutado

### Paso 1 — Verificación inicial del sistema

```powershell
python manage.py check
```
**Resultado:** `System check identified no issues (0 silenced).`

---

### Paso 2 — Respaldo de la base real

Se copió `datos/db.sqlite3` a una ubicación permanente fuera del repositorio:

```powershell
Copy-Item datos\db.sqlite3 "$env:USERPROFILE\Documents\respaldo_db_inventarios_20261024_094836.sqlite3"
```

**Respaldo generado:**

| Ítem | Valor |
|---|---|
| Archivo | `C:\Users\Jose\Documents\respaldo_db_inventarios_20261024_094836.sqlite3` |
| Tamaño | 458,752 bytes |
| SHA-256 | `0221D6E7353EAA17FEB388C87371C6BA987504EF26FDC1D5C17E5EB4544349AF` |

---

### Paso 3 — Verificación de integridad del respaldo

Se ejecutó un script Python directamente sobre el archivo de respaldo:

```python
PRAGMA integrity_check  → ok
PRAGMA foreign_key_check → OK (sin violaciones)
usuarios_usuario         → [(1, 'Jose', is_superuser=True)]
```

✅ Respaldo válido e íntegro.

---

### Paso 4 — Aplicación de migraciones a la base real

```powershell
python manage.py migrate
```

**Salida:**

```text
Running migrations:
  Applying caja.0002_integridad_fase1        ... OK
  Applying catalogo.0002_integridad_fase1    ... OK
  Applying compras.0002_integridad_fase1     ... OK
  Applying inventario.0002_integridad_fase1  ... OK
  Applying usuarios.0003_integridad_fase1    ... OK
  Applying ventas.0002_integridad_fase1      ... OK
```

---

### Paso 5 — Verificaciones post-migración

#### 5a. `manage.py check`
```
System check identified no issues (0 silenced).
```

#### 5b. `makemigrations --check --dry-run`
```
No changes detected
```

#### 5c. Integridad de la base real

| Comprobación | Resultado |
|---|---|
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` | `OK` |
| Migraciones registradas | 32 |
| Usuario `Jose` (superusuario) | ✅ Presente |
| SHA-256 post-migrate | `FEAF2C119916C897B33BCCB2142ABA309A52957FCD7CF9833C22C88A22ED7E0A` |

**Tablas con datos (preservados sin cambios):**

| Tabla | Registros |
|---|---|
| `auth_permission` | 100 |
| `django_content_type` | 25 |
| `django_migrations` | 32 |
| `django_session` | 2 |
| `usuarios_permiso` | 12 |
| `usuarios_rol` | 2 |
| `usuarios_rol_permisos` | 15 |
| `usuarios_usuario` | 1 |
| `ventas_metodopago` | 3 |

#### 5d. Suite completa de pruebas

```powershell
python manage.py test
```

```
Ran 81 tests in 56.133s
OK
```

> Los warnings `PermissionDenied` en los logs son **esperados**: corresponden a las pruebas de regresión que verifican que el Admin bloquea correctamente la edición y borrado del historial de movimientos de caja.

---

## 4. Resultado final

| Verificación | Estado |
|---|---|
| Respaldo creado y verificado | ✅ |
| 6 migraciones de integridad aplicadas | ✅ |
| `manage.py check` | ✅ Sin incidencias |
| `makemigrations --check` | ✅ Sin cambios pendientes |
| Integridad de la base real | ✅ `ok` |
| Datos preservados | ✅ Sin cambios |
| 81 pruebas automatizadas | ✅ Todas aprobadas |
| Commits / push realizados | ❌ Ninguno (fuera del alcance) |

---

## 5. Estado actual

La base de datos real contiene ahora el esquema completo de Fase 1 con las restricciones de integridad monetaria. El servidor puede levantarse sin errores:

```powershell
cd backend
python manage.py runserver
```

El respaldo pre-migración se conserva en:
```
C:\Users\Jose\Documents\respaldo_db_inventarios_20261024_094836.sqlite3
```
