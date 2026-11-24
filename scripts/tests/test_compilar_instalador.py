import importlib.util
import os
from pathlib import Path
import re
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

    def test_instalador_predeterminado_sigue_bloqueado_y_conserva_nombre(self):
        texto = (RAIZ / 'desktop/installer/setup.iss').read_text(encoding='utf-8')
        codigo = texto.split('function InitializeSetup(): Boolean;')[1]
        self.assertIn('#else\n  SuppressibleMsgBox(Msg, mbError, MB_OK, IDOK);\n  Result := False;\n#endif', codigo)
        self.assertIn('OutputBaseFilename=Instalador_Sistema_Inventarios_0.10.0_B3_BLOQUEADO', texto)
        self.assertIn('AppVerName={#ProductName} {#ProductVersion} - PRELIMINAR B3 PERSISTENTE', texto)
        self.assertIn('E3488284-3044-4D29-AB90-33D28FD02467', texto)
        self.assertIn('"0.10.0"', texto)
        self.assertIn('PrivilegesRequired=admin', texto)

    def test_initialize_setup_call_graph_no_expande_app(self):
        texto = (RAIZ / 'desktop/installer/setup.iss').read_text(encoding='utf-8')
        codigo = texto.split('[Code]', 1)[1]
        inicios = list(re.finditer(r'(?im)^\s*(?:function|procedure)\s+(\w+)\b', codigo))
        rutinas = {
            match.group(1).lower(): codigo[match.end():inicios[i + 1].start() if i + 1 < len(inicios) else len(codigo)]
            for i, match in enumerate(inicios)
        }
        pendientes = ['initializesetup']
        visitadas = set()
        while pendientes:
            nombre = pendientes.pop()
            if nombre in visitadas or nombre not in rutinas:
                continue
            visitadas.add(nombre)
            cuerpo = rutinas[nombre]
            self.assertNotIn('{app}', cuerpo.lower(), f'{nombre} expande {{app}} antes de elegir destino')
            llamadas = re.findall(r'\b([A-Za-z_]\w*)\s*\(', cuerpo)
            pendientes.extend(llamada.lower() for llamada in llamadas if llamada.lower() in rutinas)

    def test_variante_vm_solo_se_define_con_opcion_explicita_y_es_distintiva(self):
        texto = (RAIZ / 'desktop/installer/setup.iss').read_text(encoding='utf-8')
        script = (RAIZ / 'scripts/compilar_instalador.py').read_text(encoding='utf-8')
        normal = modulo.comando_compilacion(Path('C:/ISCC.exe'), self.root, False)
        vm = modulo.comando_compilacion(Path('C:/ISCC.exe'), self.root, True)
        self.assertNotIn('/DSOLO_PRUEBAS_VM', normal)
        self.assertIn('/DSOLO_PRUEBAS_VM', vm)
        self.assertIn("parser.add_argument('--solo-pruebas-vm'", script)
        self.assertIn('#ifdef SOLO_PRUEBAS_VM', texto)
        self.assertIn('OutputBaseFilename=Instalador_Sistema_Inventarios_0.10.0_SOLO_PRUEBAS_VM_NO_ENTREGAR', texto)
        self.assertIn('AppVerName=SOLO PRUEBAS VM - NO ENTREGAR AL CLIENTE', texto)
        self.assertIn('SOLO PRUEBAS VM - NO ENTREGAR AL CLIENTE', texto.split('function InitializeSetup(): Boolean;')[1])
        self.assertNotIn('SOLO_PRUEBAS_VM', normal[-1])
        self.assertNotIn(str(RAIZ), str(self.root))

    def test_contrato_windows_11_seguridad_y_accesos_directos(self):
        texto = (RAIZ / 'desktop/installer/setup.iss').read_text(encoding='utf-8')
        self.assertIn('MinVersion=10.0.22000', texto)
        self.assertIn('{commonappdata}\\SistemaInventarios', texto)
        self.assertIn('uninsneveruninstall', texto)
        self.assertNotIn('\n[Run]', texto)
        self.assertNotIn('\n[UninstallRun]', texto)
        self.assertNotIn('\n[UninstallDelete]', texto)
        iconos = texto.split('[Icons]')[1].split('; POL')[0]
        self.assertIn('Filename: "{app}\\SistemaInventarios.exe"; WorkingDir: "{app}"', iconos)
        self.assertIn('Parameters: "--operador-sid={param:OPERATOR_SID|}"', iconos)
        self.assertNotIn('--inicializar', iconos)
        self.assertIn('Windows 11 de 64 bits', texto)

    def test_inspeccion_rechaza_mismos_archivos_en_ambas_variantes(self):
        for variante in ('predeterminada bloqueada', 'solo pruebas VM'):
            for nombre in ['.env', '.env.local', 'db.sqlite3', 'db.sqlite3-wal', 'sistema.log',
                           'respaldo.bak', 'REPORTE_MIGRACIONES_FASE1.md']:
                with self.subTest(variante=variante, nombre=nombre):
                    archivo = self.paquete / nombre
                    archivo.write_text('ficticio')
                    with self.assertRaises(ValueError):
                        modulo.inspeccionar(self.paquete)
                    archivo.unlink()

    def test_directorio_temporal_de_salida_fuera_del_repositorio(self):
        temporal = Path(tempfile.gettempdir()).resolve()
        self.assertFalse(temporal == RAIZ or temporal.is_relative_to(RAIZ))

    def test_accesos_directos_transmiten_operador_y_launcher_admite_primer_inicio(self):
        texto = (RAIZ / 'desktop/installer/setup.iss').read_text(encoding='utf-8')
        launcher = (RAIZ / 'desktop/launcher.py').read_text(encoding='utf-8')
        iconos = texto.split('[Icons]')[1].split('; POL')[0]
        self.assertIn('Parameters: "--operador-sid={param:OPERATOR_SID|}"', iconos)
        self.assertIn("autorizar_nueva=(args.inicializar or (getattr(sys, 'frozen', False) and modo == 'instalado'))", launcher)
        self.assertIn('SOLO PRUEBAS VM requiere /OPERATOR_SID', texto)

    def test_descubrimiento_iscc_encuentra_compilador(self):
        iscc = modulo.buscar_iscc()
        if Path('E:/Inno Setup 7/ISCC.exe').is_file():
            self.assertIsNotNone(iscc)
            self.assertTrue(iscc.is_file())


if __name__ == '__main__':
    unittest.main()
