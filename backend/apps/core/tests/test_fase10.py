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


class LauncherPermisoBloqueoTests(SimpleTestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        import sys
        raiz = Path(__file__).resolve().parents[4]
        if str(raiz) not in sys.path:
            sys.path.insert(0, str(raiz))
        self.temp = tempfile.TemporaryDirectory(prefix='launcher_permiso_')
        self.addCleanup(self.temp.cleanup)
        self.ruta = Path(self.temp.name)

    def _ejecutar_launcher(self, error):
        from argparse import Namespace
        from contextlib import contextmanager
        from io import StringIO
        from unittest.mock import patch
        import sys
        from desktop import launcher

        args = Namespace(datos_temporales=str(self.ruta), datos_instalados=None,
            instalado=False, inicializar=False, respaldo=False, restaurar=None,
            navegador=True, puerto=8000, diagnostico=False, operador_sid=None)

        @contextmanager
        def bloqueo(_ruta):
            raise error
            yield

        salida = StringIO()
        errores = StringIO()
        with patch('argparse.ArgumentParser.parse_args', return_value=args), \
             patch('desktop.rutas.validar_temporal', return_value=self.ruta), \
             patch('desktop.rutas.recursos', return_value=self.ruta), \
             patch('desktop.bloqueo_instancia.bloqueo_instancia', bloqueo), \
             patch.object(sys, 'stdout', salida), patch.object(sys, 'stderr', errores):
            resultado = launcher.main()
        return resultado, salida.getvalue(), errores.getvalue()

    def test_permissionerror_lock_muestra_mensaje_registra_traceback_y_detiene_inicio(self):
        import logging
        from unittest.mock import patch
        from desktop.bloqueo_instancia import ErrorPermisoBloqueo
        from desktop.launcher import MENSAJE_CUENTA_NO_AUTORIZADA

        error = ErrorPermisoBloqueo(13, 'Permission denied', str(self.ruta / '.instancia.lock'))
        with patch.object(logging.getLogger('desktop.launcher'), 'exception') as log_general:
            resultado, salida, errores = self._ejecutar_launcher(error)
        self.assertEqual(resultado, 1)
        self.assertEqual(salida, '')
        self.assertEqual(errores.strip(), MENSAJE_CUENTA_NO_AUTORIZADA)
        log_general.assert_not_called()
        contenido = (self.ruta / 'logs' / 'sistema.log').read_text(encoding='utf-8')
        self.assertIn('ErrorPermisoBloqueo', contenido)
        self.assertIn('Traceback (most recent call last)', contenido)
        self.assertNotIn('Fallo técnico durante el arranque', errores)

    def test_error_inesperado_conserva_manejo_tecnico(self):
        from unittest.mock import patch
        from desktop.launcher import MENSAJE_CUENTA_NO_AUTORIZADA
        error = RuntimeError('fallo inesperado de prueba')
        with patch('logging.Logger.exception') as log_exception:
            resultado, _salida, errores = self._ejecutar_launcher(error)
        self.assertEqual(resultado, 1)
        self.assertIn('No se pudo iniciar el sistema: fallo inesperado de prueba', errores)
        self.assertNotIn(MENSAJE_CUENTA_NO_AUTORIZADA, errores)
        log_exception.assert_called_once()

    def test_cuenta_autorizada_conserva_el_flujo_normal_del_bloqueo(self):
        from argparse import Namespace
        from contextlib import contextmanager
        from unittest.mock import patch
        import sys
        from desktop import launcher
        args = Namespace(datos_temporales=str(self.ruta), datos_instalados=None,
            instalado=False, inicializar=False, respaldo=False, restaurar=None,
            navegador=True, puerto=8000, diagnostico=False, operador_sid=None)
        llamadas = []

        @contextmanager
        def bloqueo(_ruta):
            llamadas.append('adquirido')
            try:
                yield
            finally:
                llamadas.append('liberado')

        with patch('argparse.ArgumentParser.parse_args', return_value=args), \
             patch('desktop.rutas.validar_temporal', return_value=self.ruta), \
             patch('desktop.rutas.recursos', return_value=self.ruta), \
             patch('desktop.bloqueo_instancia.bloqueo_instancia', bloqueo), \
             patch('desktop.inicializacion.configurar', side_effect=RuntimeError('fin de prueba')):
            # El bloqueo se adquiere antes de configurar; se alcanza y libera en el flujo normal.
            resultado = launcher.main()
        self.assertEqual(resultado, 1)
        self.assertEqual(llamadas, ['adquirido', 'liberado'])
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
