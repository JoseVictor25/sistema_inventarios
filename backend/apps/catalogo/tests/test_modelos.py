"""Pruebas de modelos para la app catalogo: Categoria, Producto, Presentacion y AtributoProducto."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.db.utils import IntegrityError
from django.test import TestCase

from apps.catalogo.models import AtributoProducto, Categoria, Presentacion, Producto
from apps.inventario.models import Lote
from apps.usuarios.models import Usuario


class CategoriaModelTest(TestCase):
    def test_categoria_raiz_nombre_unico(self):
        Categoria.objects.create(nombre="Infusiones")
        with self.assertRaises(IntegrityError):
            Categoria.objects.create(nombre="Infusiones")

    def test_subcategorias_mismo_nombre_diferente_padre(self):
        cat1 = Categoria.objects.create(nombre="Hierbas")
        cat2 = Categoria.objects.create(nombre="Aceites")
        sub1 = Categoria.objects.create(nombre="Importados", padre=cat1)
        sub2 = Categoria.objects.create(nombre="Importados", padre=cat2)
        self.assertEqual(sub1.nombre, sub2.nombre)

    def test_subcategoria_mismo_nombre_mismo_padre_falla(self):
        cat1 = Categoria.objects.create(nombre="Hierbas")
        Categoria.objects.create(nombre="Importados", padre=cat1)
        with self.assertRaises(IntegrityError):
            Categoria.objects.create(nombre="Importados", padre=cat1)

    def test_deteccion_ciclos_rn18(self):
        cat_a = Categoria.objects.create(nombre="A")
        cat_b = Categoria.objects.create(nombre="B", padre=cat_a)
        # Intentar que cat_a sea hija de cat_b crea un ciclo A -> B -> A
        cat_a.padre = cat_b
        with self.assertRaises(ValidationError):
            cat_a.clean()


class ProductoModelTest(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(nombre="Medicinales")
        self.user = Usuario.objects.create_user(username="testuser", password="pwd")

    def test_creacion_producto_y_codigo_unico(self):
        p = Producto.objects.create(
            codigo="PROD-001",
            nombre="Manzanilla",
            categoria=self.cat,
            stock_minimo=10,
            creado_por=self.user,
            modificado_por=self.user,
        )
        self.assertEqual(str(p), "Manzanilla")
        with self.assertRaises(IntegrityError):
            Producto.objects.create(
                codigo="PROD-001",
                nombre="Otro",
                categoria=self.cat,
                creado_por=self.user,
                modificado_por=self.user,
            )

    def test_stock_actual_suma_lotes(self):
        p = Producto.objects.create(
            codigo="PROD-002",
            nombre="Valeriana",
            categoria=self.cat,
            creado_por=self.user,
            modificado_por=self.user,
        )
        self.assertEqual(p.stock_actual, 0)
        Lote.objects.create(
            producto=p,
            codigo_lote="L-2026-0001",
            cantidad_inicial=50,
            cantidad_actual=30,
            costo_unitario=Decimal("5.00"),
        )
        Lote.objects.create(
            producto=p,
            codigo_lote="L-2026-0002",
            cantidad_inicial=20,
            cantidad_actual=15,
            costo_unitario=Decimal("6.00"),
        )
        self.assertEqual(p.stock_actual, 45)

    def test_protect_en_categoria_con_productos(self):
        Producto.objects.create(
            codigo="PROD-003",
            nombre="Menta",
            categoria=self.cat,
            creado_por=self.user,
            modificado_por=self.user,
        )
        with self.assertRaises(ProtectedError):
            self.cat.delete()


class PresentacionModelTest(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(nombre="Ungüentos")
        self.user = Usuario.objects.create_user(username="testuser2", password="pwd")
        self.prod = Producto.objects.create(
            codigo="UNG-01",
            nombre="Mentolatum Natural",
            categoria=self.cat,
            creado_por=self.user,
            modificado_por=self.user,
        )

    def test_nombre_unico_por_producto(self):
        Presentacion.objects.create(
            producto=self.prod,
            nombre="Pote 50g",
            unidades_equivalentes=1,
            precio_venta=Decimal("15.50"),
            creado_por=self.user,
            modificado_por=self.user,
        )
        with self.assertRaises(IntegrityError):
            Presentacion.objects.create(
                producto=self.prod,
                nombre="Pote 50g",
                unidades_equivalentes=2,
                precio_venta=Decimal("30.00"),
                creado_por=self.user,
                modificado_por=self.user,
            )

    def test_unidades_equivalentes_minimo_uno_constraint(self):
        with self.assertRaises(IntegrityError):
            Presentacion.objects.create(
                producto=self.prod,
                nombre="Cero unidades",
                unidades_equivalentes=0,
                precio_venta=Decimal("10.00"),
                creado_por=self.user,
                modificado_por=self.user,
            )


class AtributoProductoModelTest(TestCase):
    def test_atributo_nombre_unico_por_producto(self):
        user = Usuario.objects.create_user(username="testuser3", password="pwd")
        cat = Categoria.objects.create(nombre="Hierbas Secas")
        prod = Producto.objects.create(
            codigo="H-01",
            nombre="Eucalipto",
            categoria=cat,
            creado_por=user,
            modificado_por=user,
        )
        AtributoProducto.objects.create(producto=prod, nombre="Origen", valor="Cochabamba")
        with self.assertRaises(IntegrityError):
            AtributoProducto.objects.create(producto=prod, nombre="Origen", valor="La Paz")
