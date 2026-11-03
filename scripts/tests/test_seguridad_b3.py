"""Pruebas del módulo desktop/seguridad.py en B3."""
import json
import os
from pathlib import Path
import tempfile
import unittest
import sys

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from desktop.seguridad import (
    obtener_sid_actual,
    es_administrador,
    obtener_cuenta_actual,
    leer_registro_operador,
    registrar_operador,
    validar_operador,
    migrar_operador,
    generar_comandos_icacls,
    aplicar_permisos_seguros,
    inspeccionar_permisos_icacls,
    identificar_sid_operador,
    verificar_directorio_seguro,
    SID_SYSTEM,
    SID_ADMINISTRADORES,
    SID_USERS,
    SID_AUTHENTICATED_USERS,
    SID_EVERYONE,
)


class SeguridadB3Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="Inventarios_test_seguridad_")
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_obtener_sid_actual_retorna_sid_valido(self):
        sid = obtener_sid_actual()
        self.assertTrue(isinstance(sid, str))
        self.assertTrue(sid.startswith("S-1-"))

    def test_obtener_sid_actual_acepta_simulacion(self):
        simulado = "S-1-5-21-999999999-888888888-777777777-1005"
        os.environ["INVENTARIOS_OPERADOR_SID_SIMULADO"] = simulado
        try:
            self.assertEqual(obtener_sid_actual(), simulado)
        finally:
            del os.environ["INVENTARIOS_OPERADOR_SID_SIMULADO"]

    def test_registrar_operador_crea_operador_json_valido(self):
        sid = "S-1-5-21-111111111-222222222-333333333-1001"
        resultado = registrar_operador(self.root, sid, cuenta="TESTDOM\\operador1")
        self.assertEqual(resultado["sid"], sid)
        self.assertEqual(resultado["cuenta"], "TESTDOM\\operador1")
        self.assertEqual(resultado["version"], "0.10.0")

        archivo = self.root / "operador.json"
        self.assertTrue(archivo.is_file())
        leido = json.loads(archivo.read_text(encoding="utf-8"))
        self.assertEqual(leido["sid"], sid)

    def test_registrar_operador_rechaza_sid_invalido(self):
        with self.assertRaises(ValueError):
            registrar_operador(self.root, "invalido")

    def test_registrar_operador_rechaza_sobrescribir_otro_sid_sin_migracion(self):
        sid1 = "S-1-5-21-111111111-222222222-333333333-1001"
        sid2 = "S-1-5-21-999999999-888888888-777777777-1002"
        registrar_operador(self.root, sid1)
        with self.assertRaises(ValueError) as ctx:
            registrar_operador(self.root, sid2)
        self.assertIn("migrar_operador", str(ctx.exception))

    def test_validar_operador_permite_operador_registrado(self):
        sid = "S-1-5-21-111111111-222222222-333333333-1001"
        registrar_operador(self.root, sid)
        self.assertTrue(validar_operador(self.root, sid_actual=sid))

    def test_validar_operador_rechaza_operador_diferente(self):
        sid1 = "S-1-5-21-111111111-222222222-333333333-1001"
        sid2 = "S-1-5-21-999999999-888888888-777777777-1002"
        registrar_operador(self.root, sid1)
        with self.assertRaises(PermissionError) as ctx:
            validar_operador(self.root, sid_actual=sid2)
        self.assertIn("no autorizado", str(ctx.exception))

    def test_migrar_operador_requiere_autorizacion_admin(self):
        sid1 = "S-1-5-21-111111111-222222222-333333333-1001"
        sid2 = "S-1-5-21-999999999-888888888-777777777-1002"
        registrar_operador(self.root, sid1)
        with self.assertRaises(PermissionError) as ctx:
            migrar_operador(self.root, sid2, autorizacion_admin=False)
        self.assertIn("administrativa", str(ctx.exception))

    def test_migrar_operador_con_admin_conserva_historial_y_bitacora(self):
        sid1 = "S-1-5-21-111111111-222222222-333333333-1001"
        sid2 = "S-1-5-21-999999999-888888888-777777777-1002"
        registrar_operador(self.root, sid1, cuenta="DOM\\antiguo")
        nuevo = migrar_operador(self.root, sid2, nuevo_cuenta="DOM\\nuevo", autorizacion_admin=True)

        self.assertEqual(nuevo["sid"], sid2)
        self.assertEqual(nuevo["cuenta"], "DOM\\nuevo")
        self.assertEqual(len(nuevo["historial_migraciones"]), 1)
        self.assertEqual(nuevo["historial_migraciones"][0]["sid_anterior"], sid1)

        log = (self.root / "logs" / "migracion_operador.log").read_text(encoding="utf-8")
        self.assertIn(sid1, log)
        self.assertIn(sid2, log)
        self.assertIn("CAMBIO CONTROLADO DE OPERADOR", log)

    def test_generar_comandos_icacls_incluye_sids_esenciales(self):
        sid = "S-1-5-21-111111111-222222222-333333333-1001"
        cmds = generar_comandos_icacls(self.root, sid)
        self.assertEqual(len(cmds), 4)
        texto = " ".join(" ".join(c) for c in cmds)
        self.assertIn("/inheritance:r", texto)
        self.assertIn(SID_SYSTEM, texto)
        self.assertIn(SID_ADMINISTRADORES, texto)
        self.assertIn(sid, texto)
        self.assertIn(SID_USERS, texto)
        self.assertIn(SID_AUTHENTICATED_USERS, texto)
        self.assertIn(SID_EVERYONE, texto)

    @unittest.skipIf(os.name != "nt", "icacls solo en Windows")
    def test_aplicar_y_verificar_acls_en_directorio_temporal(self):
        sub = self.root / "datos_acl"
        sub.mkdir()
        sid = obtener_sid_actual()
        aplicar_permisos_seguros(sub, sid)
        inspeccion = inspeccionar_permisos_icacls(sub)
        self.assertFalse(inspeccion["tiene_inseguros"])
        self.assertTrue(inspeccion["seguro"])

    def test_identificar_sid_operador_parametro_explicito(self):
        sid = "S-1-5-21-999999999-888888888-777777777-1002"
        resultado = identificar_sid_operador(parametro_sid=sid)
        self.assertEqual(resultado, sid)

    def test_identificar_sid_operador_rechaza_formato_invalido(self):
        with self.assertRaises(ValueError) as ctx:
            identificar_sid_operador(parametro_sid="cuenta_sin_sid")
        self.assertIn("no es válido", str(ctx.exception))

    def test_verificar_directorio_seguro_rechaza_operador_distinto(self):
        sid1 = "S-1-5-21-111111111-222222222-333333333-1001"
        sid2 = "S-1-5-21-999999999-888888888-777777777-1002"
        registrar_operador(self.root, sid1)
        with self.assertRaises(PermissionError) as ctx:
            verificar_directorio_seguro(self.root, sid_esperado=sid2)
        self.assertIn("no coincide", str(ctx.exception))

    def test_verificar_directorio_seguro_acepta_operador_coincidente(self):
        sid1 = "S-1-5-21-111111111-222222222-333333333-1001"
        registrar_operador(self.root, sid1)
        self.assertTrue(verificar_directorio_seguro(self.root, sid_esperado=sid1))


if __name__ == "__main__":
    unittest.main()
