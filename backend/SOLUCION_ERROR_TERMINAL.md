# Reporte de Solución: Error de Base de Datos en Backend Django

## 1. Contexto del Problema

Al intentar iniciar sesión en el backend (`POST /login/?next=/`), el servidor arrojó una excepción HTTP 500 con el siguiente detalle de error en consola:

```text
sqlite3.OperationalError: no such column: usuarios_usuario.rol_id
django.db.utils.OperationalError: no such column: usuarios_usuario.rol_id
[24/Oct/2026 08:56:03] "POST /login/?next=/ HTTP/1.1" 500 253092
```

### Causa Raíz
El modelo `Usuario` en la aplicación `usuarios` fue actualizado para incluir una relación ForeignKey con el modelo `Rol` (`rol = models.ForeignKey(...)`). Dicho cambio generó el archivo de migración `0002_permiso_alter_usuario_options_rol_usuario_rol.py`, pero esta migración (y las de otras aplicaciones) aún no habían sido aplicadas sobre la base de datos `db.sqlite3`.

Cuando Django ejecutó la consulta de autenticación (`Usuario.objects.get(username=username)`), SQLite no encontró la columna física `rol_id` en la tabla `usuarios_usuario`.

---

## 2. Diagnóstico Realizado

### Paso 2.1: Inspección de Migraciones en `apps/usuarios/migrations/`
Se verificó el contenido del archivo de migración `0002_permiso_alter_usuario_options_rol_usuario_rol.py`, donde se constató la adición del campo:
```python
migrations.AddField(
    model_name='usuario',
    name='rol',
    field=models.ForeignKey(
        blank=True,
        help_text='Rol de negocio del usuario. Vacío en superusuarios.',
        null=True,
        on_delete=django.db.models.deletion.PROTECT,
        related_name='usuarios',
        to='usuarios.rol',
    ),
)
```

### Paso 2.2: Verificación de Estado de Migraciones
Se ejecutó el comando de comprobación:
```powershell
python manage.py showmigrations
```

**Resultado:**
Se detectaron múltiples migraciones sin aplicar (`[ ]`):
* `usuarios`: `[ ] 0002_permiso_alter_usuario_options_rol_usuario_rol`
* `auditoria`: `[ ] 0001_initial`
* `caja`: `[ ] 0001_initial`
* `catalogo`: `[ ] 0001_initial`
* `compras`: `[ ] 0001_initial`
* `inventario`: `[ ] 0001_initial`
* `ventas`: `[ ] 0001_initial`

### Paso 2.3: Validación del Plan de Migración
Se ejecutó:
```powershell
python manage.py migrate --plan
```
Se confirmó la lista de operaciones programadas sin conflictos de dependencias.

---

## 3. Acciones Ejecutadas

### Paso 3.1: Aplicación de Migraciones a la Base de Datos
Se ejecutó el comando para actualizar el esquema físico de SQLite:
```powershell
python manage.py migrate
```

**Salida obtenida:**
```text
Operations to perform:
  Apply all migrations: admin, auditoria, auth, caja, catalogo, compras, contenttypes, inventario, sessions, usuarios, ventas
Running migrations:
  Applying auditoria.0001_initial... OK
  Applying caja.0001_initial... OK
  Applying catalogo.0001_initial... OK
  Applying compras.0001_initial... OK
  Applying inventario.0001_initial... OK
  Applying usuarios.0002_permiso_alter_usuario_options_rol_usuario_rol... OK
  Applying ventas.0001_initial... OK
```

### Paso 3.2: Carga de Datos Iniciales (Seed Data)
Para asegurar que los roles requeridos por el sistema, los permisos y métodos de pago existieran en la base de datos, se corrió el comando de gestión idempotente:
```powershell
python manage.py cargar_datos_iniciales
```

**Salida obtenida:**
```text
Iniciando carga de datos iniciales...
  Permisos: 12 creados, 0 ya existían (Total: 12).
  Roles: 2 creados, 0 ya existían (Dueño, Vendedor).
  Métodos de pago: 3 creados, 0 ya existían (Efectivo, QR, Transferencia).
Carga de datos iniciales completada exitosamente.
```

### Paso 3.3: Verificación del Usuario Administrador
Se comprobó mediante el shell de Django que el usuario existente pudiera ser leído sin errores:
```powershell
python manage.py shell -c "from apps.usuarios.models import Usuario; print(list(Usuario.objects.values_list('username', 'rol__nombre', 'is_superuser')))"
```
**Resultado:**
```text
[('Jose', None, True)]
```
El usuario `Jose` fue recuperado exitosamente con permisos de superusuario.

### Paso 3.4: Ejecución de la Suite de Pruebas
Se ejecutaron todas las pruebas automatizadas del proyecto para asegurar integridad global:
```powershell
python manage.py test
```

**Resultado:**
```text
Ran 68 tests in 48.064s

OK
```
Todas las 68 pruebas pasaron sin errores.

---

## 4. Estado Actual y Recomendación

* La base de datos SQLite contiene ahora el esquema completo y actualizado.
* Para verificarlo en el entorno local:
  1. En la carpeta `backend/`, ejecutar:
     ```powershell
     python manage.py runserver
     ```
  2. Abrir en el navegador: `http://127.0.0.1:8000/login/`
  3. Ingresar las credenciales del usuario. El error 500 ya no ocurrirá.
