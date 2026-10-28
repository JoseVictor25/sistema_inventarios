"""Archivos SQLite ficticios independientes; no utiliza la base Django activa."""
from datetime import datetime, timezone
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch
from uuid import UUID
from django.test import SimpleTestCase
from apps.core import respaldos as r


class RespaldosTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='inventarios_test_backup_')
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.origen = self.raiz / 'fuente.sqlite3'
        self.destino = self.raiz / 'copias'
        with closing(sqlite3.connect(self.origen)) as c, c:
            for tabla in r.TABLAS - {'django_migrations'}:
                c.execute(f'CREATE TABLE "{tabla}" (id INTEGER PRIMARY KEY, valor TEXT)')
            c.execute('CREATE TABLE django_migrations (app TEXT, name TEXT)')
            c.execute("INSERT INTO django_migrations VALUES ('usuarios', '0001_initial')")
            c.execute("INSERT INTO usuarios_usuario VALUES (1, 'usuario ficticio')")
            c.execute('CREATE TABLE hijo (id INTEGER PRIMARY KEY, usuario_id INTEGER REFERENCES usuarios_usuario(id))')
            c.execute('INSERT INTO hijo VALUES (1,1)')
        self.hash_original = r.hash_archivo(self.origen)

    def crear(self, conservar=30):
        return r.crear_copia(self.origen, self.destino, conservar)

    def test_copia_integridad_manifiesto_fuente_intacta(self):
        resultado = self.crear()
        copia = self.destino / resultado['archivo']
        self.assertEqual(r.verificar_copia(copia)['sha256'], resultado['sha256'])
        self.assertEqual(r.hash_archivo(self.origen), self.hash_original)
        self.assertEqual(json.loads(copia.with_suffix('.json').read_text())['motor'], 'inventarios-backup-v1')
        self.assertTrue(r.listar_copias(self.destino)[0]['verificado'])
        self.assertFalse(list(self.destino.glob('*.partial')))

    def test_restaurar_solo_a_archivo_nuevo_temporal(self):
        resultado = self.crear()
        copia = self.destino / resultado['archivo']
        restaurada = self.raiz / 'recuperada.sqlite3'
        with restaurada.open('xb'):
            pass
        origen = sqlite3.connect(copia.as_uri() + '?mode=ro', uri=True)
        destino = sqlite3.connect(restaurada)
        try:
            origen.backup(destino)
            self.assertEqual(destino.execute('SELECT * FROM usuarios_usuario').fetchall(), [(1, 'usuario ficticio')])
            self.assertEqual(destino.execute('SELECT * FROM hijo').fetchall(), [(1, 1)])
        finally:
            origen.close()
            destino.close()
        r.verificar_copia(restaurada)
        self.assertEqual(r.hash_archivo(self.origen), self.hash_original)

    def test_archivo_corrupto(self):
        corrupto = self.raiz / 'corrupto.sqlite3'
        corrupto.write_bytes(b'no es SQLite')
        with self.assertRaises(r.ErrorRespaldo):
            r.verificar_copia(corrupto)

    def test_tablas_esenciales_y_claves_foraneas(self):
        with closing(sqlite3.connect(self.origen)) as c, c:
            c.execute('INSERT INTO hijo VALUES (2,999)')
        with self.assertRaises(r.ErrorRespaldo):
            self.crear()
        with closing(sqlite3.connect(self.origen)) as c, c:
            c.execute('DELETE FROM hijo WHERE id=2')
            c.execute('DROP TABLE ventas_venta')
        with self.assertRaises(r.ErrorRespaldo):
            self.crear()
        self.assertFalse(list(self.destino.glob('respaldo_*.sqlite3')))

    def test_colision_no_sobrescribe_ni_borra(self):
        with patch.object(r, 'uuid4', return_value=UUID(int=1)), patch.object(r, 'datetime') as reloj:
            reloj.now.return_value = datetime(2026, 10, 27, tzinfo=timezone.utc)
            primero = self.crear()
            with self.assertRaises(r.ErrorRespaldo):
                self.crear()
        self.assertEqual(r.hash_archivo(self.destino / primero['archivo']), primero['sha256'])

    def test_colision_provisional_no_borra_archivo_ajeno(self):
        self.destino.mkdir()
        archivo = self.destino / ('respaldo_20261027_000000_' + UUID(int=1).hex + '.sqlite3.partial')
        archivo.write_bytes(b'provisional anterior')
        with patch.object(r, 'uuid4', return_value=UUID(int=1)), patch.object(r, 'datetime') as reloj:
            reloj.now.return_value = datetime(2026, 10, 27, tzinfo=timezone.utc)
            with self.assertRaises(r.ErrorRespaldo):
                self.crear()
        self.assertEqual(archivo.read_bytes(), b'provisional anterior')

    def test_retencion_solo_copias_gestionadas(self):
        primero = self.crear(2)
        desconocido = self.destino / 'respaldo_antiguo.sqlite3'
        desconocido.write_bytes(b'archivo ajeno')
        segundo = self.crear(2)
        tercero = self.crear(2)
        self.assertFalse((self.destino / primero['archivo']).exists())
        for nombre in (segundo['archivo'], tercero['archivo'], desconocido.name):
            self.assertTrue((self.destino / nombre).exists())

    def test_copia_alterada_no_se_purga(self):
        primero = self.crear(1)
        archivo = self.destino / primero['archivo']
        archivo.write_bytes(b'alterada')
        self.crear(1)
        self.assertTrue(archivo.exists())
        self.assertFalse(next(f for f in r.listar_copias(self.destino) if f['nombre'] == archivo.name)['verificado'])

    def test_fallo_no_purga_copia_previa(self):
        primero = self.crear(1)
        with patch.object(r, 'verificar_copia', side_effect=r.ErrorRespaldo('simulación')):
            with self.assertRaises(r.ErrorRespaldo):
                self.crear(1)
        self.assertTrue((self.destino / primero['archivo']).exists())
        self.assertFalse(list(self.destino.glob('*.partial')))

    def test_fallo_retencion_conserva_nueva_y_advierte(self):
        with patch.object(r, '_retener', side_effect=PermissionError('simulación')):
            resultado = self.crear()
        self.assertTrue(resultado['advertencia'])
        self.assertTrue((self.destino / resultado['archivo']).exists())

    def test_rutas_y_retencion_invalidas(self):
        for conservar in (0, -1, True, '30'):
            with self.subTest(conservar=conservar), self.assertRaises(r.ErrorRespaldo):
                self.crear(conservar)
        for directorio in (self.origen, self.origen.parent):
            with self.assertRaises(r.ErrorRespaldo):
                r.crear_copia(self.origen, directorio, 30)
        with self.assertRaises(r.ErrorRespaldo):
            r.crear_copia(self.raiz / 'noexiste', self.destino, 30)
        self.assertFalse((self.raiz / 'noexiste').exists())

    def test_nombre_unico_en_creaciones_sucesivas(self):
        a, b = self.crear(), self.crear()
        self.assertNotEqual(a['archivo'], b['archivo'])

    def test_tiempo_agotado_limpia_provisional(self):
        with patch.object(r.time, 'monotonic', side_effect=[0, 121]):
            with self.assertRaisesRegex(r.ErrorRespaldo, 'tiempo'):
                self.crear()
        self.assertFalse(list(self.destino.glob('*.partial')))
        self.assertFalse(list(self.destino.glob('*.sqlite3')))

    def test_fallo_publicar_manifiesto_no_retiene_y_deja_copia_no_gestionada(self):
        anterior = self.crear(1)
        publicar = r._publicar
        def fallar(provisional, final):
            if final.suffix == '.json':
                raise PermissionError('simulación')
            publicar(provisional, final)
        with patch.object(r, '_publicar', side_effect=fallar), self.assertRaises(r.ErrorRespaldo):
            self.crear(1)
        self.assertTrue((self.destino / anterior['archivo']).exists())
        self.assertEqual(sum(not fila['verificado'] for fila in r.listar_copias(self.destino)), 1)
        self.assertFalse(list(self.destino.glob('*.partial')))

    def test_bloqueo_entre_procesos(self):
        self.destino.mkdir()
        codigo = "from pathlib import Path; from apps.core.respaldos import _bloqueo; import sys\nwith _bloqueo(Path(sys.argv[1])):\n print('LISTO', flush=True)\n sys.stdin.readline()"
        proceso = subprocess.Popen([sys.executable, '-c', codigo, str(self.destino)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(proceso.stdout.readline().strip(), 'LISTO')
            with self.assertRaisesRegex(r.ErrorRespaldo, 'otra operación'):
                self.crear()
            proceso.communicate('\n', timeout=15)
        finally:
            if proceso.poll() is None:
                proceso.kill()
                proceso.communicate()
        self.crear()

    def test_copia_con_conexion_wal_abierta(self):
        c = sqlite3.connect(self.origen)
        try:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute("INSERT INTO usuarios_usuario VALUES (2, 'confirmado en WAL')")
            c.commit()
            c.execute("INSERT INTO usuarios_usuario VALUES (3, 'sin confirmar')")
            copia = self.destino / self.crear()['archivo']
            with closing(sqlite3.connect(copia)) as recuperada:
                self.assertEqual(recuperada.execute('SELECT COUNT(*) FROM usuarios_usuario').fetchone()[0], 2)
            c.rollback()
        finally:
            c.close()
