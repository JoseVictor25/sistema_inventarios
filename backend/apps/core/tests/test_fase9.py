from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from django.contrib import admin
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied
from django.test import TestCase, Client, RequestFactory
from django.utils import timezone
from apps.auditoria.models import LogAuditoria
from apps.auditoria.services import listar_eventos, registrar_cambio
from apps.auditoria.forms import FiltrosAuditoriaForm
from apps.core.services import datos_inicio, crear_respaldo, consultar_respaldos
from apps.core.respaldos import ErrorRespaldo
from apps.reportes.tests.datos import crear_datos
from apps.usuarios.models import Usuario
from apps.caja.services import abrir_caja


class Fase9Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        datos = crear_datos()
        cls.dueno, cls.vendedor = datos['dueno'], datos['vendedor']
        cls.sin_rol = Usuario.objects.create_user('sin_rol_f9')
        cls.inactivo = Usuario.objects.create_user('inactivo_f9', rol=cls.dueno.rol, is_active=False)
        cls.superusuario = Usuario.objects.create_superuser('super_f9', password='Temporal-Seguro-2026!')

    def test_consulta_orden_paginacion_y_autores_sin_n_mas_uno(self):
        LogAuditoria.objects.all().delete()  # Preparación exclusiva de la base de pruebas.
        for i in range(23):
            registrar_cambio(self.inactivo if i % 2 else None, 'PRUEBA', 'Producto', i + 1, None, {'n': i})
        LogAuditoria.objects.all().update(fecha=timezone.now())
        with self.assertNumQueries(3):  # permiso, COUNT y página con autor incluido
            pagina = listar_eventos(self.dueno)
            self.assertEqual(len(pagina), 20)
            for evento in pagina:
                str(evento.usuario)
        self.assertEqual([e.pk for e in pagina], sorted([e.pk for e in pagina], reverse=True))
        self.assertEqual(len(listar_eventos(self.dueno, {'page': 2})), 3)
        self.assertEqual(listar_eventos(self.dueno, {'usuario': self.inactivo.pk}).paginator.count, 11)

    def test_filtros_fecha_entidad_sin_limite_366(self):
        hoy = timezone.localdate()
        filtros = {'desde': (hoy - timedelta(days=800)).isoformat(), 'hasta': hoy.isoformat(), 'entidad': 'Caja'}
        self.assertEqual(listar_eventos(self.dueno, filtros).paginator.count, 1)
        filtros['entidad'] = 'NoExiste'
        self.assertEqual(listar_eventos(self.dueno, filtros).paginator.count, 0)
        for datos in ({'desde': 'incorrecta'}, {'desde': '2026-02-02', 'hasta': '2026-01-01'}, {'usuario': 999999}, {'page': 0}, {'ruta': 'x'}):
            self.assertFalse(FiltrosAuditoriaForm(datos).is_valid())

    def test_servicios_denegados_antes_de_consultar_o_copiar(self):
        for usuario in (self.vendedor, self.sin_rol, self.inactivo, AnonymousUser()):
            for servicio in (listar_eventos, crear_respaldo, consultar_respaldos):
                with self.subTest(usuario=str(usuario), servicio=servicio.__name__), self.assertRaises(PermissionDenied):
                    servicio(usuario)

    def test_http_roles_metodos_y_no_edicion(self):
        for usuario in (self.dueno, self.superusuario):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get('/auditoria/').status_code, 200)
            self.assertEqual(self.client.post('/auditoria/', {}).status_code, 405)
            self.assertEqual(self.client.get('/sistema/respaldos/crear/').status_code, 405)
            self.assertEqual(self.client.get('/auditoria/?desde=mal').status_code, 422)
        for usuario in (self.vendedor, self.sin_rol):
            self.client.force_login(usuario)
            for url in ('/auditoria/', '/sistema/respaldos/', '/sistema/respaldos/crear/'):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get('/auditoria/').status_code, 302)
        self.client.force_login(self.inactivo)
        self.assertEqual(self.client.get('/auditoria/').status_code, 302)

    def test_auditoria_escapa_json_autor_nulo_y_no_escribe(self):
        registrar_cambio(None, 'PRUEBA', 'Producto', 1, None, {'valor': '<script>alert(1)</script>'})
        cantidad = LogAuditoria.objects.count()
        self.client.force_login(self.dueno)
        respuesta = self.client.get('/auditoria/')
        self.assertContains(respuesta, '&lt;script&gt;')
        self.assertNotContains(respuesta, '<script>alert(1)</script>')
        self.assertEqual(LogAuditoria.objects.count(), cantidad)
        self.assertEqual(respuesta['Cache-Control'], 'private, no-store')

    def test_admin_exige_permiso_tecnico_y_de_negocio(self):
        modelo_admin = admin.site._registry[LogAuditoria]
        request = RequestFactory().get('/admin/')
        tecnico = Permission.objects.get(codename='view_logauditoria')
        self.vendedor.user_permissions.add(tecnico)
        request.user = Usuario.objects.get(pk=self.vendedor.pk)
        self.assertFalse(modelo_admin.has_view_permission(request))
        request.user = self.dueno
        self.assertFalse(modelo_admin.has_view_permission(request))
        self.dueno.user_permissions.add(tecnico)
        request.user = Usuario.objects.get(pk=self.dueno.pk)
        self.assertTrue(modelo_admin.has_view_permission(request))
        for usuario in (request.user, self.superusuario):
            request.user = usuario
            self.assertFalse(modelo_admin.has_add_permission(request))
            self.assertFalse(modelo_admin.has_change_permission(request))
            self.assertFalse(modelo_admin.has_delete_permission(request))

    def test_panel_indicadores_y_propiedad_turno(self):
        propia = abrir_caja(self.vendedor, Decimal('10'), 'Propio', clave=uuid4())
        abrir_caja(self.dueno, Decimal('100'), 'Ajeno', clave=uuid4())
        datos = datos_inicio(self.dueno)
        self.assertEqual(datos['ventas_hoy'], Decimal('38'))
        self.assertEqual(datos['cantidad_ventas_hoy'], 2)
        self.assertEqual(datos['stock_bajo'], 1)
        self.assertEqual(datos['por_vencer'], 1)
        self.assertEqual(datos['vencidos'], 0)
        with patch('apps.core.services.ventas_agrupadas') as ventas:
            datos = datos_inicio(self.vendedor)
            ventas.assert_not_called()
        self.assertNotIn('ventas_hoy', datos)
        self.assertEqual(datos['caja']['id'], propia.pk)
        self.assertNotIn('monto_inicial', datos['caja'])
        self.assertEqual(datos_inicio(self.sin_rol), {'caja': None})
        with self.assertRaises(PermissionDenied):
            datos_inicio(self.inactivo)

    def test_panel_y_menu_segun_permisos(self):
        self.client.force_login(self.dueno)
        self.assertContains(self.client.get('/'), 'Ventas del día')
        self.client.force_login(self.vendedor)
        respuesta = self.client.get('/')
        self.assertNotContains(respuesta, 'Ventas del día')
        self.assertNotContains(respuesta, '/auditoria/')
        self.assertNotContains(respuesta, '/sistema/respaldos/')
        self.assertContains(respuesta, 'Mi turno de caja')

    def test_panel_no_duplica_productos_con_varios_lotes(self):
        from apps.inventario.models import Lote
        lote = Lote.objects.filter(cantidad_actual__gt=0).first()
        Lote.objects.create(producto_id=lote.producto_id, codigo_lote='F9-DUPLICADO', cantidad_actual=1,
                            cantidad_inicial=1, costo_unitario='2', fecha_vencimiento=lote.fecha_vencimiento)
        self.assertEqual(datos_inicio(self.dueno)['por_vencer'], 1)

    def test_limites_fecha_local_auditoria(self):
        from datetime import datetime, time
        hoy = timezone.localdate()
        inicio = timezone.make_aware(datetime.combine(hoy, time.min))
        LogAuditoria.objects.all().delete()
        for instante in (inicio - timedelta(microseconds=1), inicio, inicio + timedelta(days=1) - timedelta(microseconds=1), inicio + timedelta(days=1)):
            evento = registrar_cambio(None, 'PRUEBA', 'Producto', 1, None, None)
            LogAuditoria.objects.filter(pk=evento.pk).update(fecha=instante)
        pagina = listar_eventos(self.dueno, {'desde': hoy.isoformat(), 'hasta': hoy.isoformat()})
        self.assertEqual(pagina.paginator.count, 2)

    def test_respaldo_csrf_rutas_arbitrarias_y_error_controlado(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.dueno)
        with patch('apps.core.services.crear_copia') as copiar:
            self.assertEqual(cliente.post('/sistema/respaldos/crear/').status_code, 403)
            self.client.force_login(self.dueno)
            self.assertEqual(self.client.post('/sistema/respaldos/crear/', {'ruta': 'otra.sqlite3'}).status_code, 422)
            copiar.assert_not_called()
        with patch('apps.core.services.crear_copia', side_effect=ErrorRespaldo('Fallo controlado')):
            respuesta = self.client.post('/sistema/respaldos/crear/', follow=True)
            self.assertContains(respuesta, 'Fallo controlado')
