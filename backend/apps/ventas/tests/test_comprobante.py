from pathlib import Path
from io import BytesIO
import re
import tempfile
from uuid import uuid4
from unittest.mock import patch
from PIL import Image, ImageDraw
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
        self.assertContains(r, 'Configuración de impresión guardada correctamente.')
        self.assertNotContains(self.client.get('/ventas/impresion/'), 'Configuración de impresión guardada correctamente.')
        self.assertContains(self.client.get(f'/ventas/{self.venta.pk}/comprobante/'), '58mm')
        self.assertEqual(leer()['ancho'], 58)
        error = self.client.post('/ventas/impresion/', {'ancho': '90'})
        self.assertEqual(error.status_code, 422)
        self.assertNotContains(error, 'Configuración de impresión guardada correctamente.', status_code=422)

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
        self.assertContains(respuesta, '@page { size: 58mm ')
        self.assertNotContains(respuesta, 'pagina.textContent')
        for margen in ('-1', '0', '11', 'x'):
            self.assertEqual(self.client.post('/ventas/impresion/',
                {'ancho': '80', 'margen_superior_mm': margen}).status_code, 422)
        self.assertEqual(leer()['margen_superior_mm'], 3)

    def test_configuracion_anterior_sin_margen_superior(self):
        from apps.ventas.impresion import ruta
        ruta().write_text('{"ancho": 80, "margen_inferior_mm": 4}', encoding='utf-8')
        self.assertEqual(leer()['margen_superior_mm'], 2)
        self.assertEqual(leer()['margen_inferior_mm'], 4)
        self.assertEqual(leer()['columnas_80'], 48)
        self.assertEqual(leer()['columnas_58'], 32)

    def test_configuracion_anterior_ignora_alimentar_lineas(self):
        from apps.ventas.impresion import ruta
        ruta().write_text('{"ancho": 80, "alimentar_lineas": 2}', encoding='utf-8')
        self.assertEqual(leer()['ancho'], 80)
        self.assertNotIn('alimentar_lineas', leer())

    def test_columnas_configurables_y_rangos(self):
        from apps.ventas.ticket import formatear_par
        palabra = 'P' * 40
        filas = formatear_par(palabra, 'Bs 15.00', 48)
        self.assertTrue(filas[0][0])
        self.assertEqual(''.join(texto for texto, _ in filas), palabra)
        self.client.force_login(self.d['dueno'])
        datos = {'ancho': '80', 'columnas_80': '44', 'columnas_58': '30'}
        self.assertEqual(self.client.post('/ventas/impresion/', datos).status_code, 302)
        self.assertEqual((leer()['columnas_80'], leer()['columnas_58']), (44, 30))
        for clave, valor in (('columnas_80', '23'), ('columnas_80', '65'),
                             ('columnas_58', '15'), ('columnas_58', '49'),
                             ('margen_superior_mm', '0'),
                             ('margen_inferior_mm', '16'),
                             ('avance_final_mm', '-1'), ('avance_final_mm', '41')):
            self.assertEqual(self.client.post('/ventas/impresion/', {**datos, clave: valor}).status_code, 422)

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
            intento = {'intento_impresion': uuid4().hex}
            with patch('apps.ventas.escpos.enviar_cola', return_value=42) as cola:
                self.assertContains(self.client.post(ruta, intento), 'Trabajo 42 aceptado')
                self.assertEqual(self.client.post(ruta, intento).status_code, 409)
                cola.assert_called_once()
                datos = cola.call_args.args[1]
                self.assertIn(b'\x1d\x76\x30\x00', datos)
                self.assertTrue(datos.endswith(b'\n\x1bJ\xff\x1bJ\x01'))
                self.assertFalse(datos.endswith(b'\x1d\x56\x01'))
            intento_fallido = {'intento_impresion': uuid4().hex}
            with patch('apps.ventas.escpos.enviar_cola', side_effect=OSError('sin papel')):
                self.assertEqual(self.client.post(ruta, intento_fallido).status_code, 503)
            with patch('apps.ventas.escpos.enviar_cola', return_value=43) as reintento:
                self.assertEqual(self.client.post(ruta, intento_fallido).status_code, 200)
                self.assertEqual(self.client.post(ruta, intento_fallido).status_code, 409)
                reintento.assert_called_once()
            self.assertEqual(antes, (Venta.objects.count(), Pago.objects.count(), list(Lote.objects.values_list('pk', 'cantidad_actual'))))

    def test_escpos_un_trabajo_y_avance_para_1_5_20_productos(self):
        from apps.ventas.ticket import desde_venta, formatear_item, formatear_par, renderizar
        self.client.force_login(self.d['dueno'])
        ruta = f'/ventas/{self.venta.pk}/comprobante/imprimir-escpos/'
        modelo = self.venta.detalles.first()
        producto = modelo.presentacion.producto
        producto.nombre = 'Producto térmico de nombre especialmente largo para probar ajuste por palabras'
        producto.save(update_fields=['nombre'])
        with patch('apps.ventas.escpos.listar_colas', return_value=['Cola ESC/POS simulada']):
            respuesta = self.client.post('/ventas/impresion/', {
                'ancho': '80', 'metodo': 'ESC/POS', 'impresora': 'Cola ESC/POS simulada',
                'escpos_confirmado': 'on', 'margen_superior_mm': '2',
                'margen_inferior_mm': '5',
                'corte_automatico': 'on',
            })
            self.assertEqual(respuesta.status_code, 302)
            tamanos = []
            for cantidad in (1, 5, 20):
                self.venta.detalles.exclude(pk=modelo.pk).delete()
                for _ in range(cantidad - 1):
                    DetalleVenta.objects.create(venta=self.venta, presentacion=modelo.presentacion,
                        cantidad_presentaciones=1, unidades_totales=3,
                        precio_aplicado=modelo.precio_aplicado, subtotal=modelo.precio_aplicado)
                intento = {'intento_impresion': uuid4().hex}
                ticket = desde_venta(self.venta, 'Gracias por su compra')
                _, meta = renderizar(ticket, leer())
                self.assertEqual(len(meta['importes']), cantidad + 1 + len(ticket.pagos))
                self.assertLessEqual(max(x + ancho for _, x, ancho in meta['importes'])
                                     - min(x + ancho for _, x, ancho in meta['importes']), 1)
                for columnas in (48, 32):
                    item = formatear_item(ticket.lineas[0], columnas)
                    self.assertGreater(len(item), 2)
                    self.assertEqual(item[0][1], f'Bs {ticket.lineas[0].subtotal:.2f}')
                    self.assertLessEqual(len(item[0][0]) + 1 + len(item[0][1]), columnas)
                    self.assertTrue(all(importe is None for _, importe in item[1:]))
                    self.assertTrue(item[-1][0].startswith(f'  {ticket.lineas[0].cantidad} x '))
                    self.assertIn(' · ', item[-1][0])
                    self.assertEqual(formatear_par('TOTAL', 'Bs 15.00', columnas)[0], ('TOTAL', 'Bs 15.00'))
                    self.assertEqual(formatear_par('Efectivo', 'Bs 20.00', columnas)[0], ('Efectivo', 'Bs 20.00'))
                with patch('apps.ventas.escpos.enviar_cola', return_value=42) as cola:
                    self.assertEqual(self.client.post(ruta, intento).status_code, 200)
                    self.assertEqual(self.client.post(ruta, intento).status_code, 409)
                    cola.assert_called_once()
                    nombre, datos = cola.call_args.args
                self.assertEqual(nombre, 'Cola ESC/POS simulada')
                self.assertTrue(datos.startswith(b'\x1b@\x1d\x76\x30\x00'))
                self.assertTrue(datos.endswith(b'\n\x1bJ\x40\x1d\x56\x42\x00'))
                self.assertNotIn(b'\x1b\x64', datos[-11:])
                posicion = 2
                filas = []
                while datos[posicion:posicion + 4] == b'\x1d\x76\x30\x00':
                    ancho_bytes = int.from_bytes(datos[posicion + 4:posicion + 6], 'little')
                    alto = int.from_bytes(datos[posicion + 6:posicion + 8], 'little')
                    posicion += 8
                    for _ in range(alto):
                        filas.append(datos[posicion:posicion + ancho_bytes])
                        posicion += ancho_bytes
                self.assertEqual(datos[posicion:], b'\n\x1bJ\x40\x1d\x56\x42\x00')
                self.assertTrue(all(not any(fila) for fila in filas[:14]))
                self.assertTrue(any(filas[14]))
                self.assertTrue(any(filas[-1]))
                tamanos.append(len(datos))
            self.assertEqual(tamanos, sorted(tamanos))
            self.assertEqual(len(set(tamanos)), 3)

    def test_polaridad_raster_blanco_y_negro(self):
        from apps.ventas.escpos import bytes_raster
        imagen = Image.new('RGB', (576, 16), 'white')
        datos = bytes_raster(imagen, avance_final_mm=0)
        self.assertEqual(datos[:10], b'\x1b@\x1d\x76\x30\x00\x48\x00\x10\x00')
        self.assertEqual(datos[10:], b'\x00' * (72 * 16) + b'\n\x1bJ\x00')
        ImageDraw.Draw(imagen).rectangle((0, 0, 7, 7), fill='black')
        datos = bytes_raster(imagen, avance_final_mm=0)
        self.assertEqual([datos[10 + fila * 72] for fila in range(8)], [255] * 8)
        self.assertEqual(datos[10 + 8 * 72], 0)
        self.assertEqual(datos[11], 0)

    def test_avance_final_en_ambos_modos_y_calibracion(self):
        from apps.ventas.escpos import bytes_raster, imagen_calibracion
        from apps.ventas.impresion import avance_final
        self.assertEqual(avance_final({**leer(), 'corte_automatico': True}), 8)
        self.assertEqual(avance_final({**leer(), 'corte_automatico': False}), 32)
        imagen = Image.new('RGB', (576, 8), 'white')
        ImageDraw.Draw(imagen).line((0, 7, 7, 7), fill='black')
        for cortar, cierre in ((True, b'\n\x1bJ\xff\x1bJ\x41\x1d\x56\x42\x00'),
                               (False, b'\n\x1bJ\xff\x1bJ\x41')):
            datos = bytes_raster(imagen, avance_final_mm=40, cortar=cortar,
                                 margen_superior_mm=1, recortar=True)
            self.assertTrue(datos.endswith(cierre))
            self.assertEqual(datos[10:10 + 72], b'\x00' * 72)  # margen superior
            self.assertEqual(datos[10 + 7 * 72], 0xff)  # último renglón conservado
        self.assertTrue(bytes_raster(imagen, avance_final_mm=0).endswith(b'\n\x1bJ\x00'))
        regla = imagen_calibracion(80)
        self.assertEqual(regla.width, 576)
        for mm in range(0, 41, 5):
            self.assertEqual(regla.getpixel((round(8 * 576 / 80), round(mm * 576 / 80))), (0, 0, 0))

        self.client.force_login(self.d['dueno'])
        ruta = '/ventas/impresion/calibracion/'
        self.assertEqual(self.client.post(ruta, {'intento_impresion': uuid4().hex}).status_code, 403)
        with patch('apps.ventas.escpos.listar_colas', return_value=['Cola simulada']):
            for cortar, cierre in ((True, b'\n\x1bJ\x40\x1d\x56\x42\x00'),
                                   (False, b'\n\x1bJ\x40')):
                self.assertEqual(self.client.post('/ventas/impresion/', {
                    'ancho': '80', 'metodo': 'ESC/POS', 'impresora': 'Cola simulada',
                    'escpos_confirmado': 'on', 'corte_automatico': 'on' if cortar else '',
                    'avance_final_mm': '8',
                }).status_code, 302)
                self.assertContains(self.client.get('/ventas/impresion/'), 'Imprimir ticket de calibración')
                intento = {'intento_impresion': uuid4().hex}
                with patch('apps.ventas.escpos.enviar_cola', return_value=77) as cola:
                    self.assertContains(self.client.post(ruta, intento), 'Calibración 77 aceptada')
                    self.assertEqual(self.client.post(ruta, intento).status_code, 409)
                    cola.assert_called_once()
                    self.assertTrue(cola.call_args.args[1].endswith(cierre))
            intento_fallido = {'intento_impresion': uuid4().hex}
            with patch('apps.ventas.escpos.enviar_cola', side_effect=OSError('cola no disponible')):
                self.assertEqual(self.client.post(ruta, intento_fallido).status_code, 503)
            with patch('apps.ventas.escpos.enviar_cola', return_value=78) as reintento:
                self.assertEqual(self.client.post(ruta, intento_fallido).status_code, 200)
                self.assertEqual(self.client.post(ruta, intento_fallido).status_code, 409)
                reintento.assert_called_once()

    def test_pagina_vertical_para_tickets_cortos_y_largos(self):
        from apps.ventas.ticket import medidas_pagina
        for ancho, puntos in ((80, 576), (58, 384)):
            corta = medidas_pagina({'ancho_px': puntos, 'alto_px': puntos // 2}, {'ancho': ancho})
            larga = medidas_pagina({'ancho_px': puntos, 'alto_px': puntos * 3}, {'ancho': ancho})
            self.assertEqual(corta, {'ancho': ancho, 'alto': ancho + 1})
            self.assertEqual(larga, {'ancho': ancho, 'alto': ancho * 3})
        self.client.force_login(self.d['dueno'])
        respuesta = self.client.get(f'/ventas/{self.venta.pk}/comprobante/')
        medida = re.search(rb'@page \{ size: 80mm (\d+)mm; margin: 0; \}', respuesta.content)
        self.assertIsNotNone(medida)
        self.assertGreater(int(medida.group(1)), 80)

    def test_boton_principal_solo_con_escpos_confirmado(self):
        self.client.force_login(self.d['dueno'])
        ruta = f'/ventas/{self.venta.pk}/comprobante/'
        sin_configurar = self.client.get(ruta)
        self.assertNotContains(sin_configurar, 'id="imprimir-escpos"')
        self.assertContains(sin_configurar, 'activar «ESC/POS»')
        with patch('apps.ventas.escpos.listar_colas', return_value=['DT-230 simulada']):
            respuesta = self.client.post('/ventas/impresion/', {
                'ancho': '80', 'metodo': 'ESC/POS', 'impresora': 'DT-230 simulada',
                'escpos_confirmado': 'on', 'margen_superior_mm': '2',
                'margen_inferior_mm': '5',
            })
        self.assertEqual(respuesta.status_code, 302)
        configurado = self.client.get(ruta)
        self.assertContains(configurado, 'id="form-escpos"')
        self.assertContains(configurado, 'id="imprimir-escpos"')
        self.assertContains(configurado, 'Imprimir ticket')
        self.assertNotContains(configurado, 'id="imprimir-comprobante"')
        self.assertContains(configurado, 'name="intento_impresion"')
        self.assertNotContains(configurado, 'activar «ESC/POS»')
        self.assertContains(configurado, '/static/js/escpos.js')
        self.assertIn("credentials: 'same-origin'", (Path(__file__).resolve().parents[4] / 'frontend/static/js/escpos.js').read_text(encoding='utf-8'))
        self.assertContains(configurado, 'role="status"')
