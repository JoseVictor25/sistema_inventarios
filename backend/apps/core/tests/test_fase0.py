"""Pruebas sin acceso a la base de datos existente."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.core.exceptions import ErrorDeNegocio
from apps.core.permissions import permiso_requerido
from apps.core.validators import validar_cantidad, validar_dinero
from config.settings import base


class ConfiguracionTests(SimpleTestCase):
    def test_secreto_ausente_vacio_o_espacios(self):
        for entorno in ({}, {"PRUEBA": ""}, {"PRUEBA": "  "}):
            with self.subTest(entorno=entorno), patch.dict(base.os.environ, entorno, clear=True):
                with self.assertRaisesRegex(RuntimeError, "PRUEBA"):
                    base.env_str("PRUEBA")

    def test_booleanos(self):
        for entrada, esperado in (("sí", True), ("TRUE", True), ("1", True), ("no", False), ("false", False), ("0", False)):
            with self.subTest(entrada=entrada), patch.dict(base.os.environ, {"PRUEBA": entrada}):
                self.assertIs(base.env_bool("PRUEBA"), esperado)

    def test_booleano_invalido(self):
        with patch.dict(base.os.environ, {"PRUEBA": "tal vez"}):
            with self.assertRaises(RuntimeError):
                base.env_bool("PRUEBA")

    def test_enteros_y_limites(self):
        for entrada in ("abc", "1.5", "", "-1", "0"):
            with self.subTest(entrada=entrada), patch.dict(base.os.environ, {"PRUEBA": entrada}):
                with self.assertRaises(RuntimeError) as error:
                    base.env_int("PRUEBA", 30, minimo=1)
                self.assertIn(str(base.ENV_FILE), str(error.exception))
        with patch.dict(base.os.environ, {"PRUEBA": "30"}):
            self.assertEqual(base.env_int("PRUEBA", 30, minimo=1), 30)

    def test_error_no_revela_valor(self):
        with patch.dict(base.os.environ, {"PRUEBA": "valor-confidencial"}):
            with self.assertRaises(RuntimeError) as error:
                base.env_int("PRUEBA", 1)
            self.assertNotIn("valor-confidencial", str(error.exception))


class ValidadoresTests(SimpleTestCase):
    def test_dinero_valido(self):
        for valor in ("0", "0.01", "12.30", "12.300"):
            validar_dinero(Decimal(valor))

    def test_dinero_invalido(self):
        for valor in (None, True, 1.2, "12.00", Decimal("-1"), Decimal("0.001"), Decimal("NaN"), Decimal("Infinity"), Decimal("1e100")):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                validar_dinero(valor)

    def test_cantidad_valida(self):
        validar_cantidad(1)
        validar_cantidad(24)

    def test_cantidad_invalida(self):
        for valor in (None, True, False, 0, -1, 1.0, "2"):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                validar_cantidad(valor)

    def test_error_de_negocio(self):
        error = ErrorDeNegocio("Revisa la cantidad.", "cantidad")
        self.assertEqual(str(error), error.mensaje)
        self.assertEqual(error.campo, "cantidad")


class PermisosTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/protegido/")
        self.vista = permiso_requerido("respaldar")(lambda request: HttpResponse("OK"))

    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_anonimo_redirige_login(self):
        self.request.user = AnonymousUser()
        self.assertEqual(self.vista(self.request).status_code, 302)

    def test_superusuario_activo(self):
        self.request.user = SimpleNamespace(is_authenticated=True, is_active=True, is_superuser=True)
        self.assertEqual(self.vista(self.request).status_code, 200)

    def test_denegacion_por_defecto(self):
        for activo, superusuario in ((True, False), (False, True)):
            self.request.user = SimpleNamespace(is_authenticated=True, is_active=activo, is_superuser=superusuario)
            with self.assertRaises(PermissionDenied):
                self.vista(self.request)


@override_settings(ALLOWED_HOSTS=["testserver"])
class InterfazTests(SimpleTestCase):
    def test_recursos_locales_servidos_por_django(self):
        from apps.core.frontend import RECURSOS_FRONTEND
        from django.conf import settings
        for ruta in (*RECURSOS_FRONTEND, "css/app.css", "js/app.js"):
            with self.subTest(ruta=ruta):
                respuesta = self.client.get("/static/" + ruta)
                self.assertEqual(respuesta.status_code, 200)
                contenido = b"".join(respuesta.streaming_content) if respuesta.streaming else respuesta.content
                self.assertEqual(contenido, (settings.FRONTEND_DIR / "static" / ruta).read_bytes())
                tipo = respuesta["Content-Type"]
                self.assertIn("css" if ruta.endswith(".css") else "javascript", tipo)

    def test_login_sin_recursos_remotos(self):
        respuesta = self.client.get("/login/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'id="mensajes"')
        self.assertContains(respuesta, 'hx-headers=')
        self.assertNotContains(respuesta, "{#")
        self.assertNotContains(respuesta, "https://")
        self.assertNotContains(respuesta, "http://")

    def test_inicio_exige_sesion(self):
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_logout_solo_post(self):
        self.assertEqual(self.client.get("/logout/").status_code, 405)

    def test_enlaces_vendor_solo_locales(self):
        html = render_to_string("base.html", {"recursos_frontend_listos": True})
        self.assertIn("vendor/adminlte/css/adminlte.min.css", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)


@override_settings(ALLOWED_HOSTS=["testserver"])
class AutenticacionTests(TestCase):
    """Usuarios y sesiones exclusivos de la base temporal del runner de Django."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        cls.usuario = get_user_model().objects.create_user(
            username="prueba_fase0", password="Clave-solo-pruebas-982!"
        )

    def test_acceso_inicio_y_salida_con_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.get("/login/")
        respuesta = cliente.post("/login/", {
            "username": "prueba_fase0", "password": "Clave-solo-pruebas-982!",
            "csrfmiddlewaretoken": cliente.cookies["csrftoken"].value,
        })
        self.assertRedirects(respuesta, "/")
        self.assertContains(cliente.get("/"), "prueba_fase0")
        respuesta = cliente.post("/logout/", {
            "csrfmiddlewaretoken": cliente.cookies["csrftoken"].value,
        })
        self.assertRedirects(respuesta, "/login/")
        self.assertEqual(cliente.get("/").status_code, 302)

    def test_clave_incorrecta_no_autentica(self):
        respuesta = self.client.post("/login/", {"username": "prueba_fase0", "password": "incorrecta"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_post_sin_csrf_rechazado(self):
        cliente = Client(enforce_csrf_checks=True)
        respuesta = cliente.post("/login/", {"username": "prueba_fase0", "password": "Clave-solo-pruebas-982!"})
        self.assertEqual(respuesta.status_code, 403)
