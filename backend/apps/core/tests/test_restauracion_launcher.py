"""Restauración limitada a directorios temporales y copias SQLite de prueba."""
from contextlib import closing
import sqlite3
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
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
        with override_settings(DB_PATH=self.db, BACKUP_DIR=self.backups,
                               BACKUP_CONSERVAR=5, DATA_DIR=self.datos):
            def preparar():
                self.assertTrue(bloqueo_activo(self.datos))
            return restaurar_con_bloqueo(copia or self.copia, self.datos, preparar=preparar)

    def test_restauracion_correcta_y_respaldo_de_seguridad(self):
        with closing(sqlite3.connect(self.db)) as conexion:
            conexion.execute('PRAGMA journal_mode=WAL')
            conexion.execute("INSERT INTO usuarios_usuario VALUES (2, 'confirmada en WAL')")
            conexion.commit()
        resultado = self._restaurar()
        self.assertEqual(self._valor(), 'respaldo')
        self.assertTrue((self.backups / resultado['respaldo_seguridad']).is_file())
        self.assertFalse(list(self.datos.glob('db_restaurada_*.sqlite3*')))
        with closing(sqlite3.connect(self.backups / resultado['respaldo_seguridad'])) as seguridad:
            self.assertEqual(seguridad.execute('SELECT valor FROM usuarios_usuario ORDER BY id').fetchall(),
                             [('actual',), ('confirmada en WAL',)])

    def test_copia_corrupta_se_rechaza_antes_de_tocar_base(self):
        corrupta = self.root / 'corrupta.sqlite3'
        corrupta.write_bytes(b'no sqlite')
        with self.assertRaises(respaldos.ErrorRespaldo):
            self._restaurar(corrupta)
        self.assertEqual(self._valor(), 'actual')

    def test_acepta_manifiesto_y_limpia_temporal_previo(self):
        anterior = self.datos / 'db_restaurada_abc.sqlite3'
        anterior.write_bytes(b'resto')
        Path(str(anterior) + '-wal').write_bytes(b'resto')
        resultado = self._restaurar(self.copia.with_suffix('.json'))
        self.assertEqual(self._valor(), 'respaldo')
        self.assertFalse(list(self.datos.glob('db_restaurada_*.sqlite3*')))

    def test_restauracion_legacy_wal_con_auxiliares(self):
        with closing(sqlite3.connect(self.copia)) as conexion:
            conexion.execute('PRAGMA journal_mode=WAL')
            conexion.execute("INSERT INTO usuarios_usuario VALUES (2, 'legacy WAL')")
            conexion.commit()
        manifiesto = self.copia.with_suffix('.json')
        datos = json.loads(manifiesto.read_text(encoding='utf-8'))
        datos['tamano'] = self.copia.stat().st_size
        datos['sha256'] = respaldos.hash_archivo(self.copia)
        manifiesto.write_text(json.dumps(datos), encoding='utf-8')
        # Sidecars válidos presentes durante la restauración, como en copias B4.
        with closing(sqlite3.connect(self.copia)) as conexion:
            conexion.execute('PRAGMA journal_mode=WAL')
            conexion.execute("INSERT INTO usuarios_usuario VALUES (3, 'legacy auxiliar')")
            conexion.commit()
            datos['tamano'] = self.copia.stat().st_size
            datos['sha256'] = respaldos.hash_archivo(self.copia)
            manifiesto.write_text(json.dumps(datos), encoding='utf-8')
            resultado = self._restaurar()
        self.assertEqual(self._valor(), 'respaldo')
        self.assertFalse(list(self.datos.glob('db_restaurada_*.sqlite3*')))

    def test_manifiesto_sin_base_indica_archivo_necesario(self):
        manifiesto = self.root / 'ausente.json'
        manifiesto.write_text('{}')
        with self.assertRaisesRegex(respaldos.ErrorRespaldo, r'Indica el archivo \.sqlite3 del respaldo'):
            self._restaurar(manifiesto)

    def test_manifiesto_con_base_no_valida_indica_archivo_necesario(self):
        copia = self.root / 'invalido.sqlite3'
        copia.write_bytes(b'no sqlite')
        manifiesto = copia.with_suffix('.json')
        manifiesto.write_text('{}')
        with self.assertRaisesRegex(respaldos.ErrorRespaldo, r'Indica el archivo \.sqlite3 del respaldo'):
            self._restaurar(manifiesto)

    def test_instancia_activa_se_rechaza(self):
        with bloqueo_instancia(self.datos):
            with self.assertRaisesRegex(respaldos.ErrorRespaldo, 'No se puede restaurar mientras el programa está en ejecución'):
                self._restaurar()
        self.assertEqual(self._valor(), 'actual')

    def test_otro_oserror_muestra_causa_distinta_y_conserva_base(self):
        with patch('desktop.restauracion.restaurar', side_effect=PermissionError('permiso denegado')):
            with self.assertRaisesRegex(respaldos.ErrorRespaldo,
                    'No se pudo restaurar por un error del sistema: permiso denegado'):
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


def bloqueo_activo(directorio):
    from desktop.bloqueo_instancia import detectar_instancia_activa
    return detectar_instancia_activa(directorio)[0]
