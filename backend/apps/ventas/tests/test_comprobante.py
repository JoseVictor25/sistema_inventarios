from pathlib import Path
from io import BytesIO
import re
import tempfile
from unittest.mock import patch
from PIL import Image
from django.test import TestCase, override_settings
from django.core.management import call_command
from apps.reportes.tests.datos import crear_datos
from apps.ventas.models import Venta, Pago, DetalleVenta
from apps.inventario.models import Lote
from apps.ventas.impresion import leer


class ComprobanteTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = override_settings(DATA_DIR=Path(self.temp.name))
        self.config.enable(); self.addCleanup(self.config.disable)
        self.d = crear_datos()
        self.venta = self.d['venta']

    def test_efectivo_qr_mixto_e_historico(self):
        self.client.force_login(self.d['dueno'])
        self.d['presentacion'].precio_venta = 99
        self.d['presentacion'].save(update_fields=['precio_venta'])
        antes = (Venta.objects.count(), Pago.objects.count(), list(Lote.objects.values_list('pk', 'cantidad_actual')))
        for venta in (self.d['venta'], self.d['venta2']):
            for _ in range(2):
                r = self.client.get(f'/ventas/{venta.pk}/comprobante/')
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, 'DOCUMENTO NO FISCAL')
                self.assertContains(r, '80mm')
                self.assertContains(r, 'window.print()')
        r = self.client.get(f'/ventas/{self.venta.pk}/comprobante/')
        self.assertContains(r, 'Efectivo: Bs 20,00')
        self.assertContains(r, 'QR: Bs 10,00')
        self.assertContains(r, '15,00')
        self.assertNotContains(r, '99,00')
        self.assertEqual(antes, (Venta.objects.count(), Pago.objects.count(), list(Lote.objects.values_list('pk', 'cantidad_actual'))))

    def test_configuracion_y_permisos(self):
        self.assertEqual(leer()['ancho'], 80)
        self.assertEqual(leer()['margen_superior_mm'], 2)
        self.assertEqual(leer()['margen_inferior_mm'], 5)
        self.assertFalse(leer()['ofrecer_al_finalizar'])
        self.client.force_login(self.d['vendedor'])
        self.assertEqual(self.client.get('/ventas/impresion/').status_code, 403)
        self.assertEqual(self.client.get(f'/ventas/{self.venta.pk}/comprobante/').status_code, 200)
        self.client.force_login(self.d['dueno'])
        r = self.client.post('/ventas/impresion/', {'ancho': '58', 'vista_previa': 'on',
            'impresion_manual': 'on', 'mensaje': 'Gracias'}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertContains(self.client.get(f'/ventas/{self.venta.pk}/comprobante/'), '58mm')
        self.assertEqual(leer()['ancho'], 58)
        self.assertEqual(self.client.post('/ventas/impresion/', {'ancho': '90'}).status_code, 422)

    def test_anonimo_inactivo_inexistente_y_enlaces(self):
        self.assertEqual(self.client.get(f'/ventas/{self.venta.pk}/comprobante/').status_code, 302)
        self.client.force_login(self.d['dueno'])
        self.assertEqual(self.client.get('/ventas/999999/comprobante/').status_code, 404)
        self.assertContains(self.client.get(f'/ventas/{self.venta.pk}/'), 'Ver / Imprimir comprobante')
        self.assertContains(self.client.get('/ventas/'), 'Comprobante')
        self.d['dueno'].is_active = False; self.d['dueno'].save()
        self.assertNotEqual(self.client.get(f'/ventas/{self.venta.pk}/comprobante/').status_code, 200)

    def test_nombre_largo_escapado_y_csrf_configuracion(self):
        from django.test import Client
        producto = self.d['producto']
        producto.nombre = '<script>alert(1)</script>' + ' Nombre extenso' * 20
        producto.save(update_fields=['nombre'])
        self.client.force_login(self.d['dueno'])
        r = self.client.get(f'/ventas/{self.venta.pk}/comprobante/')
        self.assertNotContains(r, '<script>alert(1)</script>', html=False)
        self.assertContains(r, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertContains(r, 'imagen-ticket')
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.d['dueno'])
        self.assertEqual(cliente.post('/ventas/impresion/', {'ancho': '58'}).status_code, 403)

    def test_longitudes_1_5_15_y_margen_configurable(self):
        self.client.force_login(self.d['dueno'])
        modelo = self.venta.detalles.first()
        alturas = []
        for cantidad in (1, 5, 10, 15, 30):
            self.venta.detalles.exclude(pk=modelo.pk).delete()
            while self.venta.detalles.count() < cantidad:
                DetalleVenta.objects.create(venta=self.venta, presentacion=modelo.presentacion,
                    cantidad_presentaciones=1, unidades_totales=3,
                    precio_aplicado=modelo.precio_aplicado, subtotal=modelo.precio_aplicado)
            respuesta = self.client.get(f'/ventas/{self.venta.pk}/comprobante/')
            self.assertEqual(respuesta.content.decode().count('× Bs'), cantidad)
            imagen = self.client.get(f'/ventas/{self.venta.pk}/comprobante/imagen/')
            with Image.open(BytesIO(imagen.content)) as foto:
                self.assertEqual(foto.width, 576)
                alturas.append(foto.height)
            pdf = self.client.get(f'/ventas/{self.venta.pk}/comprobante/pdf/')
            self.assertEqual(pdf.status_code, 200)
            self.assertTrue(pdf.content.startswith(b'%PDF'))
            self.assertEqual(len(re.findall(rb'/Type\s*/Page\b', pdf.content)), 1)
            self.assertContains(respuesta, 'window.print()')
        self.assertEqual(alturas, sorted(alturas))
        self.assertEqual(len(set(alturas)), len(alturas))
        self.client.post('/ventas/impresion/', {'ancho': '58', 'margen_superior_mm': '3', 'margen_inferior_mm': '7',
            'vista_previa': 'on', 'impresion_manual': 'on'})
        respuesta = self.client.get(f'/ventas/{self.venta.pk}/comprobante/')
        imagen = self.client.get(f'/ventas/{self.venta.pk}/comprobante/imagen/')
        with Image.open(BytesIO(imagen.content)) as foto:
            self.assertEqual(foto.width, 384)
        pdf_58 = self.client.get(f'/ventas/{self.venta.pk}/comprobante/pdf/')
        self.assertEqual(pdf_58.status_code, 200)
        self.assertEqual(len(re.findall(rb'/Type\s*/Page\b', pdf_58.content)), 1)
        self.assertContains(respuesta, 'const ancho = 58')
        self.assertContains(respuesta, 'imagen.naturalHeight')
        for margen in ('-1', '0', '11', 'x'):
            self.assertEqual(self.client.post('/ventas/impresion/',
                {'ancho': '80', 'margen_superior_mm': margen}).status_code, 422)
        self.assertEqual(leer()['margen_superior_mm'], 3)

    def test_configuracion_anterior_sin_margen_superior(self):
        from apps.ventas.impresion import ruta
        ruta().write_text('{"ancho": 80, "margen_inferior_mm": 4}', encoding='utf-8')
        self.assertEqual(leer()['margen_superior_mm'], 2)
        self.assertEqual(leer()['margen_inferior_mm'], 4)

    def test_nombre_largo_margenes_y_raster_continuo(self):
        from apps.ventas.ticket import desde_venta, renderizar
        from apps.ventas.escpos import bytes_raster
        producto = self.d['producto']
        producto.nombre = 'Descripción muy larga con ñ y acentos ' * 15
        producto.save(update_fields=['nombre'])
        ticket = desde_venta(self.venta, 'Gracias por su compra')
        imagen, meta = renderizar(ticket, leer())
        self.assertGreater(imagen.height, 500)
        self.assertEqual(meta['margen_superior_px'], 14)
        self.assertEqual(meta['margen_inferior_px'], 36)
        self.assertEqual(imagen.crop((0, 0, imagen.width, meta['margen_superior_px'])).getextrema(),
                         ((255, 255), (255, 255), (255, 255)))
        self.assertEqual(imagen.crop((0, meta['ultimo_texto_px'], imagen.width, imagen.height)).getextrema(),
                         ((255, 255), (255, 255), (255, 255)))
        raster = bytes_raster(imagen)
        self.assertGreater(raster.count(b'\x1d\x76\x30\x00'), 1)
        self.assertFalse(raster.endswith(b'\x1d\x56\x01'))

    def test_escpos_cola_simulada_y_fallo_sin_nueva_venta(self):
        from apps.ventas.escpos import bytes_raster
        self.client.force_login(self.d['dueno'])
        ruta = f'/ventas/{self.venta.pk}/comprobante/imprimir-escpos/'
        self.assertEqual(self.client.post(ruta).status_code, 403)
        with patch('apps.ventas.escpos.listar_colas', return_value=['DT-230 simulada']):
            self.assertEqual(self.client.post('/ventas/impresion/', {'ancho': '80',
                'metodo': 'ESC/POS', 'impresora': 'DT-230 simulada',
                'escpos_confirmado': 'on', 'margen_superior_mm': '2',
                'margen_inferior_mm': '5'}).status_code, 302)
            antes = (Venta.objects.count(), Pago.objects.count(), list(Lote.objects.values_list('pk', 'cantidad_actual')))
            with patch('apps.ventas.escpos.enviar_cola', return_value=42) as cola:
                self.assertContains(self.client.post(ruta), 'Trabajo 42 aceptado')
                datos = cola.call_args.args[1]
                self.assertIn(b'\x1d\x76\x30\x00', datos)
                self.assertFalse(datos.endswith(b'\x1d\x56\x01'))
            with patch('apps.ventas.escpos.enviar_cola', side_effect=OSError('sin papel')):
                self.assertEqual(self.client.post(ruta).status_code, 503)
            self.assertEqual(antes, (Venta.objects.count(), Pago.objects.count(), list(Lote.objects.values_list('pk', 'cantidad_actual'))))
