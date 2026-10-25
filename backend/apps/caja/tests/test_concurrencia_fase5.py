"""Carreras con conexiones independientes a la SQLite temporal del test runner."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from django.db import connections, connection
from django.test import TransactionTestCase

from apps.auditoria.models import LogAuditoria
from apps.caja import services as s
from apps.caja.models import Caja, MovimientoCaja, OperacionCaja
from apps.core.exceptions import ErrorDeNegocio
from apps.usuarios.models import Usuario
from .test_operaciones_fase5 import usuarios


class ConcurrenciaCajaTests(TransactionTestCase):
    def setUp(self):
        self.dueno, self.vendedor = usuarios()

    def carrera(self, *acciones):
        barrera = Barrier(len(acciones))
        usuario_id = self.vendedor.pk

        def ejecutar(accion):
            connections.close_all()
            try:
                usuario = Usuario.objects.select_related("rol").get(pk=usuario_id)
                conexion = connections["default"]
                conexion.ensure_connection()
                identidad = id(conexion.connection)
                barrera.wait(timeout=10)
                try:
                    return identidad, True, accion(usuario)
                except ErrorDeNegocio as error:
                    return identidad, False, error.mensaje
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(acciones)) as ejecutor:
            resultados = list(ejecutor.map(ejecutar, acciones))
        self.assertEqual(len({r[0] for r in resultados}), len(acciones))
        self.assertTrue(any(r[1] for r in resultados), resultados)
        return resultados

    def test_apertura_concurrente_misma_clave(self):
        clave = uuid4()
        accion = lambda u: s.abrir_caja(u, "100", clave=clave).pk
        self.carrera(accion, accion)
        self.assertEqual(Caja.objects.count(), 1)
        self.assertEqual(OperacionCaja.objects.count(), 1)
        self.assertEqual(accion(self.vendedor), Caja.objects.get().pk)

    def test_apertura_concurrente_distintas_claves(self):
        self.carrera(lambda u: s.abrir_caja(u, "100", clave=uuid4()).pk,
                     lambda u: s.abrir_caja(u, "100", clave=uuid4()).pk)
        self.assertEqual(Caja.objects.count(), 1)
        self.assertEqual(OperacionCaja.objects.count(), 1)

    def test_movimiento_concurrente_misma_clave(self):
        caja = s.abrir_caja(self.vendedor, "100", clave=uuid4())
        clave = uuid4()
        accion = lambda u: s.registrar_movimiento_caja(u, caja.pk, "INGRESO", "5", "Cambio", clave=clave).pk
        self.carrera(accion, accion)
        self.assertEqual(MovimientoCaja.objects.count(), 1)
        self.assertEqual(OperacionCaja.objects.count(), 2)
        self.assertEqual(accion(self.vendedor), MovimientoCaja.objects.get().pk)

    def test_movimientos_concurrentes_identicos_claves_distintas(self):
        caja = s.abrir_caja(self.vendedor, "100", clave=uuid4())
        claves = [uuid4(), uuid4()]
        def accion(clave):
            return lambda u: s.registrar_movimiento_caja(u, caja.pk, "INGRESO", "5", "Cambio", clave=clave).pk
        self.carrera(*(accion(clave) for clave in claves))
        # Si SQLite devolvió ocupado, el cliente reenvía la MISMA clave.
        for clave in claves:
            accion(clave)(self.vendedor)
        self.assertEqual(MovimientoCaja.objects.count(), 2)

    def test_misma_clave_concurrente_datos_distintos(self):
        caja = s.abrir_caja(self.vendedor, "100", clave=uuid4())
        clave = uuid4()
        self.carrera(lambda u: s.registrar_movimiento_caja(u, caja.pk, "INGRESO", "5", "Cambio", clave=clave).pk,
                     lambda u: s.registrar_movimiento_caja(u, caja.pk, "INGRESO", "6", "Cambio", clave=clave).pk)
        self.assertEqual(MovimientoCaja.objects.count(), 1)
        monto = MovimientoCaja.objects.get().monto
        distinto = "6" if monto == 5 else "5"
        with self.assertRaises(ErrorDeNegocio):
            s.registrar_movimiento_caja(self.vendedor, caja.pk, "INGRESO", distinto, "Cambio", clave=clave)

    def test_cierre_concurrente_misma_clave(self):
        caja = s.abrir_caja(self.vendedor, "100", clave=uuid4())
        clave = uuid4()
        accion = lambda u: s.cerrar_caja(u, caja.pk, "100", clave=clave)
        self.carrera(accion, accion)
        self.assertEqual(LogAuditoria.objects.filter(accion="CIERRE_CAJA").count(), 1)
        self.assertEqual(OperacionCaja.objects.filter(accion="CERRAR").count(), 1)
        self.assertEqual(accion(self.vendedor)["resultado"], "CUADRA")

    def test_cierre_concurrente_distintas_claves(self):
        caja = s.abrir_caja(self.vendedor, "100", clave=uuid4())
        self.carrera(lambda u: s.cerrar_caja(u, caja.pk, "100", clave=uuid4()),
                     lambda u: s.cerrar_caja(u, caja.pk, "100", clave=uuid4()))
        self.assertEqual(LogAuditoria.objects.filter(accion="CIERRE_CAJA").count(), 1)
        self.assertEqual(OperacionCaja.objects.filter(accion="CERRAR").count(), 1)

    def test_movimiento_concurrente_con_cierre(self):
        caja = s.abrir_caja(self.vendedor, "100", clave=uuid4())
        clave_mov, clave_cierre = uuid4(), uuid4()
        self.carrera(lambda u: s.registrar_movimiento_caja(u, caja.pk, "INGRESO", "5", "Cambio", clave=clave_mov).pk,
                     lambda u: s.cerrar_caja(u, caja.pk, "100", clave=clave_cierre))
        # Completa solo el cierre si obtuvo un conflicto transitorio.
        resumen = s.cerrar_caja(self.vendedor, caja.pk, "100", clave=clave_cierre)
        cantidad = MovimientoCaja.objects.count()
        self.assertIn(cantidad, (0, 1))
        self.assertEqual(resumen["ingresos"], cantidad * 5)
        self.assertEqual(resumen["esperado"], 100 + cantidad * 5)
        with self.assertRaises(ErrorDeNegocio):
            s.registrar_movimiento_caja(self.vendedor, caja.pk, "INGRESO", "5", "Tardío", clave=uuid4())

    def test_bloqueo_en_curso_controlado_sin_reserva_parcial(self):
        # Conexión DB-API independiente, también compatible con el URI de tests.
        import sqlite3
        nombre = str(connection.settings_dict["NAME"])
        bloqueo = sqlite3.connect(nombre, uri=nombre.startswith("file:"), timeout=0.05)
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA busy_timeout = 50")
        try:
            bloqueo.execute("BEGIN IMMEDIATE")
            with self.assertRaisesMessage(ErrorDeNegocio, "misma clave"):
                s.abrir_caja(self.vendedor, "1", clave=uuid4())
        finally:
            bloqueo.rollback()
            bloqueo.close()
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA busy_timeout = 5000")
        self.assertFalse(OperacionCaja.objects.exists())
        self.assertFalse(Caja.objects.exists())
