from io import BytesIO
import os
import json
from PIL import Image
from unittest.mock import patch
from django.test import SimpleTestCase
from . import test_respaldos_fase9 as base
from apps.core import respaldos as r


class RespaldoQRTests(SimpleTestCase):
    setUp = base.RespaldosTests.setUp
    crear = base.RespaldosTests.crear
    def imagen(self):
        salida = BytesIO()
        Image.new('RGB', (256, 256), 'white').save(salida, 'PNG')
        ruta = self.raiz / 'qr_bancario.png'
        ruta.write_bytes(salida.getvalue())
        return ruta

    def test_recuperacion_qr_integridad(self):
        qr = self.imagen()
        datos = r.crear_copia(self.origen, self.destino, 2, qr=qr)
        self.assertTrue(datos['qr_incluido'])
        resultado = r.recuperar_temporal(self.destino / datos['archivo'], self.raiz / 'recuperada')
        self.assertTrue(resultado['qr_restaurado'])
        self.assertEqual((self.raiz / 'recuperada/qr_bancario.png').read_bytes(), qr.read_bytes())
        self.assertEqual(r.hash_archivo(self.origen), self.hash_original)
        with self.assertRaises(FileExistsError):
            r.recuperar_temporal(self.destino / datos['archivo'], self.raiz / 'recuperada')

    def test_compatibilidad_sin_qr(self):
        datos = self.crear()
        resultado = r.recuperar_temporal(self.destino / datos['archivo'], self.raiz / 'antigua')
        self.assertFalse(resultado['qr_restaurado'])
        self.assertFalse((self.raiz / 'antigua/qr_bancario.png').exists())

    def test_qr_corrupto_no_publica(self):
        qr = self.imagen(); qr.write_bytes(b'corrupto')
        with self.assertRaises(r.ErrorRespaldo):
            r.crear_copia(self.origen, self.destino, 2, qr=qr)
        self.assertFalse(list(self.destino.glob('*.sqlite3')))
        self.assertFalse(list(self.destino.glob('*.partial')))

    def test_qr_ausente_y_enlace_duro(self):
        datos = r.crear_copia(self.origen, self.destino, 2, qr=self.raiz / 'ausente.png')
        self.assertFalse(datos['qr_incluido'])
        qr = self.imagen()
        os.link(qr, self.raiz / 'enlace.png')
        with self.assertRaises(r.ErrorRespaldo):
            r.crear_copia(self.origen, self.destino, 2, qr=qr)

    def test_manifiesto_alterado_no_recupera_ni_retiene(self):
        datos = r.crear_copia(self.origen, self.destino, 2, qr=self.imagen())
        copia = self.destino / datos['archivo']
        manifiesto = copia.with_suffix('.json')
        meta = json.loads(manifiesto.read_text())
        meta['qr']['sha256'] = '0' * 64
        manifiesto.write_text(json.dumps(meta))
        with self.assertRaises(r.ErrorRespaldo):
            r.recuperar_temporal(copia, self.raiz / 'fallida')
        self.assertFalse((self.raiz / 'fallida').exists())
        self.crear(conservar=1)
        self.assertTrue(copia.exists())
        self.assertFalse(next(f for f in r.listar_copias(self.destino) if f['nombre'] == copia.name)['verificado'])

    def test_retencion_incluye_qr_y_rechaza_destino_fuera_temp(self):
        datos = r.crear_copia(self.origen, self.destino, 1, qr=self.imagen())
        copia = self.destino / datos['archivo']
        with patch('apps.core.respaldos.tempfile.gettempdir', return_value=str(self.raiz / 'otro')):
            with self.assertRaises(r.ErrorRespaldo):
                r.recuperar_temporal(copia, self.raiz / 'noautorizada')
        self.crear(conservar=1)
        self.assertFalse(copia.exists())
        self.assertFalse(copia.with_suffix('.json').exists())

    def test_error_recuperacion_limpia_solo_sus_archivos(self):
        datos = self.crear()
        verificar = r.verificar_copia
        with patch.object(r, 'verificar_copia', side_effect=[verificar(self.destino / datos['archivo']), r.ErrorRespaldo('fallo')]):
            with self.assertRaises(r.ErrorRespaldo):
                r.recuperar_temporal(self.destino / datos['archivo'], self.raiz / 'fallida')
        self.assertFalse((self.raiz / 'fallida').exists())
