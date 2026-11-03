"""Pruebas del módulo desktop/mantenimiento.py en B3."""
import hashlib
import logging
import os
from pathlib import Path
import tempfile
import unittest
import sys

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from desktop.inicializacion import configurar
from desktop.mantenimiento import (
    parsear_version,
    detectar_instalacion_previa,
    detectar_procesos_activos,
    verificar_compatibilidad_version,
    crear_respaldo_seguridad,
    ensayar_migraciones_en_copia,
    planificar_actualizacion,
    documentar_recuperacion_fallida,
)


def sha(ruta):
    with Path(ruta).open("rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class MantenimientoActualizacionesB3Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="Inventarios_test_mantenimiento_")
        self.root = Path(self.temp_dir.name)
        self.sid_test = "S-1-5-21-123456789-987654321-112233445-1001"

    def tearDown(self):
        try:
            from django.db import connections
            connections.close_all()
        except Exception:
            pass
        for handler in logging.root.handlers[:]:
            try:
                handler.close()
                logging.root.removeHandler(handler)
            except Exception:
                pass
        for log_obj in list(logging.Logger.manager.loggerDict.values()):
            if hasattr(log_obj, 'handlers'):
                for h in log_obj.handlers[:]:
                    try:
                        h.close()
                        log_obj.removeHandler(h)
                    except Exception:
                        pass
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_parsear_version_correcta(self):
        self.assertEqual(parsear_version("0.10.0"), (0, 10, 0))
        self.assertEqual(parsear_version("1.2.3-rc1"), (1, 2, 3))
        self.assertEqual(parsear_version("2.1"), (2, 1, 0))

    def test_verificar_compatibilidad_version_rechaza_downgrade(self):
        self.assertTrue(verificar_compatibilidad_version("0.10.0", "0.10.1"))
        self.assertTrue(verificar_compatibilidad_version("0.10.0", "0.11.0"))
        self.assertTrue(verificar_compatibilidad_version("0.10.0", "1.0.0"))
        self.assertTrue(verificar_compatibilidad_version("0.10.0", "0.10.0"))

        with self.assertRaises(ValueError) as ctx:
            verificar_compatibilidad_version("0.10.0", "0.9.9")
        self.assertIn("Downgrade no permitido", str(ctx.exception))

    def test_detectar_instalacion_previa(self):
        datos = self.root / "datos_detectar"
        # Antes de inicializar
        info_antes = detectar_instalacion_previa(datos)
        self.assertFalse(info_antes["instalada"])

        # Inicializar
        configurar(datos, autorizar_nueva=True, modo="instalado", sid_operador=self.sid_test)
        info_despues = detectar_instalacion_previa(datos)
        self.assertTrue(info_despues["instalada"])
        self.assertEqual(info_despues["version"], "0.10.0")
        self.assertEqual(info_despues["operador_sid"], self.sid_test)

    def test_detectar_procesos_activos_por_lock_o_parcial(self):
        datos = self.root / "datos_procesos"
        configurar(datos, autorizar_nueva=True, modo="instalado", sid_operador=self.sid_test)

        # Sin procesos activos
        activo, razon = detectar_procesos_activos(datos)
        self.assertFalse(activo)

        # Simular respaldo parcial en curso
        respaldos_dir = datos / "respaldos"
        parcial = respaldos_dir / "respaldo_temporal.partial"
        parcial.touch()
        activo, razon = detectar_procesos_activos(datos)
        self.assertTrue(activo)
        self.assertIn("temporal", razon.lower())
        parcial.unlink()

        # Simular cerrojo msvcrt activo
        lock_file = datos / ".respaldos.lock"
        with lock_file.open("a+b") as f:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                activo, razon = detectar_procesos_activos(datos)
                self.assertTrue(activo)
                self.assertIn("ejecución", razon.lower())
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

    def test_ensayo_migraciones_no_altera_base_original(self):
        datos = self.root / "datos_ensayo"
        configurar(datos, autorizar_nueva=True, modo="instalado", sid_operador=self.sid_test)

        db_original = datos / "db.sqlite3"
        hash_antes = sha(db_original)

        # Ejecutar ensayo en copia
        resultado = ensayar_migraciones_en_copia(datos)
        self.assertTrue(resultado["ensayo_exitoso"])
        self.assertTrue(resultado["compatible"])

        # Confirmar que la base original NO fue alterada
        hash_despues = sha(db_original)
        self.assertEqual(hash_antes, hash_despues)

    def test_planificar_actualizacion_flujo_completo(self):
        datos = self.root / "datos_actualizar"
        configurar(datos, autorizar_nueva=True, modo="instalado", sid_operador=self.sid_test)

        plan = planificar_actualizacion(datos, version_nueva="0.10.1", autorizar_migraciones=True)
        self.assertTrue(plan["preparada"])
        self.assertEqual(plan["version_previa"], "0.10.0")
        self.assertEqual(plan["version_nueva"], "0.10.1")
        self.assertTrue(Path(plan["respaldo_previo"]).is_file())
        self.assertEqual(sha(plan["respaldo_previo"]), plan["respaldo_sha256"])

        # Documentación de recuperación
        doc = documentar_recuperacion_fallida(datos, plan["respaldo_previo"])
        self.assertIn("ROLLBACK", doc)
        self.assertIn(plan["respaldo_previo"], doc)


if __name__ == "__main__":
    unittest.main()
