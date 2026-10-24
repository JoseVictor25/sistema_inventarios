"""Pruebas de modelos para la app caja: Caja y MovimientoCaja."""
from decimal import Decimal

from django.db import transaction
from django.db.utils import IntegrityError
from django.test import TestCase

from apps.caja.models import Caja, MovimientoCaja
from apps.usuarios.models import Usuario
from apps.ventas.models import MetodoPago, Pago, Venta


class CajaModelTest(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(username="cajero1", password="pwd")
        self.user2 = Usuario.objects.create_user(username="cajero2", password="pwd")
        self.metodo_efectivo = MetodoPago.objects.create(nombre="Efectivo", es_efectivo=True)
        self.metodo_qr = MetodoPago.objects.create(nombre="QR", es_efectivo=False)

    def test_rn11_una_sola_caja_abierta_por_usuario(self):
        # Primera caja abierta: OK
        Caja.objects.create(
            usuario=self.user,
            monto_inicial=Decimal("50.00"),
            estado=Caja.EstadoCaja.ABIERTA,
            creado_por=self.user,
            modificado_por=self.user,
        )
        # Segunda caja abierta para el MISMO usuario: debe fallar por RN-11
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Caja.objects.create(
                    usuario=self.user,
                    monto_inicial=Decimal("100.00"),
                    estado=Caja.EstadoCaja.ABIERTA,
                    creado_por=self.user,
                    modificado_por=self.user,
                )
        # Pero otro usuario SI puede tener una caja abierta
        otra_caja = Caja.objects.create(
            usuario=self.user2,
            monto_inicial=Decimal("20.00"),
            estado=Caja.EstadoCaja.ABIERTA,
            creado_por=self.user2,
            modificado_por=self.user2,
        )
        self.assertEqual(otra_caja.estado, Caja.EstadoCaja.ABIERTA)

    def test_multiples_cajas_cerradas_permitidas(self):
        c1 = Caja.objects.create(
            usuario=self.user,
            monto_inicial=Decimal("50.00"),
            monto_contado=Decimal("50.00"),
            estado=Caja.EstadoCaja.CERRADA,
            creado_por=self.user,
            modificado_por=self.user,
        )
        c2 = Caja.objects.create(
            usuario=self.user,
            monto_inicial=Decimal("60.00"),
            monto_contado=Decimal("60.00"),
            estado=Caja.EstadoCaja.CERRADA,
            creado_por=self.user,
            modificado_por=self.user,
        )
        self.assertNotEqual(c1.pk, c2.pk)

    def test_monto_inicial_no_negativo_constraint(self):
        with self.assertRaises(IntegrityError):
            Caja.objects.create(
                usuario=self.user,
                monto_inicial=Decimal("-10.00"),
                creado_por=self.user,
                modificado_por=self.user,
            )

    def test_monto_esperado_y_diferencia_con_ventas_y_movimientos(self):
        caja = Caja.objects.create(
            usuario=self.user,
            monto_inicial=Decimal("100.00"),
            estado=Caja.EstadoCaja.ABIERTA,
            creado_por=self.user,
            modificado_por=self.user,
        )
        # Venta con pago en efectivo (Bs 50) y otra con QR (Bs 30)
        v1 = Venta.objects.create(
            caja=caja,
            usuario=self.user,
            total=Decimal("50.00"),
            creado_por=self.user,
            modificado_por=self.user,
        )
        Pago.objects.create(venta=v1, metodo=self.metodo_efectivo, monto=Decimal("50.00"))

        v2 = Venta.objects.create(
            caja=caja,
            usuario=self.user,
            total=Decimal("30.00"),
            creado_por=self.user,
            modificado_por=self.user,
        )
        # El pago QR NO debe contabilizarse en efectivo
        Pago.objects.create(venta=v2, metodo=self.metodo_qr, monto=Decimal("30.00"))

        # Movimiento de ingreso: +20
        MovimientoCaja.objects.create(
            caja=caja,
            tipo=MovimientoCaja.TipoMovimientoCaja.INGRESO,
            monto=Decimal("20.00"),
            concepto="Cambio extra",
            usuario=self.user,
        )

        # Movimiento de egreso: -10
        MovimientoCaja.objects.create(
            caja=caja,
            tipo=MovimientoCaja.TipoMovimientoCaja.EGRESO,
            monto=Decimal("10.00"),
            concepto="Compra de bolsas",
            usuario=self.user,
        )

        # Monto esperado = 100 (inicial) + 50 (efectivo) + 20 (ingreso) - 10 (egreso) = 160
        self.assertEqual(caja.monto_esperado(), Decimal("160.00"))

        # Diferencia sin haber contado aún: None
        self.assertIsNone(caja.diferencia())

        # Contado = 160 -> diferencia 0 (cuadra)
        caja.monto_contado = Decimal("160.00")
        self.assertEqual(caja.diferencia(), Decimal("0.00"))

        # Contado = 170 -> diferencia +10 (sobra)
        caja.monto_contado = Decimal("170.00")
        self.assertEqual(caja.diferencia(), Decimal("10.00"))

        # Contado = 150 -> diferencia -10 (falta)
        caja.monto_contado = Decimal("150.00")
        self.assertEqual(caja.diferencia(), Decimal("-10.00"))

    def test_movimiento_caja_monto_mayor_cero_constraint(self):
        caja = Caja.objects.create(
            usuario=self.user,
            monto_inicial=Decimal("50.00"),
            creado_por=self.user,
            modificado_por=self.user,
        )
        with self.assertRaises(IntegrityError):
            MovimientoCaja.objects.create(
                caja=caja,
                tipo=MovimientoCaja.TipoMovimientoCaja.INGRESO,
                monto=Decimal("0.00"),
                concepto="Monto cero inválido",
                usuario=self.user,
            )
