"""Restauración limitada a directorios temporales y copias SQLite de prueba."""
from contextlib import closing
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase
from apps.core import respaldos
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from desktop.bloqueo_instancia import bloqueo_instancia
from desktop.restauracion import restaurar_con_bloqueo


class RestauracionLauncherTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='restauracion_test_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.datos = self.root / 'datos'
        self.datos.mkdir()
        self.db = self.datos / 'db.sqlite3'
        self.backups = self.datos / 'respaldos'
        self.copias_origen = self.root / 'copias_origen'
        self.copias_origen.mkdir()
        self._crear_db(self.db, 'actual')
        otra = self.root / 'base_respaldo.sqlite3'
        self._crear_db(otra, 'respaldo')
        resultado = respaldos.crear_copia(otra, self.copias_origen, 5)
        self.copia = self.copias_origen / resultado['archivo']

    @staticmethod
    def _crear_db(ruta, contenido):
        with closing(sqlite3.connect(ruta)) as con, con:
            for tabla in respaldos.TABLAS - {'django_migrations'}:
                con.execute(f'CREATE TABLE "{tabla}" (id INTEGER PRIMARY KEY, valor TEXT)')
            con.execute('CREATE TABLE django_migrations (app TEXT, name TEXT)')
            con.execute("INSERT INTO django_migrations VALUES ('usuarios','0001_initial')")
            con.execute('INSERT INTO usuarios_usuario VALUES (1, ?)', (contenido,))

    def _valor(self):
        with closing(sqlite3.connect(self.db)) as con:
            return con.execute('SELECT valor FROM usuarios_usuario').fetchone()[0]

    def _restaurar(self, copia=None):
        return restaurar_con_bloqueo(copia or self.copia, self.db, self.datos,
            self.backups, 5, self.datos / 'qr_bancario.png')

    def test_restauracion_correcta_y_respaldo_de_seguridad(self):
        resultado = self._restaurar()
        self.assertEqual(self._valor(), 'respaldo')
        self.assertTrue((self.backups / resultado['respaldo_seguridad']).is_file())

    def test_copia_corrupta_se_rechaza_antes_de_tocar_base(self):
        corrupta = self.root / 'corrupta.sqlite3'
        corrupta.write_bytes(b'no sqlite')
        with self.assertRaises(respaldos.ErrorRespaldo):
            self._restaurar(corrupta)
        self.assertEqual(self._valor(), 'actual')

    def test_instancia_activa_se_rechaza(self):
        with bloqueo_instancia(self.datos):
            with self.assertRaisesRegex(respaldos.ErrorRespaldo, 'programa está en ejecución'):
                self._restaurar()
        self.assertEqual(self._valor(), 'actual')

    def test_fallo_al_reemplazar_recupera_base_actual(self):
        unlink_real = Path.unlink
        fallo = {'pendiente': True}
        def borrar(ruta, *args, **kwargs):
            if fallo['pendiente'] and str(ruta) == str(Path(str(self.db) + '-wal')):
                fallo['pendiente'] = False
                raise OSError('fallo controlado después de reemplazar la base')
            return unlink_real(ruta, *args, **kwargs)
        with patch.object(Path, 'unlink', autospec=True, side_effect=lambda ruta, *args, **kwargs: borrar(ruta, *args, **kwargs)):
            with self.assertRaisesRegex(respaldos.ErrorRespaldo, 'base anterior fue recuperada'):
                self._restaurar()
        self.assertEqual(self._valor(), 'actual')
