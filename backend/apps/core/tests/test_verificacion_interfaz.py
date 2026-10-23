"""Regresiones del verificador aislado, sin GUI ni datos del negocio."""
import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase


RUTA = Path(__file__).resolve().parents[4] / "scripts" / "verificar_interfaz_fase0.py"
# tests/ -> core/ -> apps/ -> backend/ -> raíz
SPEC = importlib.util.spec_from_file_location("verificacion_fase0", RUTA)
verificacion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verificacion)


class VerificacionInterfazTests(SimpleTestCase):
    def datos(self):
        return {"documento": "nuevo", "ancho": 376, "ruta": "/login/", "listo": "complete", "errores": [], "bloqueos": [],
                "desbordamiento": False, "bootstrap": "object", "adminlte": "object",
                "htmx": "object", "chart": "function", "tomselect": "function",
                "css": [{"url": "http://127.0.0.1:8000/static/app.css", "reglas": 2}],
                "scripts": ["http://127.0.0.1:8000/static/app.js"]}

    def test_pagina_completa(self):
        self.assertEqual(verificacion.validar_pagina(self.datos(), "/login/",
                         ["/static/app.css", "/static/app.js"]), [])

    def test_evidencia_ausente_no_aprueba(self):
        self.assertTrue(verificacion.validar_pagina({}, "/login/", ["/static/app.css"]))

    def test_carga_incorrecta_no_aprueba(self):
        for campo, valor in (("errores", ["fallo JS"]), ("bloqueos", ["externo"]),
                             ("chart", "undefined"), ("desbordamiento", True),
                             ("ruta", "/otra/"), ("css", [])):
            with self.subTest(campo=campo):
                datos = self.datos()
                datos[campo] = valor
                self.assertTrue(verificacion.validar_pagina(datos, "/login/", ["/static/app.css"]))

    def test_origen_incluye_puerto(self):
        origen = "http://127.0.0.1:8000"
        self.assertFalse(verificacion.es_externa(origen + "/static/app.js", origen))
        self.assertFalse(verificacion.es_externa("data:image/svg+xml;base64,AAAA", origen))
        self.assertTrue(verificacion.es_externa("http://127.0.0.1:9000/app.js", origen))
        self.assertTrue(verificacion.es_externa("https://example.com/app.js", origen))

    def test_no_usa_objetos_nativos(self):
        import ast
        arbol = ast.parse(RUTA.read_text(encoding="utf-8"))
        atributos = {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
        self.assertFalse(atributos & {"native", "CoreWebView2", "Invoke", "CapturePreviewAsync"})

    def test_no_migra_base_fuera_del_directorio_temporal(self):
        with patch("django.conf.settings.DATABASES", {"default": {
            "ENGINE": "django.db.backends.sqlite3", "NAME": "base_ajena.sqlite3"
        }}), patch("django.core.management.call_command") as comando:
            with self.assertRaisesRegex(RuntimeError, "Se rechazó migrar"):
                verificacion.preparar_base_temporal("carpeta_temporal_de_prueba")
            comando.assert_not_called()

    def test_no_acepta_dimension_incorrecta(self):
        datos = self.datos()
        datos["ancho"] = 1536
        self.assertTrue(verificacion.validar_pagina(datos, "/login/", [], 390))

    def test_espera_documento_nuevo_y_bibliotecas(self):
        ventana = Mock()
        ventana.events.loaded.wait.return_value = True
        anterior = self.datos() | {"documento": "anterior"}
        incompleto = self.datos() | {"chart": "undefined"}
        ventana.evaluate_js.side_effect = [json.dumps(d) for d in (anterior, incompleto, self.datos())]
        resultado = verificacion.esperar_documento(
            ventana, "/login/", "anterior", ["/static/app.css"], 390, 2, threading.Event())
        self.assertEqual(resultado["documento"], "nuevo")
        self.assertEqual(ventana.evaluate_js.call_count, 3)

    def test_cancelacion_no_aprueba(self):
        cancelado = threading.Event()
        cancelado.set()
        with self.assertRaises(RuntimeError):
            verificacion.esperar_documento(Mock(), "/login/", None, [], 390, 1, cancelado)

    def test_servidor_http_comparte_base_temporal_migrada(self):
        raiz = RUTA.parent.parent
        protegidos = [raiz / "backend/.env", raiz / "backend/datos/db.sqlite3"]
        antes = {p: hashlib.sha256(p.read_bytes()).digest() for p in protegidos if p.exists()}
        with tempfile.TemporaryDirectory(prefix="test_fase0_http_") as salida:
            proceso = subprocess.run([sys.executable, str(RUTA), "--solo-http", "--salida", salida],
                                     cwd=raiz, capture_output=True, text=True, timeout=90)
            self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
            datos = json.loads((Path(salida) / "resultado.json").read_text(encoding="utf-8"))
            self.assertTrue(datos["base_temporal"]["tabla_verificada"])
            self.assertEqual(datos["base_temporal"]["tabla_usuario"], "usuarios_usuario")
            self.assertTrue(datos["solo_http_aprobado"])
            self.assertTrue(datos["autenticacion_http"]["conexion_anticipada"])
            self.assertFalse(datos["automatizacion_aprobada"])
            for accion in ("login", "inicio", "logout"):
                self.assertTrue(datos["autenticacion_http"][accion])
            self.assertEqual(len(datos["autenticacion_http"]["recursos_verificados"]), 10)
            self.assertTrue(all(r["estado"] < 400 for r in datos["http_local"]))
        for ruta, valor in antes.items():
            self.assertEqual(hashlib.sha256(ruta.read_bytes()).digest(), valor)
