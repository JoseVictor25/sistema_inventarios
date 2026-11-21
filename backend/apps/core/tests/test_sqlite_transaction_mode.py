"""Reproduce la promoción DEFERRED -> escritura bajo WAL y valida IMMEDIATE."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest
from uuid import uuid4

from django.db import OperationalError, connections, transaction


class SQLiteTransactionModeTests(unittest.TestCase):
    def test_wal_lectura_y_escritura_concurrentes_immediate_serializa(self):
        with tempfile.TemporaryDirectory(prefix='sqlite_transaction_mode_') as temporal:
            base = Path(temporal) / 'concurrencia.sqlite3'
            with closing(sqlite3.connect(base)) as inicial, inicial:
                self.assertEqual(inicial.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
                inicial.execute('CREATE TABLE contador (id INTEGER PRIMARY KEY, valor INTEGER NOT NULL)')
                inicial.execute('INSERT INTO contador VALUES (1, 0)')

            alias = 'wal_mode_' + uuid4().hex
            configuracion = dict(connections.databases['default'])
            configuracion['NAME'] = str(base)
            configuracion['OPTIONS'] = dict(configuracion['OPTIONS'])
            modo_configurado = configuracion['OPTIONS'].get('transaction_mode')
            self.assertEqual(modo_configurado, 'IMMEDIATE')
            conexiones = connections.databases
            conexiones[alias] = configuracion
            try:
                # Una lectura ORM/DB-API simple sigue en autocommit y no abre
                # una transacción IMMEDIATE por sí sola.
                lectura = connections[alias]
                self.assertTrue(lectura.get_autocommit())
                with lectura.cursor() as cursor:
                    cursor.execute('SELECT valor FROM contador WHERE id=1')
                    self.assertEqual(cursor.fetchone()[0], 0)
                self.assertFalse(lectura.in_atomic_block)
                lectura.close()

            # Sin transaction_mode, ambos hilos leen la misma versión WAL y
            # uno no puede promover su snapshot obsoleto a escritor.
                configuracion['OPTIONS'].pop('transaction_mode', None)
                resultados_diferidos = self._ejecutar_dos_hilos(alias, barrera_tras_lectura=True)
                self.assertCountEqual(resultados_diferidos, ['ok', 'locked'])
                self.assertEqual(self._leer_valor(base), 1)

                with closing(sqlite3.connect(base)) as reinicio, reinicio:
                    reinicio.execute('UPDATE contador SET valor=0 WHERE id=1')
                configuracion['OPTIONS']['transaction_mode'] = modo_configurado
                resultados_inmediatos = self._ejecutar_dos_hilos(alias, barrera_tras_lectura=False)
                self.assertCountEqual(resultados_inmediatos, ['ok', 'ok'])
                self.assertEqual(self._leer_valor(base), 2)
            finally:
                connections.close_all()
                conexiones.pop(alias, None)

    @staticmethod
    def _leer_valor(base):
        with closing(sqlite3.connect(base)) as consulta:
            return consulta.execute('SELECT valor FROM contador WHERE id=1').fetchone()[0]

    @staticmethod
    def _ejecutar_dos_hilos(alias, *, barrera_tras_lectura):
        barrera = Barrier(2)

        def actualizar():
            conexion = connections[alias]
            try:
                if not barrera_tras_lectura:
                    # Con IMMEDIATE el segundo BEGIN espera al primer COMMIT;
                    # sincronizar después de BEGIN bloquearía intencionalmente.
                    barrera.wait(timeout=5)
                with transaction.atomic(using=alias):
                    with conexion.cursor() as cursor:
                        cursor.execute('SELECT valor FROM contador WHERE id=1')
                        cursor.fetchone()
                    if barrera_tras_lectura:
                        barrera.wait(timeout=5)
                    with conexion.cursor() as cursor:
                        cursor.execute('UPDATE contador SET valor=valor+1 WHERE id=1')
                return 'ok'
            except OperationalError as error:
                if 'locked' in str(error).lower() or 'busy' in str(error).lower():
                    return 'locked'
                raise
            finally:
                conexion.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(lambda _: actualizar(), range(2)))
