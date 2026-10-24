"""Pruebas de modelos para la app ventas: MetodoPago, Venta, DetalleVenta, DetalleVentaLote y Pago."""
from decimal import Decimal

from django.db import transaction
from django.db.models import ProtectedError
from django.db.utils import IntegrityError
from django.test import TestCase

from apps.caja.models import Caja
from apps.catalogo.models import Categoria, Presentacion, Producto
from apps.inventario.models import Lote
from apps.usuarios.models import Usuario
from apps.ventas.models import DetalleVenta, DetalleVentaLote, MetodoPago, Pago, Venta


class VentasModelTest(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(username="cajero", password="pwd")
        self.caja = Caja.objects.create(
            usuario=self.user,
            monto_inicial=Decimal("100.00"),
            creado_por=self.user,
            modificado_por=self.user,
        )
        self.cat = Categoria.objects.create(nombre="Jarabes")
        self.prod = Producto.objects.create(
            codigo="JAR-01",
            nombre="Propóleo con Miel",
            categoria=self.cat,
            creado_por=self.user,
            modificado_por=self.user,
        )
        self.pres = Presentacion.objects.create(
            producto=self.prod,
            nombre="Frasco 120ml",
            unidades_equivalentes=1,
            precio_venta=Decimal("25.00"),
            creado_por=self.user,
            modificado_por=self.user,
        )
        self.lote = Lote.objects.create(
            producto=self.prod,
            codigo_lote="L-2026-0020",
            cantidad_inicial=50,
            cantidad_actual=50,
            costo_unitario=Decimal("12.00"),
        )
        self.metodo_efectivo = MetodoPago.objects.create(nombre="Efectivo", es_efectivo=True)
        self.metodo_qr = MetodoPago.objects.create(nombre="QR", es_efectivo=False)

    def test_metodo_pago_nombre_unico(self):
        with self.assertRaises(IntegrityError):
            MetodoPago.objects.create(nombre="Efectivo", es_efectivo=True)

    def test_venta_total_no_negativo_constraint(self):
        with self.assertRaises(IntegrityError):
            Venta.objects.create(
                caja=self.caja,
                usuario=self.user,
                total=Decimal("-10.00"),
                creado_por=self.user,
                modificado_por=self.user,
            )

    def test_detalle_venta_minimo_unidades_constraints(self):
        venta = Venta.objects.create(
            caja=self.caja,
            usuario=self.user,
            total=Decimal("25.00"),
            creado_por=self.user,
            modificado_por=self.user,
        )
        # cantidad_presentaciones = 0 viola constraint
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                DetalleVenta.objects.create(
                    venta=venta,
                    presentacion=self.pres,
                    cantidad_presentaciones=0,
                    unidades_totales=1,
                    precio_aplicado=Decimal("25.00"),
                    subtotal=Decimal("0.00"),
                )
        # unidades_totales = 0 viola constraint
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                DetalleVenta.objects.create(
                    venta=venta,
                    presentacion=self.pres,
                    cantidad_presentaciones=1,
                    unidades_totales=0,
                    precio_aplicado=Decimal("25.00"),
                    subtotal=Decimal("25.00"),
                )

    def test_detalle_venta_lote_y_protect_en_lote(self):
        venta = Venta.objects.create(
            caja=self.caja,
            usuario=self.user,
            total=Decimal("25.00"),
            creado_por=self.user,
            modificado_por=self.user,
        )
        detalle = DetalleVenta.objects.create(
            venta=venta,
            presentacion=self.pres,
            cantidad_presentaciones=1,
            unidades_totales=1,
            precio_aplicado=Decimal("25.00"),
            subtotal=Decimal("25.00"),
        )
        DetalleVentaLote.objects.create(
            detalle_venta=detalle,
            lote=self.lote,
            cantidad_unidades=1,
        )
        # No se puede eliminar lote con historial de venta
        with self.assertRaises(ProtectedError):
            self.lote.delete()

    def test_pago_monto_mayor_cero_constraint(self):
        venta = Venta.objects.create(
            caja=self.caja,
            usuario=self.user,
            total=Decimal("25.00"),
            creado_por=self.user,
            modificado_por=self.user,
        )
        with self.assertRaises(IntegrityError):
            Pago.objects.create(
                venta=venta,
                metodo=self.metodo_efectivo,
                monto=Decimal("0.00"),
            )
