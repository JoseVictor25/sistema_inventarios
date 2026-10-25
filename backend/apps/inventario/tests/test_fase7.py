"""Fase 7: consultas, escritura atómica, autorización y exposición de costos."""
from datetime import timedelta, datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.catalogo.models import Categoria, Producto, Presentacion
from apps.inventario.models import Lote, MovimientoInventario, OperacionAjusteInventario
from apps.inventario import services as s
from apps.auditoria.models import LogAuditoria
from apps.usuarios.models import Usuario, Rol


def preparar():
    call_command('cargar_datos_iniciales', stdout=StringIO())
    dueno = Usuario.objects.create_user('dueno7', rol=Rol.objects.get(nombre='Dueño'))
    vendedor = Usuario.objects.create_user('vendedor7', rol=Rol.objects.get(nombre='Vendedor'))
    categoria = Categoria.objects.create(nombre='Prueba fase 7')
    producto = Producto.objects.create(codigo='F7', nombre='Producto fase 7', categoria=categoria, stock_minimo=5)
    presentacion = Presentacion.objects.create(producto=producto, nombre='Unidad', unidades_equivalentes=1, precio_venta=Decimal('10'))
    return dueno, vendedor, producto, presentacion


def lote(producto, codigo, actual, fecha=None, inicial=None):
    return Lote.objects.create(producto=producto, codigo_lote=codigo, cantidad_actual=actual,
        cantidad_inicial=inicial if inicial is not None else max(actual, 1),
        fecha_vencimiento=fecha, costo_unitario=Decimal('9876.54'))


class ConsultasFase7Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dueno, cls.vendedor, cls.producto, cls.presentacion = preparar()

    def test_producto_sin_lotes_y_minimo_cero(self):
        Producto.objects.filter(pk=self.producto.pk).update(stock_minimo=0)
        fila = s.listar_stock(self.vendedor, {'solo_bajo': '1'})[0]
        self.assertEqual(fila['stock_actual'], 0)
        self.assertEqual(fila['stock_disponible'], 0)
        self.assertEqual(len(s.obtener_alertas(usuario=self.vendedor)['stock_bajo']), 1)

    def test_stock_fisico_y_disponible(self):
        hoy = timezone.localdate()
        lote(self.producto, 'VENCIDO', 10, hoy - timedelta(days=1))
        lote(self.producto, 'HOY', 2, hoy)
        lote(self.producto, 'FUTURO', 3, hoy + timedelta(days=31))
        lote(self.producto, 'SIN-FECHA', 4)
        lote(self.producto, 'AGOTADO', 0, hoy)
        fila = s.listar_stock(self.vendedor)[0]
        self.assertEqual(fila['stock_actual'], 19)
        self.assertEqual(fila['stock_disponible'], 9)
        self.assertEqual(self.producto.stock_actual, 19)

    def test_solo_vencidos_no_hay_disponible(self):
        lote(self.producto, 'VENCIDO', 10, timezone.localdate() - timedelta(days=1))
        fila = s.listar_stock(self.vendedor)[0]
        self.assertEqual((fila['stock_actual'], fila['stock_disponible']), (10, 0))
        self.assertFalse(s.obtener_alertas(usuario=self.vendedor)['stock_bajo'])
        self.assertEqual(len(s.obtener_alertas(usuario=self.vendedor)['vencidos']), 1)

    def test_stock_bajo_incluye_igual_no_suficiente(self):
        registro = lote(self.producto, 'MINIMO', 5, inicial=6)
        self.assertEqual(len(s.listar_stock(self.vendedor, {'solo_bajo': '1'})), 1)
        Lote.objects.filter(pk=registro.pk).update(cantidad_actual=6)
        self.assertEqual(len(s.listar_stock(self.vendedor, {'solo_bajo': '1'})), 0)

    @override_settings(DIAS_ALERTA_VENCIMIENTO=30)
    def test_limites_vencimiento_y_agotados(self):
        hoy = timezone.localdate()
        for codigo, dias, cantidad in [('AYER', -1, 1), ('HOY', 0, 1), ('LIMITE', 30, 1), ('DESPUES', 31, 1), ('VACIO', -1, 0)]:
            lote(self.producto, codigo, cantidad, hoy + timedelta(days=dias))
        lote(self.producto, 'NULO', 1)
        alertas = s.obtener_alertas(usuario=self.vendedor)
        self.assertEqual({x['codigo_lote'] for x in alertas['por_vencer']}, {'HOY', 'LIMITE'})
        self.assertEqual({x['codigo_lote'] for x in alertas['vencidos']}, {'AYER'})

    @override_settings(DIAS_ALERTA_VENCIMIENTO=0)
    def test_alerta_cero_dias(self):
        lote(self.producto, 'HOY', 1, timezone.localdate())
        lote(self.producto, 'MANANA', 1, timezone.localdate() + timedelta(days=1))
        self.assertEqual([x['codigo_lote'] for x in s.obtener_alertas(usuario=self.vendedor)['por_vencer']], ['HOY'])

    @override_settings(TIME_ZONE='America/La_Paz', DIAS_ALERTA_VENCIMIENTO=0)
    def test_fecha_local_alrededor_de_medianoche(self):
        from datetime import timezone as tz
        instante = datetime(2026, 10, 26, 2, 0, tzinfo=tz.utc)  # En Bolivia todavía es 25.
        lote(self.producto, 'LOCAL', 1, datetime(2026, 10, 25).date())
        with patch('django.utils.timezone.now', return_value=instante):
            self.assertEqual(len(s.obtener_alertas(usuario=self.vendedor)['por_vencer']), 1)
            self.assertEqual(s.listar_stock(self.vendedor)[0]['stock_disponible'], 1)

    def test_inactivos_con_stock_y_historial_agotado(self):
        Producto.objects.filter(pk=self.producto.pk).update(activo=False)
        self.assertFalse(s.listar_stock(self.vendedor))
        registro = lote(self.producto, 'INACTIVO', 2, timezone.localdate())
        self.assertFalse(s.listar_stock(self.vendedor)[0]['activo'])
        self.assertEqual(len(s.obtener_alertas(usuario=self.vendedor)['por_vencer']), 1)
        Lote.objects.filter(pk=registro.pk).update(cantidad_actual=0)
        self.assertFalse(s.obtener_alertas(usuario=self.vendedor)['por_vencer'])
        self.assertEqual(len(s.listar_lotes(self.vendedor, {'estado': 'agotado'})), 1)

    def test_proyeccion_costos_y_filtros_manipulados(self):
        lote(self.producto, 'COSTO', 1)
        self.assertNotIn('costo_unitario', s.listar_lotes(self.vendedor)[0])
        self.assertIn('costo_unitario', s.listar_lotes(self.dueno)[0])
        for filtros in ({'costo_unitario': '1'}, {'estado': 'otro'}, {'producto': '-1'}, {'page': 'no'}):
            with self.assertRaises(ErrorDeNegocio):
                s.listar_lotes(self.vendedor, filtros)

    def test_filtros_lotes_y_busqueda(self):
        hoy = timezone.localdate()
        lote(self.producto, 'AYER', 1, hoy - timedelta(days=1))
        lote(self.producto, 'HOY', 1, hoy)
        lote(self.producto, 'NULO', 1)
        self.assertEqual(len(s.listar_lotes(self.vendedor, {'estado': 'vigente'})), 2)
        self.assertEqual(len(s.listar_lotes(self.vendedor, {'estado': 'vencido'})), 1)
        self.assertEqual(len(s.listar_lotes(self.vendedor, {'estado': 'sin_fecha'})), 1)
        self.assertEqual(len(s.listar_lotes(self.vendedor, {'q': 'HOY', 'producto': self.producto.pk})), 1)
        self.assertEqual(len(s.listar_stock(self.vendedor, {'q': 'F7'})), 1)
        self.assertEqual(len(s.listar_stock(self.vendedor, {'q': 'ausente'})), 0)

    def test_paginacion_stock_lotes_alertas_y_movimientos(self):
        for n in range(22):
            producto = Producto.objects.create(codigo=f'P{n}', nombre=f'Producto {n}', categoria=self.producto.categoria)
            registro = lote(producto, f'L{n}', 1, timezone.localdate())
            MovimientoInventario.objects.create(lote=registro, tipo='ENTRADA', cantidad=1, usuario=self.dueno)
        for funcion in (s.listar_stock, s.listar_lotes, s.listar_movimientos):
            self.assertEqual(len(funcion(self.vendedor)), 20)
            self.assertGreater(len(funcion(self.vendedor, {'page': 2})), 0)
        alertas = s.obtener_alertas(usuario=self.vendedor, filtros={'page_por_vencer': 2})
        self.assertEqual(len(alertas['por_vencer']), 2)
        self.assertEqual(len(alertas['stock_bajo']), 20)

    def test_numero_consultas_no_crece_por_fila(self):
        def contar():
            with CaptureQueriesContext(connection) as capturas:
                list(s.listar_stock(self.vendedor))
                list(s.listar_lotes(self.vendedor))
            return len(capturas)
        lote(self.producto, 'UNO', 1)
        contar()  # Cargar rol, no contar el caché inicial de FK del actor.
        inicial = contar()
        for n in range(15):
            producto = Producto.objects.create(codigo=f'P{n}', nombre=f'P{n}', categoria=self.producto.categoria)
            lote(producto, f'L{n}', 1)
        self.assertEqual(contar(), inicial)

    def test_movimientos_fechas_tipos_y_no_costos(self):
        registro = lote(self.producto, 'HISTORIA', 1)
        mov = MovimientoInventario.objects.create(lote=registro, tipo='ENTRADA', cantidad=1, motivo='Compra de prueba', usuario=self.dueno)
        hoy = timezone.localdate().isoformat()
        filas = s.listar_movimientos(self.vendedor, {'lote': registro.pk, 'desde': hoy, 'hasta': hoy, 'tipo': 'ENTRADA'})
        self.assertEqual(filas[0]['id'], mov.pk)
        self.assertNotIn('costo_unitario', filas[0])
        self.assertFalse(s.listar_movimientos(self.vendedor, {'tipo': 'SALIDA'}))
        with self.assertRaises(ErrorDeNegocio):
            s.listar_movimientos(self.vendedor, {'desde': '2026-10-26', 'hasta': '2026-10-25'})


class AjustesFase7Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dueno, cls.vendedor, cls.producto, cls.presentacion = preparar()
        cls.lote = lote(cls.producto, 'AJUSTE', 10, inicial=20)

    def test_ajustes_y_merma_con_auditoria(self):
        for tipo, cantidad, esperado in [('AJUSTE', 2, 12), ('AJUSTE', -1, 11), ('MERMA', -3, 8)]:
            mov = s.ajustar_inventario(self.dueno, self.lote, tipo, cantidad, '  Conteo físico  ')
            self.lote.refresh_from_db()
            self.assertEqual(self.lote.cantidad_actual, esperado)
            log = LogAuditoria.objects.get(valor_nuevo__movimiento_id=mov.pk)
            self.assertEqual(log.usuario, self.dueno)
            self.assertEqual(log.valor_nuevo['cantidad_actual'], esperado)
            self.assertEqual(log.valor_anterior['cantidad_actual'], esperado - cantidad)
            self.assertEqual(mov.motivo, 'Conteo físico')
        self.assertEqual(self.lote.costo_unitario, Decimal('9876.54'))
        self.assertEqual(self.lote.cantidad_inicial, 20)

    def test_validaciones_estrictas(self):
        for tipo, cantidad, motivo in [('ENTRADA', 1, 'Prueba'), ('SALIDA', -1, 'Prueba'),
                ('MERMA', 1, 'Prueba'), ('AJUSTE', 0, 'Prueba'), ('AJUSTE', True, 'Prueba'),
                ('AJUSTE', 1.5, 'Prueba'), ('AJUSTE', '1', 'Prueba'), ('AJUSTE', -11, 'Prueba'),
                ('AJUSTE', 11, 'Prueba'), ('AJUSTE', 1, ' abc '), ('AJUSTE', 1, 'x' * 201)]:
            with self.subTest(tipo=tipo, cantidad=cantidad, motivo=motivo):
                with self.assertRaises(ErrorDeNegocio):
                    s.ajustar_inventario(self.dueno, self.lote, tipo, cantidad, motivo)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_actual, 10)
        self.assertFalse(MovimientoInventario.objects.exists())
        self.assertFalse(LogAuditoria.objects.exists())

    def test_lote_inexistente(self):
        with self.assertRaises(ErrorDeNegocio):
            s.ajustar_inventario(self.dueno, 999999, 'AJUSTE', 1, 'Prueba')

    def test_rollback_si_falla_movimiento_o_auditoria(self):
        for objetivo in ('apps.inventario.services.MovimientoInventario.save', 'apps.inventario.services.registrar_cambio'):
            with patch(objetivo, side_effect=ValidationError('Fallo simulado')):
                with self.assertRaises(ErrorDeNegocio):
                    s.ajustar_inventario(self.dueno, self.lote, 'MERMA', -1, 'Prueba')
            self.lote.refresh_from_db()
            self.assertEqual(self.lote.cantidad_actual, 10)
            self.assertFalse(MovimientoInventario.objects.exists())
            self.assertFalse(LogAuditoria.objects.exists())
            self.assertFalse(OperacionAjusteInventario.objects.exists())

    def test_cantidad_se_relee_no_confia_instancia_vieja(self):
        Lote.objects.filter(pk=self.lote.pk).update(cantidad_actual=1)
        with self.assertRaises(ErrorDeNegocio):
            s.ajustar_inventario(self.dueno, self.lote, 'MERMA', -2, 'Prueba')

    def test_claves_diferentes_permiten_operaciones_independientes(self):
        c1, c2 = uuid4(), uuid4()
        m1 = s.ajustar_inventario(self.dueno, self.lote, 'MERMA', -1, 'Prueba 1', clave=c1)
        m2 = s.ajustar_inventario(self.dueno, self.lote, 'MERMA', -1, 'Prueba 2', clave=c2)
        self.assertNotEqual(m1.pk, m2.pk)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_actual, 8)
        self.assertEqual(MovimientoInventario.objects.count(), 2)
        self.assertEqual(LogAuditoria.objects.count(), 2)
        self.assertEqual(OperacionAjusteInventario.objects.count(), 2)

    def test_permisos_servicios(self):
        sinrol = Usuario.objects.create_user('sinrol')
        inactivo = Usuario.objects.create_user('inactivo', rol=self.dueno.rol, is_active=False)
        for actor in (sinrol, inactivo, AnonymousUser()):
            for funcion in (s.listar_stock, s.listar_lotes, s.listar_movimientos):
                with self.assertRaises(PermissionDenied):
                    funcion(actor)
            with self.assertRaises(PermissionDenied):
                s.obtener_alertas(usuario=actor)
        for actor in (sinrol, inactivo, AnonymousUser(), self.vendedor):
            with self.assertRaises(PermissionDenied):
                s.ajustar_inventario(actor, self.lote, 'MERMA', -1, 'Prueba')
        superusuario = Usuario.objects.create_superuser('super7', password=None)
        s.ajustar_inventario(superusuario, self.lote, 'AJUSTE', 1, 'Prueba')

    def test_integracion_compra_venta_ajuste_caja(self):
        from apps.compras.services import registrar_compra
        from apps.compras.models import Proveedor
        from apps.caja.services import abrir_caja, cerrar_caja
        from apps.ventas.services import registrar_venta
        from apps.ventas.models import MetodoPago
        producto = Producto.objects.create(codigo='CICLO', nombre='Ciclo', categoria=self.producto.categoria)
        pres = Presentacion.objects.create(producto=producto, nombre='Par', unidades_equivalentes=2, precio_venta=Decimal('10'))
        proveedor = Proveedor.objects.create(nombre='Proveedor', tipo='EMPRESA')
        compra = registrar_compra(self.dueno, proveedor, [{'producto_id': producto.pk, 'cantidad': 10, 'costo_unitario': '2'}])
        registro = Lote.objects.get(producto=producto)
        caja = abrir_caja(self.vendedor, '0', clave=uuid4())
        venta = registrar_venta(self.vendedor, [{'presentacion_id': pres.pk, 'cantidad': 2}],
            [{'metodo_id': MetodoPago.objects.get(nombre='Efectivo').pk, 'monto': '20'}], clave=uuid4())
        historicos = list(MovimientoInventario.objects.values().order_by('pk'))
        s.ajustar_inventario(self.dueno, registro, 'MERMA', -1, 'Producto dañado')
        self.assertEqual(producto.stock_actual, 5)
        self.assertEqual(list(MovimientoInventario.objects.filter(pk__in=[x['id'] for x in historicos]).values().order_by('pk')), historicos)
        self.assertEqual(venta.total, Decimal('20'))
        self.assertEqual(compra.total, Decimal('20'))
        self.assertEqual(cerrar_caja(self.vendedor, caja.pk, '20', clave=uuid4())['resultado'], 'CUADRA')


from apps.core.exceptions import ErrorDeNegocio


class PantallasFase7Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dueno, cls.vendedor, cls.producto, cls.presentacion = preparar()
        cls.lote = lote(cls.producto, 'LOTE-HTTP', 10, inicial=20)

    def test_cinco_pantallas_dueno_y_recorrido_post(self):
        self.client.force_login(self.dueno)
        for ruta in ('', 'lotes/', 'alertas/', 'movimientos/', 'ajuste/'):
            self.assertEqual(self.client.get('/inventario/' + ruta).status_code, 200)
        respuesta = self.client.post('/inventario/ajuste/', {'lote': self.lote.pk, 'tipo': 'MERMA', 'cantidad': -1, 'motivo': 'Prueba HTTP'}, follow=True)
        self.assertContains(respuesta, 'registrado')
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_vendedor_consulta_no_ajusta_y_no_costos(self):
        self.client.force_login(self.vendedor)
        for ruta in ('', 'lotes/', 'alertas/', 'movimientos/'):
            for headers in ({}, {'HTTP_HX_REQUEST': 'true'}, {'HTTP_ACCEPT': 'application/json'}):
                respuesta = self.client.get('/inventario/' + ruta, **headers)
                self.assertEqual(respuesta.status_code, 200)
                self.assertNotContains(respuesta, '9876')
                self.assertNotContains(respuesta, 'Costo unitario')
        self.assertEqual(self.client.get('/inventario/ajuste/').status_code, 403)
        self.assertEqual(self.client.post('/inventario/ajuste/', {}).status_code, 403)
        self.assertContains(self.client.get('/inventario/'), 'href="/inventario/"')

    def test_anonimo_y_sin_rol(self):
        for metodo in (self.client.get, self.client.post):
            self.assertEqual(metodo('/inventario/ajuste/').status_code, 302)
        self.client.force_login(Usuario.objects.create_user('sinrol'))
        for ruta in ('', 'lotes/', 'alertas/', 'movimientos/', 'ajuste/'):
            self.assertEqual(self.client.get('/inventario/' + ruta).status_code, 403)

    def test_csrf_campos_protegidos_y_validacion(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.dueno)
        self.assertEqual(cliente.post('/inventario/ajuste/', {}).status_code, 403)
        self.client.force_login(self.dueno)
        datos = {'lote': self.lote.pk, 'tipo': 'AJUSTE', 'cantidad': 1, 'motivo': 'Prueba'}
        for campo in ('costo_unitario', 'usuario', 'cantidad_inicial', 'fecha'):
            self.assertEqual(self.client.post('/inventario/ajuste/', {**datos, campo: '1'}).status_code, 422)
        for ruta in ('/inventario/?page=no', '/inventario/lotes/?estado=no', '/inventario/alertas/?page_bajo=-1', '/inventario/movimientos/?hasta=error'):
            self.assertEqual(self.client.get(ruta).status_code, 422)
        self.assertEqual(self.client.get('/inventario/ajuste/?lote=no').status_code, 422)
        self.assertFalse(MovimientoInventario.objects.exists())

    def test_admin_no_expone_costos_con_solo_permiso_tecnico(self):
        from apps.compras.models import Compra, DetalleCompra, Proveedor
        proveedor = Proveedor.objects.create(nombre='P', tipo='EMPRESA')
        compra = Compra.objects.create(proveedor=proveedor, usuario=self.dueno, total=Decimal('9876.54'))
        detalle = DetalleCompra.objects.create(compra=compra, producto=self.producto, cantidad_unidades=1, costo_unitario=Decimal('9876.54'), subtotal=Decimal('9876.54'))
        self.vendedor.is_staff = True
        self.vendedor.save(update_fields=['is_staff'])
        self.vendedor.user_permissions.add(*Permission.objects.filter(codename__in=['view_lote', 'view_compra', 'view_detallecompra']))
        self.client.force_login(self.vendedor)
        for app, modelo, pk in [('inventario', 'lote', self.lote.pk), ('compras', 'compra', compra.pk), ('compras', 'detallecompra', detalle.pk)]:
            for sufijo in ('', f'{pk}/change/', '?costo_unitario__gte=1'):
                self.assertEqual(self.client.get(f'/admin/{app}/{modelo}/{sufijo}').status_code, 403)
        self.vendedor.rol = self.dueno.rol
        self.vendedor.save(update_fields=['rol'])
        self.assertEqual(self.client.get(f'/admin/inventario/lote/{self.lote.pk}/change/').status_code, 200)
        self.dueno.is_staff = True
        self.dueno.save(update_fields=['is_staff'])
        self.client.force_login(self.dueno)
        self.assertEqual(self.client.get('/admin/inventario/lote/').status_code, 403)

    def test_ux_formulario_ajuste_elementos_informativos(self):
        """Verifica que el formulario incluye la guía conceptual, métricas del lote y ejemplos."""
        self.client.force_login(self.dueno)
        respuesta = self.client.get(f'/inventario/ajuste/?lote={self.lote.pk}')
        self.assertEqual(respuesta.status_code, 200)

        # 1. Sección informativa conceptual
        self.assertContains(respuesta, 'Ajuste positivo')
        self.assertContains(respuesta, 'Ajuste negativo')
        self.assertContains(respuesta, 'Merma')
        self.assertContains(respuesta, 'Nueva compra')

        # 2. Detalles del lote seleccionado
        self.assertContains(respuesta, self.lote.codigo_lote)
        self.assertContains(respuesta, self.producto.nombre)
        self.assertContains(respuesta, self.producto.codigo)
        self.assertContains(respuesta, str(self.lote.cantidad_inicial))
        self.assertContains(respuesta, str(self.lote.cantidad_actual))

        # 3. Ejemplos de cantidad
        self.assertContains(respuesta, '+2')
        self.assertContains(respuesta, '-3')

    def test_ux_enlace_compras_solo_con_permiso(self):
        """El enlace a Registrar compra solo aparece si el usuario tiene el permiso gestionar_compras."""
        from apps.usuarios.models import Permiso

        # Dueño tiene gestionar_compras
        self.client.force_login(self.dueno)
        res_dueno = self.client.get(f'/inventario/ajuste/?lote={self.lote.pk}')
        self.assertContains(res_dueno, '/compras/nueva/')

        # Usuario con rol personalizado que solo tiene ajustar_inventario
        rol_ajustador = Rol.objects.create(nombre='Ajustador')
        rol_ajustador.permisos.add(Permiso.objects.get(codigo='ajustar_inventario'))
        ajustador = Usuario.objects.create_user('ajustador_test', rol=rol_ajustador)

        self.client.force_login(ajustador)
        res_ajustador = self.client.get(f'/inventario/ajuste/?lote={self.lote.pk}')
        self.assertEqual(res_ajustador.status_code, 200)
        self.assertNotContains(res_ajustador, '/compras/nueva/')

    def test_ux_validacion_formulario_mensajes_claros(self):
        """Verifica mensajes de error descriptivos en el formulario."""
        self.client.force_login(self.dueno)

        # Cantidad cero
        res_cero = self.client.post('/inventario/ajuste/', {
            'lote': self.lote.pk,
            'tipo': 'AJUSTE',
            'cantidad': 0,
            'motivo': 'Prueba conteo',
        })
        self.assertEqual(res_cero.status_code, 422)
        self.assertContains(res_cero, 'distinta de cero', status_code=422)

        # Merma con cantidad positiva
        res_merma_pos = self.client.post('/inventario/ajuste/', {
            'lote': self.lote.pk,
            'tipo': 'MERMA',
            'cantidad': 5,
            'motivo': 'Producto roto',
        })
        self.assertEqual(res_merma_pos.status_code, 422)
        self.assertContains(res_merma_pos, 'Una merma debe retirar unidades', status_code=422)


class IdempotenciaAjustesFase7Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dueno, cls.vendedor, cls.producto, cls.presentacion = preparar()
        cls.lote = lote(cls.producto, 'IDEMPOTENCIA', 10, inicial=20)

    def test_uuid_unico_y_huella_sha256_persistente(self):
        clave = uuid4()
        mov = s.ajustar_inventario(self.dueno, self.lote, 'AJUSTE', 2, '  Conteo físico verificado  ', clave=clave)
        op = OperacionAjusteInventario.objects.get(clave=clave)
        self.assertEqual(op.usuario, self.dueno)
        self.assertEqual(op.lote_id, self.lote.pk)
        self.assertEqual(op.tipo, 'AJUSTE')
        self.assertEqual(len(op.huella), 64)
        self.assertEqual(op.movimiento, mov)
        self.assertIsNotNone(op.auditoria)
        self.assertEqual(op.auditoria.accion, 'AJUSTE_INVENTARIO')

    def test_misma_clave_mismos_datos_recupera_resultado_anterior(self):
        clave = uuid4()
        m1 = s.ajustar_inventario(self.dueno, self.lote, 'AJUSTE', 3, 'Conteo de estante', clave=clave)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_actual, 13)
        self.assertEqual(MovimientoInventario.objects.count(), 1)
        self.assertEqual(LogAuditoria.objects.count(), 1)
        self.assertEqual(OperacionAjusteInventario.objects.count(), 1)

        # Repetición con la misma clave y los mismos datos: no altera stock ni crea nuevos registros
        m2 = s.ajustar_inventario(self.dueno, self.lote, 'AJUSTE', 3, 'Conteo de estante', clave=clave)
        self.assertEqual(m1.pk, m2.pk)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_actual, 13)
        self.assertEqual(MovimientoInventario.objects.count(), 1)
        self.assertEqual(LogAuditoria.objects.count(), 1)
        self.assertEqual(OperacionAjusteInventario.objects.count(), 1)

    def test_misma_clave_datos_distintos_rechaza_solicitud(self):
        clave = uuid4()
        s.ajustar_inventario(self.dueno, self.lote, 'AJUSTE', 2, 'Motivo original', clave=clave)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_actual, 12)

        # Diferente cantidad
        with self.assertRaises(ErrorDeNegocio):
            s.ajustar_inventario(self.dueno, self.lote, 'AJUSTE', 3, 'Motivo original', clave=clave)

        # Diferente motivo
        with self.assertRaises(ErrorDeNegocio):
            s.ajustar_inventario(self.dueno, self.lote, 'AJUSTE', 2, 'Motivo alterado', clave=clave)

        # Diferente tipo
        with self.assertRaises(ErrorDeNegocio):
            s.ajustar_inventario(self.dueno, self.lote, 'MERMA', -2, 'Motivo original', clave=clave)

        # Mismo stock y registros conservados
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_actual, 12)
        self.assertEqual(MovimientoInventario.objects.count(), 1)
        self.assertEqual(OperacionAjusteInventario.objects.count(), 1)

    def test_misma_clave_otro_usuario_rechaza_solicitud(self):
        clave = uuid4()
        s.ajustar_inventario(self.dueno, self.lote, 'AJUSTE', 1, 'Motivo de prueba', clave=clave)
        otro_dueno = Usuario.objects.create_user('otro_dueno', rol=self.dueno.rol)
        with self.assertRaises(ErrorDeNegocio):
            s.ajustar_inventario(otro_dueno, self.lote, 'AJUSTE', 1, 'Motivo de prueba', clave=clave)

    def test_rollback_completo_no_persiste_operacion(self):
        clave = uuid4()
        with self.assertRaises(ErrorDeNegocio):
            # Intentar ajuste que supera cantidad inicial (10 + 15 = 25 > 20)
            s.ajustar_inventario(self.dueno, self.lote, 'AJUSTE', 15, 'Exceso de stock', clave=clave)
        self.assertEqual(OperacionAjusteInventario.objects.filter(clave=clave).count(), 0)
        self.assertEqual(MovimientoInventario.objects.count(), 0)
        self.assertEqual(LogAuditoria.objects.count(), 0)

    def test_admin_operacion_ajuste_solo_lectura(self):
        from django.contrib import admin
        self.assertIn(OperacionAjusteInventario, admin.site._registry)
        admin_op = admin.site._registry[OperacionAjusteInventario]
        request = self.client.request().wsgi_request
        self.assertFalse(admin_op.has_add_permission(request))
        self.assertFalse(admin_op.has_change_permission(request))
        self.assertFalse(admin_op.has_delete_permission(request))

    def test_http_doble_envio_misma_clave_deduplica_en_formulario(self):
        self.client.force_login(self.dueno)
        clave = str(uuid4())
        datos = {
            'lote': self.lote.pk,
            'tipo': 'MERMA',
            'cantidad': -2,
            'motivo': 'Rotura de frascos en almacén',
            'clave': clave,
        }
        # Primer envío exitoso
        res1 = self.client.post('/inventario/ajuste/', datos)
        self.assertEqual(res1.status_code, 302)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_actual, 8)
        self.assertEqual(MovimientoInventario.objects.count(), 1)
        self.assertEqual(OperacionAjusteInventario.objects.count(), 1)

        # Reenvío idéntico (simulando reintento de red o reenvío POST)
        res2 = self.client.post('/inventario/ajuste/', datos)
        self.assertEqual(res2.status_code, 302)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_actual, 8)
        self.assertEqual(MovimientoInventario.objects.count(), 1)
        self.assertEqual(OperacionAjusteInventario.objects.count(), 1)

        # Envío con misma clave pero datos alterados -> 422
        datos_alterados = {**datos, 'cantidad': -4}
        res3 = self.client.post('/inventario/ajuste/', datos_alterados)
        self.assertEqual(res3.status_code, 422)
        self.assertContains(res3, 'La clave ya fue utilizada con otros datos', status_code=422)
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.cantidad_actual, 8)
