from types import SimpleNamespace
from django.test import SimpleTestCase
from apps.auditoria.presentacion import preparar, filas


class PresentacionAuditoriaTests(SimpleTestCase):
    def test_precio_y_diferencias(self):
        evento = preparar(SimpleNamespace(accion='CAMBIO_PRECIO', valor_anterior={'precio_venta': '50'}, valor_nuevo={'precio_venta': '60'}))
        self.assertEqual(evento.accion_legible, 'Cambio de precio')
        self.assertTrue(evento.detalles[0]['cambio'])
        self.assertIn('50,00', evento.detalles[0]['anterior'])

    def test_anidados_nulos_y_secretos(self):
        resultado = dict(filas({'datos': {'password': 'secreto', 'valor': None}, 'lista': [True, '<script>']}))
        self.assertNotIn('secreto', str(resultado))
        self.assertIn('Sin valor', resultado.values())
        self.assertIn('<script>', resultado.values())  # La plantilla aplica escape HTML.
