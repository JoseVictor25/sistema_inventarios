from django.test import TestCase
from django.test import SimpleTestCase, Client
from django.core.management import call_command
from django.core.exceptions import PermissionDenied
from apps.core import primer_uso as p
from apps.usuarios.models import Usuario


class PrimerUsoTests(TestCase):
    def setUp(self):
        call_command('cargar_datos_iniciales', verbosity=0)
        self.token = p.habilitar()

    def tearDown(self):
        p._token = None

    def datos(self):
        return dict(autorizacion=self.token, username='dueno_temporal', password1='Clave-Segura-Ficticia-2026!', password2='Clave-Segura-Ficticia-2026!')

    def test_alta_unica_sin_privilegios(self):
        usuario = p.crear_dueno(self.datos())
        self.assertEqual(usuario.rol.nombre, 'Dueño')
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.is_superuser)
        with self.assertRaises(PermissionDenied):
            p.crear_dueno(self.datos())
        self.assertEqual(Usuario.objects.count(), 1)

    def test_codigo_invalido_no_crea(self):
        datos = self.datos()
        datos['autorizacion'] = 'incorrecto'
        with self.assertRaises(PermissionDenied):
            p.crear_dueno(datos)
        self.assertFalse(Usuario.objects.exists())

    def test_formulario_contrasenas(self):
        datos = self.datos()
        datos.update(password1='123', password2='123')
        self.assertFalse(p.PrimerDuenoForm(datos).is_valid())

    def test_ruta_y_bloqueo_posterior(self):
        self.assertEqual(self.client.get('/configuracion-inicial/').status_code, 200)
        contenido = self.client.get('/configuracion-inicial/').content.decode()
        for etiqueta in ('Código local de un solo uso (aparece en la ventana negra)', 'Usuario', 'Contraseña', 'Repetir contraseña'):
            self.assertIn(etiqueta, contenido)
        for etiqueta_interna in ('Autorizacion', 'Username', 'Password1', 'Password2'):
            self.assertNotIn(etiqueta_interna, contenido)
        self.assertEqual(self.client.post('/configuracion-inicial/', self.datos()).status_code, 302)
        self.assertEqual(self.client.get('/configuracion-inicial/').status_code, 403)

    def test_csrf_y_validacion_en_servicio(self):
        from django.core.exceptions import ValidationError
        self.assertEqual(Client(enforce_csrf_checks=True).post('/configuracion-inicial/', self.datos()).status_code, 403)
        datos = self.datos()
        datos.update(password1='123', password2='123')
        with self.assertRaises(ValidationError):
            p.crear_dueno(datos)
        self.assertFalse(Usuario.objects.exists())


class RutasDesktopTests(SimpleTestCase):
    def test_mensaje_cuenta_no_autorizada_no_expone_detalle(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
        from desktop.launcher import _mensaje_inicio, MENSAJE_CUENTA_NO_AUTORIZADA
        self.assertEqual(_mensaje_inicio(PermissionError("[Errno 13] C:\\ProgramData\\SistemaInventarios\\.instancia.lock")),
                         MENSAJE_CUENTA_NO_AUTORIZADA)
        self.assertNotIn('Errno', _mensaje_inicio(PermissionError('detalle')))
    def test_rechaza_rutas_no_temporales(self):
        from pathlib import Path
        import sys
        import tempfile
        raiz = Path(__file__).resolve().parents[4]
        sys.path.insert(0, str(raiz))
        from desktop.rutas import validar_temporal
        for ruta in ('relativa', str(raiz / 'datos'), tempfile.gettempdir(), 'C:/ProgramData/SistemaInventarios'):
            with self.subTest(ruta=ruta), self.assertRaises(ValueError):
                validar_temporal(ruta)
