from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import SimpleTestCase


class PaginacionFrontendTests(SimpleTestCase):
    def test_primera_intermedia_y_ultima(self):
        paginas = Paginator(range(50), 20)
        for numero in (1, 2, 3):
            html = render_to_string('components/_paginacion.html', {'page_obj': paginas.page(numero)})
            self.assertNotIn('?&amp;page=', html)
            self.assertIn(f'Página {numero} de 3', html)
            self.assertIn('aria-current="page"', html)
            if numero == 1:
                self.assertIn('aria-disabled="true">Anterior', html)
            if numero == 3:
                self.assertIn('aria-disabled="true">Siguiente', html)
        filtrada = render_to_string('components/_paginacion.html', {
            'page_obj': paginas.page(2), 'filtros_query': 'desde=2026-11-01'})
        self.assertIn('?desde=2026-11-01&amp;page=3', filtrada)
