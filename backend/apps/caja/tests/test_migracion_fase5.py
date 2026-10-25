"""Actualización desde el esquema inmediatamente anterior, solo en BD de tests."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.core.management import call_command
from io import StringIO
from apps.core.tests.test_regresiones_fase1 import crear_historial


class MigracionOperacionCajaTests(TransactionTestCase):
    def test_desde_0002_preserva_historial_y_crea_solo_tabla_nueva(self):
        ejecutor = MigrationExecutor(connection)
        finales = ejecutor.loader.graph.leaf_nodes()
        anteriores = [(app, '0002_integridad_fase1' if app == 'caja' else nombre)
                      for app, nombre in finales]

        def registros():
            with connection.cursor() as cursor:
                resultado = {}
                for tabla in connection.introspection.table_names(cursor):
                    if tabla != 'django_migrations':
                        cursor.execute('SELECT * FROM ' + connection.ops.quote_name(tabla))
                        resultado[tabla] = sorted(cursor.fetchall(), key=repr)
                return resultado
        try:
            ejecutor.migrate(anteriores)
            crear_historial()
            call_command('cargar_datos_iniciales', stdout=StringIO())
            antes = registros()
            MigrationExecutor(connection).migrate(finales)
            despues = registros()
            self.assertEqual({tabla: despues[tabla] for tabla in antes}, antes)
            self.assertEqual(set(despues) - set(antes), {'caja_operacioncaja'})
            self.assertEqual(despues['caja_operacioncaja'], [])
            with connection.cursor() as cursor:
                cursor.execute('PRAGMA integrity_check')
                self.assertEqual(cursor.fetchone()[0], 'ok')
                cursor.execute('PRAGMA foreign_key_check')
                self.assertEqual(cursor.fetchall(), [])
        finally:
            MigrationExecutor(connection).migrate(finales)
