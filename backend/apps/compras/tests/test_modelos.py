"""Pruebas de modelos para la app compras: Proveedor, Compra y DetalleCompra."""
from decimal import Decimal

from django.db.models import ProtectedError
from django.db.utils import IntegrityError
from django.test import TestCase

from apps.catalogo.models import Categoria, Producto
from apps.compras.models import Compra, DetalleCompra, Proveedor
from apps.usuarios.models import Usuario


class ComprasModelTest(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(username="comprador", password="pwd")
        self.cat = Categoria.objects.create(nombre="Materia Prima")
        self.prod = Producto.objects.create(
            codigo="MP-01",
            nombre="Cera de Abeja",
            categoria=self.cat,
            creado_por=self.user,
            modificado_por=self.user,
        )
        self.prov = Proveedor.objects.create(
            nombre="Apícola del Valle",
            tipo=Proveedor.TipoProveedor.EMPRESA,
            creado_por=self.user,
            modificado_por=self.user,
        )

    def test_proveedor_nombre_unico(self):
        with self.assertRaises(IntegrityError):
            Proveedor.objects.create(
                nombre="Apícola del Valle",
                tipo=Proveedor.TipoProveedor.COMPRA_PROPIA,
                creado_por=self.user,
                modificado_por=self.user,
            )

    def test_compra_y_detalle_compra(self):
        compra = Compra.objects.create(
            proveedor=self.prov,
            total=Decimal("100.00"),
            usuario=self.user,
            creado_por=self.user,
            modificado_por=self.user,
        )
        detalle = DetalleCompra.objects.create(
            compra=compra,
            producto=self.prod,
            cantidad_unidades=10,
            costo_unitario=Decimal("10.00"),
            subtotal=Decimal("100.00"),
        )
        self.assertEqual(compra.detalles.count(), 1)
        self.assertEqual(detalle.producto, self.prod)

    def test_detalle_compra_cantidad_minimo_uno_constraint(self):
        compra = Compra.objects.create(
            proveedor=self.prov,
            total=Decimal("0.00"),
            usuario=self.user,
            creado_por=self.user,
            modificado_por=self.user,
        )
        with self.assertRaises(IntegrityError):
            DetalleCompra.objects.create(
                compra=compra,
                producto=self.prod,
                cantidad_unidades=0,
                costo_unitario=Decimal("10.00"),
                subtotal=Decimal("0.00"),
            )

    def test_protect_en_proveedor_con_compras(self):
        Compra.objects.create(
            proveedor=self.prov,
            total=Decimal("50.00"),
            usuario=self.user,
            creado_por=self.user,
            modificado_por=self.user,
        )
        with self.assertRaises(ProtectedError):
            self.prov.delete()
