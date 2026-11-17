"""Contraste y reglas estructurales de las plantillas locales."""
from pathlib import Path
import re

from django.test import SimpleTestCase


RAIZ = Path(__file__).resolve().parents[4]
PLANTILLAS = RAIZ / 'frontend/templates'


def contraste_con_blanco(hexadecimal):
    canales = [int(hexadecimal[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lineales = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in canales]
    luminancia = sum(c * peso for c, peso in zip(lineales, (.2126, .7152, .0722)))
    return 1.05 / (luminancia + .05)


class FrontendEstaticoTests(SimpleTestCase):
    def test_contraste_indicadores(self):
        css = (RAIZ / 'frontend/static/css/app.css').read_text(encoding='utf-8')
        for selector in ('.tarjeta-indicador', '.indicador-caja', '.indicador-alerta',
                         '.indicador-alerta.alerta-2', '.indicador-alerta.alerta-3'):
            regla = re.search(re.escape(selector) + r'\s*\{[^}]+\}', css)
            self.assertIsNotNone(regla, selector)
            pares = re.search(r'linear-gradient\(130deg,\s*(#[0-9a-f]{6}),\s*(#[0-9a-f]{6})\)', regla.group())
            self.assertIsNotNone(pares, selector)
            for color in pares.groups():
                self.assertGreaterEqual(contraste_con_blanco(color), 4.5, (selector, color))

    def test_tablas_estilos_y_simbolos(self):
        for ruta in PLANTILLAS.rglob('*.html'):
            texto = ruta.read_text(encoding='utf-8')
            with self.subTest(ruta=ruta.relative_to(PLANTILLAS)):
                self.assertNotIn('style="', texto)
                self.assertIsNone(re.search(r'[🔍⚠●✓✕←☰]|[\U0001F300-\U0001FAFF]', texto))
                for tabla in re.finditer(r'<table\b[^>]*>', texto, re.I):
                    self.assertRegex(texto[tabla.end():], r'^\s*<caption\b')

    def test_formularios_delicados_piden_confirmacion(self):
        for nombre in ('catalogo/producto_detalle.html', 'core/qr.html', 'caja/estado.html'):
            texto = (PLANTILLAS / nombre).read_text(encoding='utf-8')
            self.assertRegex(texto, r'<form\b[^>]*data-confirmar\b[^>]*>')
            for atributo in ('titulo', 'mensaje', 'boton', 'variante'):
                self.assertIn(f'data-confirmar-{atributo}=', texto)
