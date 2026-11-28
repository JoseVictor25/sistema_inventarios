"""Pruebas del módulo desktop/rutas.py en B3."""
import os
from pathlib import Path
import tempfile
import unittest
import sys

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from desktop.rutas import (
    recursos,
    validar_temporal,
    validar_datos_instalados,
    resolver_rutas,
    obtener_ruta_datos,
    PROGRAM_FILES_DIR,
    PROGRAM_DATA_DIR,
)


class RutasB3Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="Inventarios_test_rutas_")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_recursos_apunta_a_raiz(self):
        rec = recursos()
        self.assertTrue((rec / "backend").is_dir())
        self.assertTrue((rec / "desktop").is_dir())

    def test_validar_temporal_acepta_subcarpeta_temp(self):
        sub = self.root / "subcarpeta"
        resultado = validar_temporal(sub)
        self.assertEqual(resultado, sub.resolve())

    def test_validar_temporal_rechaza_ruta_relativa(self):
        with self.assertRaises(ValueError) as ctx:
            validar_temporal("relativa/temp")
        self.assertIn("absoluta", str(ctx.exception))

    def test_validar_temporal_rechaza_raiz_temp_directa(self):
        with self.assertRaises(ValueError):
            validar_temporal(tempfile.gettempdir())

    def test_validar_datos_instalados_acepta_ruta_exacta(self):
        destino = validar_datos_instalados(PROGRAM_DATA_DIR)
        self.assertEqual(destino, PROGRAM_DATA_DIR.resolve())

    def test_validar_datos_instalados_acepta_ruta_exacta_con_otro_case(self):
        variante = Path(str(PROGRAM_DATA_DIR).upper())
        destino = validar_datos_instalados(variante)
        self.assertEqual(os.path.normcase(str(destino)),
                         os.path.normcase(str(PROGRAM_DATA_DIR.resolve())))

    def test_validar_datos_instalados_rechaza_subcarpeta_arbitraria(self):
        with self.assertRaisesRegex(ValueError, "exactamente"):
            validar_datos_instalados(PROGRAM_DATA_DIR / "subcarpeta_arbitraria")

    def test_validar_datos_instalados_rechaza_ruta_relativa(self):
        with self.assertRaises(ValueError) as ctx:
            validar_datos_instalados("datos_relativos")
        self.assertIn("absoluta", str(ctx.exception))

    def test_validar_datos_instalados_rechaza_program_files(self):
        ruta_pf = PROGRAM_FILES_DIR / "datos"
        with self.assertRaisesRegex(ValueError, "exactamente"):
            validar_datos_instalados(ruta_pf)

    def test_validar_datos_instalados_rechaza_raiz_de_unidad(self):
        with self.assertRaisesRegex(ValueError, "exactamente"):
            validar_datos_instalados("C:\\")

    def test_validar_datos_instalados_rechaza_raiz_program_data(self):
        pd = Path(os.environ.get("ProgramData", "C:/ProgramData"))
        with self.assertRaisesRegex(ValueError, "exactamente"):
            validar_datos_instalados(pd)

    def test_validar_datos_instalados_rechaza_dentro_de_recursos(self):
        ruta_en_codigo = recursos() / "backend" / "datos_inseguros"
        with self.assertRaisesRegex(ValueError, "exactamente"):
            validar_datos_instalados(ruta_en_codigo)

    @unittest.skipUnless(os.name == "nt", "ruta UNC es específica de Windows")
    def test_validar_datos_instalados_rechaza_ruta_unc(self):
        with self.assertRaisesRegex(ValueError, "exactamente"):
            validar_datos_instalados(r"\\servidor\recurso\SistemaInventarios")

    @unittest.skipUnless(os.name == "nt", "symlink requiere Windows")
    def test_validar_datos_instalados_rechaza_alias_symlink(self):
        alias = self.root / "alias_programdata"
        try:
            alias.symlink_to(PROGRAM_DATA_DIR, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink no disponible en este entorno: {exc}")
        with self.assertRaisesRegex(ValueError, "exactamente"):
            validar_datos_instalados(alias)

    def test_resolver_rutas_estructura_canonica(self):
        sub = self.root / "datos_prueba"
        estructura = resolver_rutas(sub)
        self.assertEqual(estructura["datos"], sub)
        self.assertEqual(estructura["db"], sub / "db.sqlite3")
        self.assertEqual(estructura["env"], sub / ".env")
        self.assertEqual(estructura["respaldos"], sub / "respaldos")
        self.assertEqual(estructura["logs"], sub / "logs")
        self.assertEqual(estructura["operador"], sub / "operador.json")
        self.assertEqual(estructura["lock"], sub / ".respaldos.lock")

    def test_obtener_ruta_datos_distingue_temporal_e_instalado(self):
        class ArgsMock:
            datos_temporales = str(self.root / "temp_sub")
            datos_instalados = None

        modo, ruta = obtener_ruta_datos(ArgsMock())
        self.assertEqual(modo, "temporal")
        self.assertEqual(ruta, (self.root / "temp_sub").resolve())

        class ArgsInstaladoMock:
            datos_temporales = None
            datos_instalados = str(PROGRAM_DATA_DIR)

        modo, ruta = obtener_ruta_datos(ArgsInstaladoMock())
        self.assertEqual(modo, "instalado")
        self.assertEqual(ruta, PROGRAM_DATA_DIR.resolve())

    def test_obtener_ruta_datos_rechaza_instalado_arbitrario(self):
        class ArgsInstaladoInvalido:
            datos_temporales = None
            datos_instalados = str(self.root / "instalado_sub")

        with self.assertRaisesRegex(ValueError, "exactamente"):
            obtener_ruta_datos(ArgsInstaladoInvalido())


if __name__ == "__main__":
    unittest.main()
