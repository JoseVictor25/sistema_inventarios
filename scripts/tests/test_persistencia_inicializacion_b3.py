"""Pruebas de primer arranque, persistencia y recuperación segura en B3."""
import logging
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import sys

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from desktop.inicializacion import configurar, recuperar_inicializacion_incompleta
from desktop.seguridad import leer_registro_operador


class PersistenciaInicializacionB3Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="Inventarios_test_init_")
        self.root = Path(self.temp_dir.name)
        self.sid_test = "S-1-5-21-123456789-987654321-112233445-1001"

    def tearDown(self):
        try:
            from django.db import connections
            connections.close_all()
        except Exception:
            pass
        # Cerrar handlers de logging que mantienen abierto sistema.log en Windows
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

    def test_primera_inicializacion_genera_secretos_y_base(self):
        datos = self.root / "datos_nuevos"
        configurar(datos, autorizar_nueva=True, modo="instalado", sid_operador=self.sid_test)

        base = datos / "db.sqlite3"
        entorno = datos / ".env"
        operador = datos / "operador.json"

        self.assertTrue(base.is_file())
        self.assertTrue(entorno.is_file())
        self.assertTrue(operador.is_file())

        texto_env = entorno.read_text(encoding="utf-8")
        self.assertIn("SECRET_KEY=", texto_env)
        clave = texto_env.split("SECRET_KEY=")[1].strip()
        self.assertGreaterEqual(len(clave), 50)

        # Verificar operador registrado
        reg = leer_registro_operador(datos)
        self.assertEqual(reg["sid"], self.sid_test)

        # Verificar tablas creadas en SQLite
        con = sqlite3.connect(base.resolve().as_uri() + "?mode=ro", uri=True)
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        self.assertIn("django_migrations", tablas)
        self.assertIn("usuarios_usuario", tablas)

    def test_segundo_arranque_conserva_datos_y_secret_key(self):
        datos = self.root / "datos_existentes"
        configurar(datos, autorizar_nueva=True, modo="instalado", sid_operador=self.sid_test)

        entorno = datos / ".env"
        base = datos / "db.sqlite3"
        clave_primera = entorno.read_text(encoding="utf-8")
        tamano_base_primera = base.stat().st_size

        # Segundo arranque (sin autorizar_nueva)
        configurar(datos, autorizar_nueva=False, modo="instalado", sid_operador=self.sid_test)

        clave_segunda = entorno.read_text(encoding="utf-8")
        self.assertEqual(clave_primera, clave_segunda)
        self.assertEqual(base.stat().st_size, tamano_base_primera)

    def test_instalacion_incompleta_falta_base_no_regenera_env(self):
        datos = self.root / "datos_incompletos_base"
        datos.mkdir()
        entorno = datos / ".env"
        entorno.write_text("SECRET_KEY=clave_existente_previa_de_mas_de_cincuenta_caracteres_seguros_123456\n")

        with self.assertRaises(ValueError) as ctx:
            configurar(datos, autorizar_nueva=False, modo="instalado", sid_operador=self.sid_test)
        self.assertIn("incompleta", str(ctx.exception).lower())
        # Confirmar que .env previo no fue alterado ni borrado
        self.assertIn("clave_existente_previa", entorno.read_text(encoding="utf-8"))

    def test_instalacion_incompleta_falta_env_no_sobrescribe_base(self):
        datos = self.root / "datos_incompletos_env"
        datos.mkdir()
        base = datos / "db.sqlite3"
        base.write_bytes(b"SQLite format 3\x00contenido-ficticio-protegido")

        with self.assertRaises(ValueError) as ctx:
            configurar(datos, autorizar_nueva=False, modo="instalado", sid_operador=self.sid_test)
        self.assertIn("incompleta", str(ctx.exception).lower())
        # Confirmar que base previa no fue alterada
        self.assertEqual(base.read_bytes(), b"SQLite format 3\x00contenido-ficticio-protegido")

    def test_recuperacion_segura_de_inicializacion_interrumpida(self):
        datos = self.root / "datos_interrumpidos"
        datos.mkdir()
        entorno = datos / ".env"
        entorno.write_text("SECRET_KEY=clave_previa_valida_para_recuperacion_de_mas_de_cincuenta_caracteres_12345\n")
        # db.sqlite3 vacía creada por fallo previo
        base = datos / "db.sqlite3"
        base.touch()

        # Sin forzar debe fallar
        with self.assertRaises(ValueError) as ctx:
            recuperar_inicializacion_incompleta(datos, forzar=False, modo="instalado", sid_operador=self.sid_test)
        self.assertIn("forzar=True", str(ctx.exception))

        # Con forzar=True y base vacía debe recuperar exitosamente
        recuperar_inicializacion_incompleta(datos, forzar=True, modo="instalado", sid_operador=self.sid_test)
        self.assertGreater(base.stat().st_size, 0)
        self.assertIn("clave_previa_valida", entorno.read_text(encoding="utf-8"))

    def test_recuperacion_rechaza_reinicializar_base_con_tablas(self):
        datos = self.root / "datos_con_tablas"
        configurar(datos, autorizar_nueva=True, modo="instalado", sid_operador=self.sid_test)

        # Intentar recuperar forzadamente una base que ya tiene tablas reales
        with self.assertRaises(ValueError) as ctx:
            recuperar_inicializacion_incompleta(datos, forzar=True, modo="instalado", sid_operador=self.sid_test)
        self.assertIn("protegidos", str(ctx.exception).lower())

    def test_reinstalacion_simulada_conserva_datos_y_bloquea_primer_dueno(self):
        datos = self.root / "datos_reinstalacion"
        configurar(datos, autorizar_nueva=True, modo="instalado", sid_operador=self.sid_test)

        # Insertar un usuario para simular Dueño existente
        from apps.usuarios.models import Usuario, Rol
        rol_dueno = Rol.objects.get(nombre="Dueño")
        usuario = Usuario.objects.create_user(username="operador_dueno", password="Password123!", rol=rol_dueno)

        # Simular reinstalación: se ejecuta configurar con autorizar_nueva=False (o arranque de nueva versión de binarios)
        configurar(datos, autorizar_nueva=False, modo="instalado", sid_operador=self.sid_test)

        # Confirmar que el usuario sigue existiendo intacto
        self.assertTrue(Usuario.objects.filter(username="operador_dueno").exists())

        # Confirmar que habilitar primer Dueño está bloqueado
        from apps.core.primer_uso import habilitar
        self.assertIsNone(habilitar())


if __name__ == "__main__":
    unittest.main()
