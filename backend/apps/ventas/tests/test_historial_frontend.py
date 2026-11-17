"""Filtros del historial, con datos ficticios del conjunto de reportes."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.reportes.tests.datos import crear_datos
from apps.ventas.models import Venta


class HistorialVentasTests(TestCase):
    def setUp(self):
        self.datos = crear_datos()
        self.client.force_login(self.datos['dueno'])

    def test_hoy_rango_y_total(self):
        anterior = timezone.now() - timedelta(days=2)
        Venta.objects.filter(pk=self.datos['venta2'].pk).update(fecha=anterior)
        hoy = self.client.get('/ventas/')
        self.assertEqual(hoy.status_code, 200)
        self.assertEqual([v.pk for v in hoy.context['page_obj']], [self.datos['venta'].pk])
        self.assertContains(hoy, 'Bs 30,00')
        desde = (timezone.localdate() - timedelta(days=2)).isoformat()
        hasta = timezone.localdate().isoformat()
        rango = self.client.get('/ventas/', {'desde': desde, 'hasta': hasta})
        self.assertEqual({v.pk for v in rango.context['page_obj']},
                         {self.datos['venta'].pk, self.datos['venta2'].pk})
        self.assertContains(rango, 'Bs 38,00')

    def test_vendedor_y_errores(self):
        Venta.objects.filter(pk=self.datos['venta2'].pk).update(usuario=self.datos['vendedor'])
        respuesta = self.client.get('/ventas/', {'vendedor': self.datos['vendedor'].pk})
        self.assertEqual([v.pk for v in respuesta.context['page_obj']], [self.datos['venta2'].pk])
        hoy = timezone.localdate()
        for params in ({'desde': hoy.isoformat(), 'hasta': (hoy - timedelta(days=1)).isoformat()},
                       {'desde': (hoy - timedelta(days=367)).isoformat(), 'hasta': hoy.isoformat()}):
            error = self.client.get('/ventas/', params)
            self.assertEqual(error.status_code, 422)
            self.assertNotContains(error, 'id="tabla-ventas"', status_code=422)

    def test_paginacion_conserva_filtros_y_permiso(self):
        for _ in range(21):
            Venta.objects.create(caja=self.datos['caja'], usuario=self.datos['dueno'],
                                 total=Decimal('1.00'), creado_por=self.datos['dueno'],
                                 modificado_por=self.datos['dueno'])
        hoy = timezone.localdate().isoformat()
        respuesta = self.client.get('/ventas/', {'desde': hoy, 'hasta': hoy, 'page': '2'})
        self.assertContains(respuesta, f'desde={hoy}&amp;hasta={hoy}&amp;page=1')
        self.assertContains(respuesta, 'Bs 59,00')
        self.datos['vendedor'].rol = None
        self.datos['vendedor'].save(update_fields=['rol'])
        self.client.force_login(self.datos['vendedor'])
        self.assertEqual(self.client.get('/ventas/').status_code, 403)
