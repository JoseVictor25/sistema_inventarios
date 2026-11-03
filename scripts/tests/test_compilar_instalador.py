import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

RAIZ = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('compilar_instalador', RAIZ / 'scripts/compilar_instalador.py')
modulo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(modulo)


class InstaladorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='Inventarios_B3_test_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paquete = self.root / 'paquete'
        (self.paquete / '_internal').mkdir(parents=True)
        (self.paquete / 'SistemaInventarios.exe').write_bytes(b'fixture-no-ejecutable')
        (self.paquete / '_internal/app.css').write_text('body {}')

    def test_paquete_completo_copiado_con_hashes(self):
        salida = self.root / 'salida'
        contenido = modulo.preparar(self.paquete, salida)
        self.assertEqual(len(contenido), 2)
        for fila in contenido:
            self.assertEqual(modulo.sha(salida / 'payload' / fila['archivo']), fila['sha256'])
        self.assertNotIn('*', (salida / 'archivos.iss').read_text(encoding='utf-8-sig'))

    def test_rechaza_archivos_protegidos_y_datos(self):
        for nombre in ['.env', '.env.local', 'db.sqlite3', 'db.sqlite3-wal', 'sistema.log',
                       'respaldo.bak', 'REPORTE_MIGRACIONES_FASE1.md', 'SOLUCION_ERROR_TERMINAL.md']:
            with self.subTest(nombre=nombre):
                f = self.paquete / nombre
                f.write_text('ficticio')
                with self.assertRaises(ValueError):
                    modulo.inspeccionar(self.paquete)
                f.unlink()

    def test_rechaza_directorios_privados(self):
        d = self.paquete / 'respaldos'
        d.mkdir()
        (d / 'copia.txt').write_text('ficticio')
        with self.assertRaises(ValueError):
            modulo.inspeccionar(self.paquete)

    def test_rechaza_paquete_incompleto(self):
        (self.paquete / 'SistemaInventarios.exe').unlink()
        with self.assertRaises(ValueError):
            modulo.inspeccionar(self.paquete)

    def test_rechaza_inyeccion_en_lista_inno(self):
        (self.paquete / 'archivo;ajeno.txt').write_text('ficticio')
        with self.assertRaises(ValueError):
            modulo.inspeccionar(self.paquete)

    def test_instalacion_bloqueada_y_contrato(self):
        texto = (RAIZ / 'desktop/installer/setup.iss').read_text(encoding='utf-8')
        codigo = texto.split('function InitializeSetup(): Boolean;')[1]
        self.assertIn('Result := False;', codigo)
        self.assertNotIn('Result := True;', codigo)
        self.assertIn('E3488284-3044-4D29-AB90-33D28FD02467', texto)
        self.assertIn('"0.10.0"', texto)
        self.assertIn('PrivilegesRequired=admin', texto)
        self.assertIn('B3_BLOQUEADO', texto)
        self.assertIn('{commonappdata}\\SistemaInventarios', texto)
        self.assertIn('uninsneveruninstall', texto)
        self.assertNotIn('\n[Run]', texto)
        self.assertNotIn('\n[UninstallDelete]', texto)

    def test_descubrimiento_iscc_encuentra_compilador(self):
        iscc = modulo.buscar_iscc()
        if Path('E:/Inno Setup 7/ISCC.exe').is_file():
            self.assertIsNotNone(iscc)
            self.assertTrue(iscc.is_file())


if __name__ == '__main__':
    unittest.main()
