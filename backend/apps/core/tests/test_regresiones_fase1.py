"""Regresiones de integridad y protección del administrador de fase 1."""
from decimal import Decimal
from io import StringIO

from django.apps import apps
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.caja.forms import MovimientoCajaAdminForm
from apps.caja.models import Caja, MovimientoCaja
from apps.catalogo.models import Categoria, Presentacion, Producto
from apps.compras.models import Compra, DetalleCompra, Proveedor
from apps.inventario.models import Lote, MovimientoInventario
from apps.usuarios.models import Usuario, Permiso, Rol
from apps.ventas.models import DetalleVenta, DetalleVentaLote, MetodoPago, Pago, Venta


def crear_historial():
    """Crea relaciones completas exclusivamente en la base de pruebas."""
    usuario = Usuario.objects.create_superuser(username="regresion", password=None)
    categoria = Categoria.objects.create(nombre="Prueba")
    producto = Producto.objects.create(codigo="PRUEBA", nombre="Prueba", categoria=categoria)
    presentacion = Presentacion.objects.create(
        producto=producto, nombre="Unidad", unidades_equivalentes=1, precio_venta=Decimal("2")
    )
    proveedor = Proveedor.objects.create(nombre="Prueba", tipo="EMPRESA")
    compra = Compra.objects.create(proveedor=proveedor, usuario=usuario, total=Decimal("3"))
    detalle_compra = DetalleCompra.objects.create(
        compra=compra, producto=producto, cantidad_unidades=3,
        costo_unitario=Decimal("1"), subtotal=Decimal("3")
    )
    lote = Lote.objects.create(
        producto=producto, detalle_compra=detalle_compra, codigo_lote="PRUEBA",
        cantidad_inicial=3, cantidad_actual=2, costo_unitario=Decimal("1")
    )
    caja = Caja.objects.create(
        usuario=usuario, monto_inicial=Decimal("0"), estado="CERRADA",
        monto_contado=Decimal("2"), fecha_cierre=timezone.now(), cerrada_por=usuario
    )
    venta = Venta.objects.create(caja=caja, usuario=usuario, total=Decimal("2"))
    detalle_venta = DetalleVenta.objects.create(
        venta=venta, presentacion=presentacion, cantidad_presentaciones=1,
        unidades_totales=1, precio_aplicado=Decimal("2"), subtotal=Decimal("2")
    )
    salida = DetalleVentaLote.objects.create(detalle_venta=detalle_venta, lote=lote, cantidad_unidades=1)
    metodo = MetodoPago.objects.create(nombre="Prueba efectivo", es_efectivo=True)
    pago = Pago.objects.create(venta=venta, metodo=metodo, monto=Decimal("2"))
    movimiento = MovimientoInventario.objects.create(lote=lote, usuario=usuario, tipo="SALIDA", cantidad=-1)
    movimiento_caja = MovimientoCaja.objects.create(
        caja=caja, usuario=usuario, tipo="INGRESO", monto=Decimal("1"), concepto="Prueba"
    )
    return locals()


class IntegridadMonetariaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.datos = crear_historial()

    def casos(self):
        return [(self.datos[nombre], campo) for nombre, campo in [
            ("presentacion", "precio_venta"), ("compra", "total"),
            ("detalle_compra", "costo_unitario"), ("detalle_compra", "subtotal"),
            ("lote", "costo_unitario"), ("detalle_venta", "precio_aplicado"),
            ("detalle_venta", "subtotal"), ("caja", "monto_contado"),
        ]]

    def test_modelo_rechaza_negativos_sin_depender_de_constraints(self):
        for objeto, campo in self.casos():
            with self.subTest(modelo=objeto._meta.label, campo=campo):
                setattr(objeto, campo, Decimal("-0.01"))
                with self.assertRaises(ValidationError) as error:
                    objeto.full_clean(validate_constraints=False)
                self.assertIn(campo, error.exception.message_dict)
                objeto.refresh_from_db()

    def test_bd_rechaza_negativos_sin_ejecutar_validadores(self):
        for objeto, campo in self.casos():
            with self.subTest(modelo=objeto._meta.label, campo=campo):
                anterior = getattr(objeto, campo)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    type(objeto).objects.filter(pk=objeto.pk).update(**{campo: Decimal("-0.01")})
                objeto.refresh_from_db()
                self.assertEqual(getattr(objeto, campo), anterior)

    def test_cero_permitido_en_los_ocho_campos(self):
        for objeto, campo in self.casos():
            with self.subTest(modelo=objeto._meta.label, campo=campo):
                setattr(objeto, campo, Decimal("0"))
                objeto.full_clean()
                objeto.save(update_fields=[campo])
                objeto.refresh_from_db()
                self.assertEqual(getattr(objeto, campo), Decimal("0"))

    def test_contado_puede_ser_nulo_y_diferencia_negativa(self):
        caja = self.datos["caja"]
        caja.monto_contado = None
        caja.full_clean()
        caja.save(update_fields=["monto_contado"])
        self.assertIsNone(caja.diferencia())
        caja.monto_contado = Decimal("0")
        self.assertLess(caja.diferencia(), 0)


class ProteccionAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.datos = crear_historial()

    def setUp(self):
        self.client.force_login(self.datos["usuario"])
        self.request = RequestFactory().get("/admin/")
        self.request.user = self.datos["usuario"]

    def protegidos(self):
        return [self.datos[n] for n in (
            "compra", "detalle_compra", "venta", "detalle_venta", "salida", "pago",
            "lote", "movimiento", "caja", "movimiento_caja",
        )]

    def url(self, obj, accion, con_pk=True):
        return reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_{accion}",
                       args=[obj.pk] if con_pk else None)

    def test_consulta_permitida_y_post_edicion_borrado_denegados(self):
        for obj in self.protegidos():
            with self.subTest(modelo=obj._meta.label):
                antes = type(obj).objects.values().get(pk=obj.pk)
                self.assertEqual(self.client.get(self.url(obj, "change")).status_code, 200)
                for accion in ("change", "delete"):
                    respuesta = self.client.post(self.url(obj, accion), {"post": "yes", "estado": "ABIERTA"})
                    self.assertEqual(respuesta.status_code, 403)
                self.assertEqual(type(obj).objects.values().get(pk=obj.pk), antes)

    def test_altas_aisladas_de_historial_denegadas(self):
        for obj in self.protegidos():
            with self.subTest(modelo=obj._meta.label):
                self.assertEqual(self.client.post(self.url(obj, "add", False), {}).status_code, 403)

    def test_borrado_masivo_no_disponible(self):
        for obj in self.protegidos():
            with self.subTest(modelo=obj._meta.label):
                self.assertNotIn("delete_selected", admin.site._registry[type(obj)].get_actions(self.request))
                self.client.post(self.url(obj, "changelist", False), {
                    "action": "delete_selected", "_selected_action": obj.pk, "post": "yes"
                })
                self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())

    def test_inlines_historicos_sin_altas_cambios_ni_bajas(self):
        for nombre in ("compra", "venta", "caja"):
            obj = self.datos[nombre]
            for inline in admin.site._registry[type(obj)].get_inline_instances(self.request, obj):
                with self.subTest(inline=type(inline).__name__):
                    self.assertFalse(inline.has_add_permission(self.request, obj))
                    self.assertFalse(inline.has_change_permission(self.request, obj))
                    self.assertFalse(inline.has_delete_permission(self.request, obj))

    def test_movimiento_no_se_puede_agregar_a_caja_cerrada(self):
        obj = self.datos["movimiento_caja"]
        cantidad = MovimientoCaja.objects.count()
        respuesta = self.client.post(self.url(obj, "add", False), {
            "caja": self.datos["caja"].pk, "usuario": self.datos["usuario"].pk,
            "tipo": "INGRESO", "monto": "1.00", "concepto": "No permitido",
            "fecha_0": "2026-10-24", "fecha_1": "10:00:00",
        })
        # Fase 5 autorizada: toda alta administrativa se deniega antes del formulario.
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(MovimientoCaja.objects.count(), cantidad)

    def test_movimientos_abiertos_validos_sin_traslado_a_cerrada(self):
        abierta = Caja.objects.create(usuario=self.datos["usuario"], monto_inicial=Decimal("0"))
        datos = {"caja": abierta.pk, "usuario": self.datos["usuario"].pk,
                 "tipo": "INGRESO", "monto": "1.00", "concepto": "Prueba", "fecha": timezone.now()}
        form = MovimientoCajaAdminForm(data=datos)
        self.assertTrue(form.is_valid(), form.errors)
        mov = form.save()
        # Se conserva la validación heredada, pero Admin ya no permite escrituras.
        self.assertFalse(admin.site._registry[Caja].has_change_permission(self.request, abierta))
        self.assertFalse(admin.site._registry[MovimientoCaja].has_change_permission(self.request, mov))
        datos["caja"] = self.datos["caja"].pk
        self.assertFalse(MovimientoCajaAdminForm(data=datos, instance=mov).is_valid())
        datos["caja"] = abierta.pk
        self.assertFalse(MovimientoCajaAdminForm(
            data=datos, instance=self.datos["movimiento_caja"]
        ).is_valid())


class OrdenYCargaTests(TestCase):
    def test_todos_los_modelos_del_dominio_tienen_orden(self):
        for model in apps.get_models():
            if model.__module__.startswith("apps."):
                with self.subTest(modelo=model._meta.label):
                    self.assertTrue(model.objects.all().ordered)
        self.assertEqual(Usuario._meta.ordering, ["username"])
        for model in (DetalleCompra, DetalleVenta, DetalleVentaLote, Pago):
            self.assertEqual(model._meta.ordering, ["pk"])

    def test_carga_repetida_preserva_datos_y_relaciones(self):
        modelos = (Permiso, Rol, Rol.permisos.through, MetodoPago)
        call_command("cargar_datos_iniciales", stdout=StringIO())
        antes = {m: list(m.objects.order_by("pk").values()) for m in modelos}
        call_command("cargar_datos_iniciales", stdout=StringIO())
        self.assertEqual(antes, {m: list(m.objects.order_by("pk").values()) for m in modelos})


class PreservacionMigracionesTests(TransactionTestCase):
    """Ejercita la actualización con historial no vacío en la base del test runner."""

    def test_actualizacion_conserva_todos_los_registros(self):
        anteriores = {
            "caja": "0001_initial", "catalogo": "0001_initial",
            "compras": "0001_initial", "inventario": "0001_initial",
            "usuarios": "0002_permiso_alter_usuario_options_rol_usuario_rol",
            "ventas": "0001_initial",
        }
        executor = MigrationExecutor(connection)
        finales = executor.loader.graph.leaf_nodes()
        iniciales = [(app, anteriores.get(app, nombre)) for app, nombre in finales]

        def registros():
            with connection.cursor() as cursor:
                tablas = connection.introspection.table_names(cursor)
                resultado = {}
                for tabla in tablas:
                    if tabla != "django_migrations":
                        cursor.execute(f"SELECT * FROM {connection.ops.quote_name(tabla)}")
                        resultado[tabla] = sorted(cursor.fetchall(), key=repr)
                return resultado

        try:
            executor.migrate(iniciales)
            crear_historial()
            call_command("cargar_datos_iniciales", stdout=StringIO())
            antes = registros()
            MigrationExecutor(connection).migrate(finales)
            despues = registros()
            self.assertEqual({tabla: despues[tabla] for tabla in antes}, antes)
            self.assertEqual(set(despues) - set(antes), {"caja_operacioncaja", "ventas_operacionventa"})
            self.assertEqual(despues["caja_operacioncaja"], [])
            self.assertEqual(despues["ventas_operacionventa"], [])
            self.assertEqual(Usuario.objects.filter(is_superuser=True).count(), 1)
            self.assertEqual(Pago.objects.count(), 1)
            self.assertEqual(Permiso.objects.count(), 12)
            self.assertEqual(Rol.objects.count(), 2)
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA integrity_check")
                self.assertEqual(cursor.fetchone()[0], "ok")
                cursor.execute("PRAGMA foreign_key_check")
                self.assertEqual(cursor.fetchall(), [])
        finally:
            # Restituye exclusivamente el esquema de la base temporal de pruebas.
            MigrationExecutor(connection).migrate(finales)
