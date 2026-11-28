from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase


class MenuActivoTests(SimpleTestCase):
    def test_una_sola_entrada_activa(self):
        casos = ('ventas:lista', 'ventas:detalle', 'ventas:comprobante',
                 'ventas:pos', 'ventas:configurar_impresion', 'core:qr_configurar')
        for nombre in casos:
            with self.subTest(nombre=nombre):
                app, url = nombre.split(':')
                solicitud = SimpleNamespace(resolver_match=SimpleNamespace(
                    view_name=nombre, app_name=app, url_name=url))
                html = render_to_string('components/_menu.html', {
                    'request': solicitud, 'user': SimpleNamespace(get_username='prueba'),
                    'permisos': ['vender', 'gestionar_usuarios'],
                    'NOMBRE_NEGOCIO': 'Pruebas',
                })
                self.assertEqual(html.count('active fw-bold'), 1)
