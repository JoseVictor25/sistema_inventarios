"""Pruebas del algoritmo FEFO y descuento de inventario (RN-06, RN-07)."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

from django.db import connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto
from apps.core.exceptions import ErrorDeNegocio
from apps.inventario.models import Lote
from apps.inventario.services import descontar_stock_fefo


def crear_producto_base(nombre="Producto Prueba", codigo="PROD-001"):
    cat, _ = Categoria.objects.get_or_create(nombre="Categoría Test")
    return Producto.objects.create(
        codigo=codigo,
        nombre=nombre,
        categoria=cat,
        stock_minimo=5,
    )


def crear_lote(producto, codigo, cantidad, vencimiento=None, costo="10.00"):
    return Lote.objects.create(
        producto=producto,
        codigo_lote=codigo,
        cantidad_inicial=cantidad,
        cantidad_actual=cantidad,
        costo_unitario=Decimal(costo),
        fecha_vencimiento=vencimiento,
    )


class DescontarStockFEFOTests(TestCase):
    def setUp(self):
        self.producto = crear_producto_base()
        self.hoy = timezone.localdate()

    def test_fefo_orden_vencimiento_proximo_primero(self):
        """RN-06: Se descuenta primero el lote con fecha de vencimiento más próxima."""
        lote_lejano = crear_lote(self.producto, "L-LEJANO", 10, vencimiento=self.hoy + timedelta(days=30))
        lote_cercano = crear_lote(self.producto, "L-CERCANO", 10, vencimiento=self.hoy + timedelta(days=5))

        with transaction.atomic():
            salidas = descontar_stock_fefo(self.producto, 15)

        self.assertEqual(len(salidas), 2)
        # El primero en salir debe ser el cercano por 10 unidades
        self.assertEqual(salidas[0][0].pk, lote_cercano.pk)
        self.assertEqual(salidas[0][1], 10)
        # El segundo en salir debe ser el lejano por 5 unidades
        self.assertEqual(salidas[1][0].pk, lote_lejano.pk)
        self.assertEqual(salidas[1][1], 5)

        lote_cercano.refresh_from_db()
        lote_lejano.refresh_from_db()
        self.assertEqual(lote_cercano.cantidad_actual, 0)
        self.assertEqual(lote_lejano.cantidad_actual, 5)

    def test_fefo_lotes_sin_vencimiento_al_final(self):
        """RN-06: Los lotes sin vencimiento (NULL) se consumen después de los que vencen."""
        lote_sin_venc = crear_lote(self.producto, "L-SINVENC", 10, vencimiento=None)
        lote_con_venc = crear_lote(self.producto, "L-CONVENC", 10, vencimiento=self.hoy + timedelta(days=10))

        with transaction.atomic():
            salidas = descontar_stock_fefo(self.producto, 12)

        self.assertEqual(salidas[0][0].pk, lote_con_venc.pk)
        self.assertEqual(salidas[0][1], 10)
        self.assertEqual(salidas[1][0].pk, lote_sin_venc.pk)
        self.assertEqual(salidas[1][1], 2)

        lote_con_venc.refresh_from_db()
        lote_sin_venc.refresh_from_db()
        self.assertEqual(lote_con_venc.cantidad_actual, 0)
        self.assertEqual(lote_sin_venc.cantidad_actual, 8)

    def test_fefo_lotes_vencidos_excluidos(self):
        """RN-07: Los lotes vencidos están completamente excluidos de la venta."""
        lote_vencido = crear_lote(self.producto, "L-VENCIDO", 20, vencimiento=self.hoy - timedelta(days=1))
        lote_valido = crear_lote(self.producto, "L-VALIDO", 5, vencimiento=self.hoy + timedelta(days=2))

        with transaction.atomic():
            salidas = descontar_stock_fefo(self.producto, 5)

        self.assertEqual(len(salidas), 1)
        self.assertEqual(salidas[0][0].pk, lote_valido.pk)
        self.assertEqual(salidas[0][1], 5)

        lote_vencido.refresh_from_db()
        self.assertEqual(lote_vencido.cantidad_actual, 20)

        # Si se piden más de las disponibles válidas, falla aunque el vencido tenga stock
        with self.assertRaises(ErrorDeNegocio) as ctx:
            with transaction.atomic():
                descontar_stock_fefo(self.producto, 1)
        self.assertIn("No alcanza el stock", ctx.exception.mensaje)

    def test_fefo_stock_insuficiente(self):
        """Si la suma de lotes válidos no alcanza, lanza ErrorDeNegocio informando disponible."""
        crear_lote(self.producto, "L-01", 3, vencimiento=self.hoy + timedelta(days=10))
        with self.assertRaises(ErrorDeNegocio) as ctx:
            with transaction.atomic():
                descontar_stock_fefo(self.producto, 5)
        self.assertIn("No alcanza el stock de Producto Prueba: quedan 3 unidades", ctx.exception.mensaje)

    def test_fefo_unidades_invalidas(self):
        """Valida que unidades sea un entero estricto mayor a cero."""
        for invalido in (0, -1, -10, 1.5, True, False, "10", None, []):
            with self.assertRaises(ErrorDeNegocio):
                with transaction.atomic():
                    descontar_stock_fefo(self.producto, invalido)

    def test_fefo_rollback_atomico(self):
        """Si una transacción falla posteriormente, los descuentos de lotes se revierten."""
        lote = crear_lote(self.producto, "L-01", 10, vencimiento=self.hoy + timedelta(days=10))
        try:
            with transaction.atomic():
                descontar_stock_fefo(self.producto, 4)
                raise RuntimeError("Error forzado posterior")
        except RuntimeError:
            pass

        lote.refresh_from_db()
        self.assertEqual(lote.cantidad_actual, 10)


class ConcurrenciaFEFOTests(TransactionTestCase):
    def test_concurrencia_descuento_fefo(self):
        """Dos transacciones simultáneas con conexiones independientes no descuentan más de lo existente."""
        producto = crear_producto_base("Producto Concurrente", "P-CONC")
        crear_lote(producto, "L-CONC", 10, vencimiento=timezone.localdate() + timedelta(days=10))

        barrera = Barrier(2)

        def intentar_descuento(unidades):
            connections.close_all()
            try:
                conexion = connections["default"]
                conexion.ensure_connection()
                identidad = id(conexion.connection)
                barrera.wait(timeout=10)
                try:
                    with transaction.atomic():
                        prod = Producto.objects.get(pk=producto.pk)
                        descontar_stock_fefo(prod, unidades)
                    return identidad, True, None
                except ErrorDeNegocio as error:
                    return identidad, False, error.mensaje
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            # Ambos intentan descontar 8 unidades de un total de 10
            futuro1 = ejecutor.submit(intentar_descuento, 8)
            futuro2 = ejecutor.submit(intentar_descuento, 8)
            r1 = futuro1.result()
            r2 = futuro2.result()

        # Uno debió tener éxito y el otro debió fallar por stock insuficiente (quedaban 2 u.)
        exitos = [r for r in (r1, r2) if r[1]]
        fallos = [r for r in (r1, r2) if not r[1]]
        self.assertEqual(len(exitos), 1)
        self.assertTrue(
            any(txt in fallos[0][2] for txt in ("No alcanza el stock", "El inventario está siendo actualizado")),
            fallos[0][2],
        )

        lote = Lote.objects.get(codigo_lote="L-CONC")
        self.assertEqual(lote.cantidad_actual, 2)
