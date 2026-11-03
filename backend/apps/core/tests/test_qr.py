from io import BytesIO
from pathlib import Path
import tempfile
import subprocess
import sys
from PIL import Image
from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.core.management import call_command
from apps.usuarios.models import Usuario, Rol
from apps.core.qr import normalizar, ruta_qr
from unittest.mock import patch
from django.http import HttpResponse
from apps.ventas.models import MetodoPago, Venta


class QRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('cargar_datos_iniciales', verbosity=0)
        cls.dueno = Usuario.objects.create_user('qr_dueno', rol=Rol.objects.get(nombre='Dueño'))
        cls.vendedor = Usuario.objects.create_user('qr_vendedor', rol=Rol.objects.get(nombre='Vendedor'))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.override = override_settings(DATA_DIR=Path(self.tmp.name))
        self.override.enable()
        self.addCleanup(self.override.disable)

    def archivo(self, formato='PNG'):
        b = BytesIO(); Image.new('RGB', (256, 256), 'white').save(b, formato)
        return SimpleUploadedFile('qr.' + {'JPEG':'jpg'}.get(formato, formato.lower()), b.getvalue())

    def test_formatos(self):
        for f in ['PNG', 'JPEG', 'WEBP']:
            self.assertTrue(normalizar(self.archivo(f)).startswith(b'\x89PNG'))

    def test_invalidos(self):
        for f in [SimpleUploadedFile('x.png', b'no imagen'), SimpleUploadedFile('x.svg', b'<svg/>'), SimpleUploadedFile('x.png', b'x'*(5*1024*1024+1))]:
            with self.assertRaises(ValidationError): normalizar(f)
        b = BytesIO(); Image.new('RGB', (10, 10)).save(b, 'PNG')
        with self.assertRaises(ValidationError): normalizar(SimpleUploadedFile('x.png', b.getvalue()))

    def test_cargar_reemplazar_persistir_eliminar(self):
        self.client.force_login(self.dueno)
        for _ in range(2):
            self.assertEqual(self.client.post('/sistema/qr/', {'accion':'guardar', 'imagen':self.archivo()}).status_code, 302)
        self.assertTrue(ruta_qr().is_file())
        subprocess.run([sys.executable, '-c',
                        'from PIL import Image; import sys; Image.open(sys.argv[1]).verify()',
                        str(ruta_qr())], check=True)
        self.client.logout(); self.client.force_login(self.vendedor)
        self.assertEqual(self.client.get('/sistema/qr/imagen/').status_code, 200)
        self.client.force_login(self.dueno)
        self.assertEqual(self.client.post('/sistema/qr/', {'accion':'eliminar'}).status_code, 302)
        self.assertEqual(self.client.get('/sistema/qr/imagen/').status_code, 404)

    def test_permisos(self):
        self.client.force_login(self.vendedor)
        self.assertEqual(self.client.post('/sistema/qr/', {'accion':'guardar','imagen':self.archivo()}).status_code,403)
        self.vendedor.is_active=False; self.vendedor.save()
        self.assertNotEqual(self.client.get('/sistema/qr/imagen/').status_code,200)

    def test_pos_modal_y_confirmacion(self):
        self.client.force_login(self.vendedor)
        respuesta=self.client.get('/ventas/nueva/')
        self.assertContains(respuesta,'id="modal-qr"')
        self.assertContains(respuesta,'qr_confirmado')
        self.assertContains(respuesta,'Total de la venta: Bs')
        self.assertEqual(Venta.objects.count(), 0)

    def test_confirmacion_manual_backend(self):
        self.client.force_login(self.vendedor)
        datos={'metodo_id':MetodoPago.objects.get(nombre='QR').pk, 'monto':'1'}
        with patch('apps.ventas.views.registrar_venta') as registrar:
            respuesta=self.client.post('/ventas/confirmar/',datos)
            self.assertEqual(respuesta.status_code,422)
            registrar.assert_not_called()
            datos['qr_confirmado']='si'
            with patch('apps.ventas.views.render',return_value=HttpResponse('ok')):
                self.assertEqual(self.client.post('/ventas/confirmar/',datos).status_code,200)
            registrar.assert_called_once()

    def test_csrf(self):
        from django.test import Client
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.dueno)
        self.assertEqual(cliente.post('/sistema/qr/', {'accion':'eliminar'}).status_code,403)
