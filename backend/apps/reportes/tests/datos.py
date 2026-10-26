"""Datos ficticios compartidos por pruebas y verificación aislada; nunca al inicio."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from django.core.management import call_command
from django.utils import timezone
from apps.usuarios.models import Usuario, Rol
from apps.catalogo.models import Categoria, Producto, Presentacion
from apps.compras.models import Proveedor
from apps.compras.services import registrar_compra
from apps.caja.services import abrir_caja, registrar_movimiento_caja, cerrar_caja
from apps.ventas.services import registrar_venta
from apps.ventas.models import MetodoPago


def crear_datos(password='Temporal-Reportes-2026!'):
    call_command('cargar_datos_iniciales', verbosity=0)
    dueno = Usuario.objects.create_user('dueno_fase8', password=password, rol=Rol.objects.get(nombre='Dueño'))
    vendedor = Usuario.objects.create_user('vendedor_fase8', password=password, rol=Rol.objects.get(nombre='Vendedor'))
    categoria = Categoria.objects.create(nombre='Naturales de demostración')
    hija = Categoria.objects.create(nombre='Subcategoría', padre=categoria)
    producto = Producto.objects.create(codigo='F8-01', nombre='Aceite de demostración', categoria=categoria)
    vacio = Producto.objects.create(codigo='F8-02', nombre='Sin existencias', categoria=hija)
    presentacion = Presentacion.objects.create(producto=producto, nombre='Tres unidades', unidades_equivalentes=3, precio_venta=Decimal('15'))
    unidad = Presentacion.objects.create(producto=producto, nombre='Unidad', unidades_equivalentes=1, precio_venta=Decimal('8'))
    proveedor = Proveedor.objects.create(nombre='Proveedor ficticio', tipo='EMPRESA')
    hoy = timezone.localdate()
    compra = registrar_compra(dueno, proveedor, [
        dict(producto_id=producto.pk, cantidad=5, costo_unitario=Decimal('2'), fecha_vencimiento=hoy + timedelta(days=5)),
        dict(producto_id=producto.pk, cantidad=10, costo_unitario=Decimal('4'), fecha_vencimiento=hoy + timedelta(days=10)),
    ])
    caja = abrir_caja(dueno, Decimal('50'), 'Mañana', clave=uuid4())
    efectivo = MetodoPago.objects.get(nombre='Efectivo')
    qr = MetodoPago.objects.get(nombre='QR')
    venta = registrar_venta(dueno, [dict(presentacion_id=presentacion.pk, cantidad=2)], [dict(metodo_id=efectivo.pk, monto='20'), dict(metodo_id=qr.pk, monto='10')], clave=uuid4())
    venta2 = registrar_venta(dueno, [dict(presentacion_id=unidad.pk, cantidad=1)], [dict(metodo_id=efectivo.pk, monto='8')], clave=uuid4())
    registrar_movimiento_caja(dueno, caja.pk, 'INGRESO', '5', 'Ingreso ficticio', clave=uuid4())
    registrar_movimiento_caja(dueno, caja.pk, 'EGRESO', '2', 'Egreso ficticio', clave=uuid4())
    cerrar_caja(dueno, caja.pk, '80', clave=uuid4())
    caja.refresh_from_db()
    return locals()
