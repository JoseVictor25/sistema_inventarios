from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase


class NavegacionLateralTests(SimpleTestCase):
    def menu(self, permisos):
        return render_to_string('components/_menu.html', {
            'permisos': permisos,
            'NOMBRE_NEGOCIO': 'Tienda con nombre completo <prueba>',
            'user': SimpleNamespace(get_username=lambda: 'operador'),
        })

    def test_panel_unico_y_nombre_escapado(self):
        html = self.menu(['vender'])
        self.assertEqual(html.count('id="nav-collapsible"'), 1)
        self.assertIn('offcanvas-lg offcanvas-start', html)
        self.assertIn('data-bs-toggle="offcanvas"', html)
        self.assertIn('Tienda con nombre completo &lt;prueba&gt;', html)
        self.assertNotIn('text-truncate', html)
        self.assertNotIn('dropdown-toggle', html)

    def test_modulos_administrativos_no_aparecen_sin_permiso(self):
        html = self.menu(['vender', 'ver_stock'])
        self.assertNotIn('>Usuarios</span>', html)
        self.assertNotIn('>Roles</span>', html)
        self.assertNotIn('>Respaldos</span>', html)
        self.assertIn('>Inventario</span>', html)

    def test_modulos_administrativos_con_permiso(self):
        html = self.menu(['gestionar_usuarios', 'respaldar'])
        self.assertIn('>Usuarios</span>', html)
        self.assertIn('>Roles</span>', html)
        self.assertIn('>Respaldos</span>', html)
