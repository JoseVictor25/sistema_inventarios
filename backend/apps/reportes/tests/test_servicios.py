"""Cálculos verificables sobre operaciones reales y SQLite de pruebas."""
from datetime import datetime, date, timedelta, timezone as tz
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.db import connection
from django.test.utils import CaptureQueriesContext
from apps.auditoria.models import LogAuditoria
from apps.caja.models import Caja
from apps.catalogo.models import Producto
from apps.inventario.models import Lote
from apps.ventas.models import Venta, Pago
from apps.core.exceptions import ErrorDeNegocio
from apps.reportes.services import consultar_reporte, REPORTES, ZONA
from .datos import crear_datos


class ReportesServiciosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = crear_datos()

    def consultar(self, nombre, **filtros):
        datos = {} if nombre == 'inventario_valorizado' else {'dias': 30} if nombre == 'vencimientos' else {'desde': self.d['hoy'], 'hasta': self.d['hoy']}
        if nombre == 'ventas':
            datos['agrupar'] = 'dia'
        return consultar_reporte(self.d['dueno'], nombre, {**datos, **filtros})

    def test_totales_ocho_reportes(self):
        resultados = {n: self.consultar(n) for n in REPORTES}
        self.assertEqual(resultados['ventas']['totales'], {'cantidad': 2, 'total': Decimal('38')})
        self.assertEqual(resultados['ventas_metodo_pago']['totales']['total'], Decimal('38'))
        self.assertEqual(resultados['productos_mas_vendidos']['totales'], {'unidades': 7, 'total': Decimal('38')})
        self.assertEqual(resultados['compras']['totales']['total'], Decimal('50'))
        self.assertEqual(resultados['inventario_valorizado']['totales'], {'stock': 8, 'valor': Decimal('32')})
        self.assertEqual(resultados['ganancias']['totales'], {'ventas': Decimal('38'), 'costo': Decimal('18'), 'ganancia': Decimal('20')})
        self.assertEqual(resultados['vencimientos']['totales']['stock'], 8)
        self.assertEqual(resultados['cierres_caja']['totales'], {'esperado': Decimal('81'), 'contado': Decimal('80'), 'diferencia': Decimal('-1')})

    def test_pagos_mixtos_cuenta_ventas_distintas(self):
        filas = {f['metodo']: f for f in self.consultar('ventas_metodo_pago')['filas']}
        self.assertEqual(filas['Efectivo']['cantidad'], 2)
        self.assertEqual(filas['Efectivo']['total'], Decimal('28'))
        self.assertEqual(filas['QR']['cantidad'], 1)
        self.assertEqual(filas['QR']['total'], Decimal('10'))
        # Datos históricos con dos pagos del mismo método tampoco duplican conteo.
        Pago.objects.create(venta=self.d['venta'], metodo=self.d['qr'], monto=Decimal('1'))
        filas = {f['metodo']: f for f in self.consultar('ventas_metodo_pago')['filas']}
        self.assertEqual(filas['QR']['cantidad'], 1)

    def test_historial_no_usa_equivalencia_ni_precio_actual(self):
        p = self.d['presentacion']
        p.unidades_equivalentes, p.precio_venta = 12, Decimal('999')
        p.save()
        self.assertEqual(self.consultar('productos_mas_vendidos')['totales'], {'unidades': 7, 'total': Decimal('38')})
        self.assertEqual(self.consultar('ganancias')['totales']['ganancia'], Decimal('20'))

    def test_promedio_redondeado_no_recalcula_valor(self):
        Lote.objects.filter(producto=self.d['producto']).update(cantidad_actual=0)
        for codigo, cantidad, costo in [('X1', 1, '1'), ('X2', 2, '2')]:
            Lote.objects.create(producto=self.d['producto'], codigo_lote=codigo, cantidad_inicial=cantidad, cantidad_actual=cantidad, costo_unitario=Decimal(costo))
        fila = self.consultar('inventario_valorizado')['filas'][0]
        self.assertEqual((fila['stock'], fila['costo'], fila['valor']), (3, Decimal('1.67'), Decimal('5')))

    def test_inventario_inactivo_vencido_y_sin_lotes(self):
        Producto.objects.filter(pk=self.d['producto'].pk).update(activo=False)
        Lote.objects.update(fecha_vencimiento=self.d['hoy'] - timedelta(days=1))
        filas = self.consultar('inventario_valorizado')['filas']
        self.assertIn('(inactivo)', filas[0]['producto'])
        self.assertEqual(filas[0]['valor'], Decimal('32'))
        self.assertIsNone(filas[1]['costo'])
        self.assertEqual(filas[1]['stock'], 0)

    def test_categoria_exacta_incluye_historico_inactivo(self):
        self.d['categoria'].activa = False
        self.d['categoria'].save()
        self.assertEqual(self.consultar('inventario_valorizado', categoria=self.d['categoria'].pk)['totales']['stock'], 8)
        self.assertEqual(self.consultar('inventario_valorizado', categoria=self.d['hija'].pk)['totales']['stock'], 0)
        self.assertFalse(self.consultar('ganancias', categoria=self.d['hija'].pk)['filas'])

    def test_filtros_proveedor_usuario(self):
        self.assertEqual(len(self.consultar('compras', proveedor=self.d['proveedor'].pk)['filas']), 1)
        self.assertFalse(self.consultar('cierres_caja', usuario=self.d['vendedor'].pk)['filas'])
        self.assertEqual(len(self.consultar('cierres_caja', usuario=self.d['dueno'].pk)['filas']), 1)

    def test_cierre_prioriza_instantanea(self):
        Pago.objects.all().update(monto=Decimal('100'))
        self.assertEqual(self.consultar('cierres_caja')['totales']['esperado'], Decimal('81'))
        self.assertFalse(self.consultar('cierres_caja')['notas'])

    def test_cierre_antiguo_recalculado_sin_escrituras(self):
        LogAuditoria.objects.filter(accion='CIERRE_CAJA').delete()
        with CaptureQueriesContext(connection) as consultas:
            resultado = self.consultar('cierres_caja')
        self.assertEqual(resultado['totales']['diferencia'], Decimal('-1'))
        self.assertIn('recalculados', resultado['notas'][0])
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in consultas))

    def test_cierre_incompleto_error_controlado(self):
        LogAuditoria.objects.filter(accion='CIERRE_CAJA').delete()
        Caja.objects.filter(pk=self.d['caja'].pk).update(monto_contado=None)
        with self.assertRaises(ErrorDeNegocio):
            self.consultar('cierres_caja')

    def test_cierre_resumen_invalido_recalcula(self):
        LogAuditoria.objects.filter(accion='CIERRE_CAJA').update(valor_nuevo={'version': 1, 'caja_id': self.d['caja'].pk, 'esperado': 'NaN'})
        self.assertEqual(self.consultar('cierres_caja')['totales']['esperado'], Decimal('81'))
        self.assertTrue(self.consultar('cierres_caja')['notas'])

    def test_limites_vencimiento(self):
        Lote.objects.all().update(cantidad_actual=0)
        for n, dias, cantidad in [('ayer', -1, 1), ('hoy', 0, 1), ('limite', 30, 1), ('fuera', 31, 1), ('agotado', 5, 0), ('sinfecha', None, 1)]:
            Lote.objects.create(producto=self.d['producto'], codigo_lote=n, cantidad_inicial=1, cantidad_actual=cantidad, costo_unitario=Decimal('1'), fecha_vencimiento=self.d['hoy'] + timedelta(days=dias) if dias is not None else None)
        self.assertEqual([f['lote'] for f in self.consultar('vencimientos')['filas']], ['hoy', 'limite'])
        self.assertEqual([f['lote'] for f in self.consultar('vencimientos', dias=0)['filas']], ['hoy'])

    def test_fechas_inclusivas_y_zona_horaria(self):
        Venta.objects.filter(pk=self.d['venta'].pk).update(fecha=datetime(2026, 1, 2, 3, 59, tzinfo=tz.utc))
        Venta.objects.filter(pk=self.d['venta2'].pk).update(fecha=datetime(2026, 1, 2, 4, 0, tzinfo=tz.utc))
        self.assertEqual(self.consultar('ventas', desde='2026-01-01', hasta='2026-01-01')['totales']['total'], Decimal('30'))
        self.assertEqual(self.consultar('ventas', desde='2026-01-02', hasta='2026-01-02')['totales']['total'], Decimal('8'))

    def test_semanas_y_meses(self):
        Venta.objects.filter(pk=self.d['venta'].pk).update(fecha=datetime(2026, 1, 4, 12, tzinfo=ZONA))
        Venta.objects.filter(pk=self.d['venta2'].pk).update(fecha=datetime(2026, 1, 5, 12, tzinfo=ZONA))
        filas = self.consultar('ventas', desde='2026-01-01', hasta='2026-01-31', agrupar='semana')['filas']
        self.assertEqual([f['periodo'] for f in filas], ['Semana desde lunes 2025-12-29', 'Semana desde lunes 2026-01-05'])
        filas = self.consultar('ventas', desde='2026-01-01', hasta='2026-01-31', agrupar='mes')['filas']
        self.assertEqual(filas, [dict(periodo='2026-01', cantidad=2, total=Decimal('38'))])

    def test_rango_366_y_367_dias(self):
        self.consultar('ventas', desde='2024-01-01', hasta='2024-12-31')
        with self.assertRaises(ErrorDeNegocio):
            self.consultar('ventas', desde='2024-01-01', hasta='2025-01-01')

    def test_filtros_invalidos(self):
        casos = [('ventas', {'desde': 'mal'}), ('ventas', {'desde': '2026-02-02', 'hasta': '2026-01-01'}), ('ventas', {'agrupar': 'anio'}), ('compras', {'proveedor': 999999}), ('ganancias', {'categoria': 999999}), ('cierres_caja', {'usuario': 999999}), ('vencimientos', {'dias': -1}), ('vencimientos', {'dias': 10**20}), ('ventas', {'costos': 1})]
        for nombre, filtros in casos:
            with self.subTest(nombre=nombre, filtros=filtros), self.assertRaises(ErrorDeNegocio):
                self.consultar(nombre, **filtros)

    def test_periodos_vacios(self):
        for nombre in REPORTES:
            if nombre in ('inventario_valorizado', 'vencimientos'):
                continue
            with self.subTest(nombre=nombre):
                resultado = self.consultar(nombre, desde='2000-01-01', hasta='2000-01-01')
                self.assertFalse(resultado['filas'])
                self.assertTrue(all(v == 0 for v in resultado['totales'].values()))

    def test_precision_decimal(self):
        Venta.objects.all().update(total=Decimal('0.10'))
        self.assertEqual(self.consultar('ventas')['totales']['total'], Decimal('0.20'))

    def test_ganancia_negativa(self):
        from apps.ventas.models import DetalleVenta
        DetalleVenta.objects.all().update(subtotal=Decimal('1'))
        self.assertEqual(self.consultar('ganancias')['totales']['ganancia'], Decimal('-16'))

    def test_consultas_no_crecen_por_producto(self):
        with CaptureQueriesContext(connection) as antes:
            self.consultar('inventario_valorizado')
        Producto.objects.bulk_create([Producto(codigo=f'N{i}', nombre=f'Extra{i}', categoria=self.d['categoria']) for i in range(30)])
        with CaptureQueriesContext(connection) as despues:
            resultado = self.consultar('inventario_valorizado')
        self.assertEqual(len(antes), len(despues))
        self.assertEqual(len(resultado['filas']), 32)

    def test_cierres_sin_n_mas_uno(self):
        with CaptureQueriesContext(connection) as antes:
            self.consultar('cierres_caja')
        Caja.objects.bulk_create([Caja(usuario=self.d['dueno'], estado='CERRADA', fecha_cierre=self.d['caja'].fecha_cierre, monto_inicial=Decimal('0'), monto_contado=Decimal('0')) for _ in range(25)])
        with CaptureQueriesContext(connection) as despues:
            resultado = self.consultar('cierres_caja')
        self.assertEqual(len(antes), len(despues))
        self.assertEqual(len(resultado['filas']), 26)
