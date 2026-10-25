"""Conexiones independientes sobre SQLite temporal, ajustes contra ventas."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from django.db import connections
from django.test import TransactionTestCase
from apps.core.exceptions import ErrorDeNegocio
from apps.inventario import services as s
from apps.inventario.models import Lote, MovimientoInventario
from apps.auditoria.models import LogAuditoria
from apps.usuarios.models import Usuario
from apps.caja.services import abrir_caja
from apps.ventas.services import registrar_venta
from apps.ventas.models import MetodoPago
from .test_fase7 import preparar, lote


class ConcurrenciaFase7Tests(TransactionTestCase):
    def setUp(self):
        self.dueno, self.vendedor, self.producto, self.pres = preparar()
        self.lote = lote(self.producto, 'CONCURRENTE', 10)

    def carrera(self, acciones):
        barrera = Barrier(len(acciones))
        def ejecutar(datos):
            usuario_id, accion = datos
            connections.close_all()
            try:
                usuario = Usuario.objects.get(pk=usuario_id)
                conexion = connections['default']
                conexion.ensure_connection()
                identidad = id(conexion.connection)
                barrera.wait(timeout=10)
                try:
                    accion(usuario)
                    return identidad, True
                except ErrorDeNegocio:
                    return identidad, False
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(acciones)) as ejecutor:
            resultados = list(ejecutor.map(ejecutar, acciones))
        self.assertEqual(len({r[0] for r in resultados}), len(acciones))
        self.assertTrue(any(r[1] for r in resultados))
        return resultados

    def test_dos_mermas_no_sobrevenden_y_no_dejan_historia_parcial(self):
        accion = lambda usuario: s.ajustar_inventario(usuario, self.lote.pk, 'MERMA', -8, 'Rotura comprobada')
        resultados = self.carrera([(self.dueno.pk, accion), (self.dueno.pk, accion)])
        self.assertEqual(sum(r[1] for r in resultados), 1)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_actual, 2)
        self.assertEqual(MovimientoInventario.objects.count(), 1)
        self.assertEqual(LogAuditoria.objects.count(), 1)

    def test_merma_compite_con_venta_fefo(self):
        abrir_caja(self.vendedor, '0', clave=uuid4())
        metodo = MetodoPago.objects.get(nombre='Efectivo')
        def venta(usuario):
            registrar_venta(usuario, [{'presentacion_id': self.pres.pk, 'cantidad': 8}],
                            [{'metodo_id': metodo.pk, 'monto': '80'}], clave=uuid4())
        resultados = self.carrera([
            (self.dueno.pk, lambda usuario: s.ajustar_inventario(usuario, self.lote.pk, 'MERMA', -8, 'Rotura comprobada')),
            (self.vendedor.pk, venta)])
        self.assertEqual(sum(r[1] for r in resultados), 1)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_actual, 2)
        self.assertEqual(MovimientoInventario.objects.count(), 1)
        movimiento = MovimientoInventario.objects.get()
        self.assertIn(movimiento.tipo, ('MERMA', 'SALIDA'))
        self.assertEqual(LogAuditoria.objects.filter(accion='AJUSTE_INVENTARIO').count(), int(movimiento.tipo == 'MERMA'))

    def test_operaciones_compatibles_no_pierden_actualizaciones(self):
        accion = lambda usuario: s.ajustar_inventario(usuario, self.lote.pk, 'AJUSTE', -1, 'Conteo físico')
        resultados = self.carrera([(self.dueno.pk, accion), (self.dueno.pk, accion)])
        exitos = sum(r[1] for r in resultados)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_actual, 10 - exitos)
        self.assertEqual(MovimientoInventario.objects.count(), exitos)
        self.assertEqual(LogAuditoria.objects.count(), exitos)

    def test_concurrencia_misma_clave_deduplica_y_mantiene_stock(self):
        from apps.inventario.models import OperacionAjusteInventario
        clave_compartida = uuid4()
        accion = lambda usuario: s.ajustar_inventario(usuario, self.lote.pk, 'AJUSTE', -2, 'Conteo físico simultáneo', clave=clave_compartida)
        resultados = self.carrera([(self.dueno.pk, accion), (self.dueno.pk, accion)])
        self.assertTrue(any(r[1] for r in resultados))
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_actual, 8)
        self.assertEqual(MovimientoInventario.objects.count(), 1)
        self.assertEqual(LogAuditoria.objects.count(), 1)
        self.assertEqual(OperacionAjusteInventario.objects.filter(clave=clave_compartida).count(), 1)
