"""Regresiones financieras, autorización, HTTP e idempotencia de caja."""
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase

from apps.auditoria.models import LogAuditoria
from apps.caja.models import Caja, MovimientoCaja, OperacionCaja
from apps.caja import services as s
from apps.core.exceptions import ErrorDeNegocio
from apps.usuarios.models import Usuario, Rol, Permiso
from apps.ventas.models import Venta, Pago, MetodoPago


def usuarios():
    call_command("cargar_datos_iniciales", stdout=StringIO())
    return (Usuario.objects.create_user("dueno", rol=Rol.objects.get(nombre="Dueño")),
            Usuario.objects.create_user("vendedor", rol=Rol.objects.get(nombre="Vendedor")))


class OperacionesCajaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dueno, cls.vendedor = usuarios()
        cls.otro = Usuario.objects.create_user("otro", rol=cls.vendedor.rol)
        cls.superusuario = Usuario.objects.create_superuser("super", password=None)
        cls.sin_rol = Usuario.objects.create_user("sinrol")

    def abrir(self, usuario=None, monto="100", clave=None):
        return s.abrir_caja(usuario or self.vendedor, monto, clave=clave or uuid4())

    def movimiento(self, caja, clave=None, **datos):
        return s.registrar_movimiento_caja(self.vendedor, caja.pk, **{
            "tipo": "INGRESO", "monto": "10", "concepto": "Cambio", **datos}, clave=clave or uuid4())

    def test_apertura_auditable_y_reenvio_normalizado(self):
        clave = uuid4()
        caja = s.abrir_caja(self.vendedor, "100", " Mañana ", clave=clave)
        repetida = s.abrir_caja(self.vendedor, Decimal("100.00"), "Mañana", clave=clave)
        self.assertEqual(caja.pk, repetida.pk)
        self.assertEqual(Caja.objects.count(), 1)
        self.assertEqual(OperacionCaja.objects.count(), 1)
        self.assertEqual(caja.creado_por, self.vendedor)
        self.assertEqual(len(OperacionCaja.objects.get().huella), 64)

    def test_apertura_duplicada_otra_clave_y_datos_distintos(self):
        clave = uuid4()
        self.abrir(clave=clave)
        for otra, monto in ((uuid4(), "100"), (clave, "101")):
            with self.assertRaises(ErrorDeNegocio):
                self.abrir(clave=otra, monto=monto)
        self.assertEqual(OperacionCaja.objects.count(), 1)

    def test_movimientos_iguales_distintas_claves_y_reenvio(self):
        caja = self.abrir()
        clave = uuid4()
        primero = self.movimiento(caja, clave)
        self.assertEqual(self.movimiento(caja, clave).pk, primero.pk)
        self.movimiento(caja)
        self.assertEqual(MovimientoCaja.objects.count(), 2)
        self.assertEqual(s.calcular_resumen_caja(caja, usuario=self.vendedor)["esperado"], Decimal("120"))

    def test_huella_incluye_usuario_accion_turno_y_datos(self):
        caja = self.abrir()
        clave = uuid4()
        self.movimiento(caja, clave)
        for cambios in ({"monto": "11"}, {"tipo": "EGRESO"}, {"concepto": "Otro"}):
            with self.assertRaises(ErrorDeNegocio):
                self.movimiento(caja, clave, **cambios)
        with self.assertRaises(ErrorDeNegocio):
            s.registrar_movimiento_caja(self.dueno, caja.pk, "INGRESO", "10", "Cambio", clave=clave)
        with self.assertRaises(ErrorDeNegocio):
            s.cerrar_caja(self.vendedor, caja.pk, "10", clave=clave)
        otra = self.abrir(usuario=self.otro)
        with self.assertRaises(ErrorDeNegocio):
            self.movimiento(otra, clave)

    def test_validaciones_servicio_no_dejan_reservas(self):
        for monto in ("-1", "NaN", "Infinity", "1.001", "10000000000"):
            with self.assertRaises(ErrorDeNegocio):
                self.abrir(monto=monto)
        caja = self.abrir()
        for datos in ({"monto": "0"}, {"monto": "-1"}, {"tipo": "VENTA"}, {"concepto": " "}):
            with self.assertRaises(ErrorDeNegocio):
                self.movimiento(caja, **datos)
        with self.assertRaises(ErrorDeNegocio):
            s.cerrar_caja(self.vendedor, caja.pk, "-1", clave=uuid4())
        self.assertEqual(OperacionCaja.objects.count(), 1)
        self.assertEqual(MovimientoCaja.objects.count(), 0)

    def test_rollback_apertura_movimiento_y_auditoria(self):
        with patch.object(Caja, "save", side_effect=ValidationError("Fallo simulado")):
            with self.assertRaises(ErrorDeNegocio):
                self.abrir()
        self.assertFalse(OperacionCaja.objects.exists())
        caja = self.abrir()
        with patch.object(MovimientoCaja, "save", side_effect=ValidationError("Fallo simulado")):
            with self.assertRaises(ErrorDeNegocio):
                self.movimiento(caja)
        with patch.object(s, "registrar_cambio", side_effect=ValidationError("Fallo simulado")):
            with self.assertRaises(ErrorDeNegocio):
                s.cerrar_caja(self.vendedor, caja.pk, "100", clave=uuid4())
        caja.refresh_from_db()
        self.assertEqual(caja.estado, "ABIERTA")
        self.assertIsNone(caja.fecha_cierre)
        self.assertFalse(LogAuditoria.objects.exists())
        self.assertFalse(MovimientoCaja.objects.exists())
        self.assertEqual(OperacionCaja.objects.count(), 1)

    def test_cierre_cuadra_sobra_falta_y_reenvio(self):
        for contado, resultado in (("100", "CUADRA"), ("101", "SOBRA"), ("99", "FALTA")):
            caja = self.abrir()
            clave = uuid4()
            resumen = s.cerrar_caja(self.vendedor, caja.pk, contado, clave=clave)
            self.assertEqual(resumen["resultado"], resultado)
            self.assertFalse(resumen["recalculado"])
            self.assertEqual(s.cerrar_caja(self.vendedor, caja.pk, contado, clave=clave), resumen)
            with self.assertRaises(ErrorDeNegocio):
                s.cerrar_caja(self.vendedor, caja.pk, contado, clave=uuid4())
            self.assertEqual(LogAuditoria.objects.filter(entidad_id=caja.pk).count(), 1)

    def test_pagos_mixtos_auditoria_y_resumen_inmutable(self):
        caja = self.abrir()
        venta = Venta.objects.create(caja=caja, usuario=self.vendedor, total=Decimal("90"))
        for nombre, monto in (("Efectivo", "40"), ("QR", "30"), ("Transferencia", "20")):
            Pago.objects.create(venta=venta, metodo=MetodoPago.objects.get(nombre=nombre), monto=Decimal(monto))
        self.movimiento(caja)
        self.movimiento(caja, tipo="EGRESO", monto="5")
        resumen = s.cerrar_caja(self.dueno, caja.pk, "145", clave=uuid4())
        registro = LogAuditoria.objects.get(accion="CIERRE_CAJA")
        self.assertEqual(registro.usuario, self.dueno)
        self.assertEqual(resumen["propietario_id"], self.vendedor.pk)
        self.assertEqual(resumen["cerrado_por_id"], self.dueno.pk)
        self.assertEqual(resumen["esperado"], Decimal("145"))
        self.assertEqual(len(resumen["pagos_por_metodo"]), 3)
        for campo in ("monto_inicial", "ventas_efectivo", "otros_metodos", "ingresos", "egresos", "esperado", "contado", "diferencia", "fecha_cierre"):
            self.assertIn(campo, registro.valor_nuevo)
        # Simula cambios externos únicamente en fixtures: el cierre no se recalcula.
        MetodoPago.objects.filter(nombre="QR").update(nombre="QR nuevo", es_efectivo=True)
        self.assertEqual(s.calcular_resumen_caja(caja, usuario=self.dueno), resumen)

    def test_cierre_ajeno_solo_dueno_o_super_no_historial(self):
        caja = self.abrir()
        rol = Rol.objects.create(nombre="Lector temporal")
        rol.permisos.add(*Permiso.objects.filter(codigo__in=["ver_historial_caja", "gestionar_caja"]))
        lector = Usuario.objects.create_user("lector", rol=rol)
        for actor in (self.otro, lector):
            with self.assertRaises(PermissionDenied):
                s.cerrar_caja(actor, caja.pk, "100", clave=uuid4())
        self.assertEqual(s.cerrar_caja(self.superusuario, caja.pk, "100", clave=uuid4())["cerrado_por_id"], self.superusuario.pk)

    def test_movimiento_ajeno_incluso_dueno_denegado(self):
        caja = self.abrir()
        for actor in (self.otro, self.dueno, self.superusuario):
            with self.assertRaises(PermissionDenied):
                s.registrar_movimiento_caja(actor, caja.pk, "INGRESO", "1", "Ajeno", clave=uuid4())
        self.assertEqual(OperacionCaja.objects.count(), 1)

    def test_inactivos_anonimos_sin_rol_denegados_en_servicios(self):
        inactivo = Usuario.objects.create_user("inactivo", is_active=False, rol=self.dueno.rol)
        caja = self.abrir()
        for actor in (inactivo, AnonymousUser(), self.sin_rol):
            for funcion, args in ((s.abrir_caja, ("0",)), (s.cerrar_caja, (caja.pk, "0")),
                                  (s.registrar_movimiento_caja, (caja.pk, "INGRESO", "1", "Cambio"))):
                with self.assertRaises(PermissionDenied):
                    funcion(actor, *args, clave=uuid4())

    def test_formulario_antiguo_no_toca_nuevo_turno(self):
        caja = self.abrir()
        clave = uuid4()
        movimiento = self.movimiento(caja, clave)
        s.cerrar_caja(self.vendedor, caja.pk, "110", clave=uuid4())
        nueva = self.abrir()
        self.assertEqual(self.movimiento(caja, clave).pk, movimiento.pk)
        with self.assertRaises(ErrorDeNegocio):
            self.movimiento(caja)
        with self.assertRaises(ErrorDeNegocio):
            s.cerrar_caja(self.vendedor, caja.pk, "110", clave=uuid4())
        self.assertFalse(nueva.movimientos.exists())
        self.assertEqual(Caja.objects.get(pk=nueva.pk).estado, "ABIERTA")

    def test_admin_operacion_solo_consulta(self):
        request = RequestFactory().get("/admin/")
        request.user = self.superusuario
        administrador = admin.site._registry[OperacionCaja]
        self.assertFalse(administrador.has_add_permission(request))
        self.assertFalse(administrador.has_change_permission(request))
        self.assertFalse(administrador.has_delete_permission(request))


class PantallasCajaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dueno, cls.vendedor = usuarios()

    def test_recorrido_http_y_htmx_con_reenvios(self):
        self.client.force_login(self.vendedor)
        self.assertContains(self.client.get("/caja/"), "Abrir caja")
        datos = {"clave": uuid4(), "monto_inicial": "100", "turno": "Tarde"}
        self.assertEqual(self.client.post("/caja/abrir/", datos).status_code, 302)
        self.assertEqual(self.client.post("/caja/abrir/", datos).status_code, 302)
        caja = Caja.objects.get()
        mov = {"clave": uuid4(), "caja_id": caja.pk, "tipo": "INGRESO", "monto": "5", "concepto": "Cambio"}
        for _ in range(2):
            respuesta = self.client.post("/caja/movimientos/nuevo/", mov, HTTP_HX_REQUEST="true")
            self.assertContains(respuesta, 'hx-swap-oob="outerHTML"')
            self.assertNotContains(respuesta, "<!DOCTYPE")
        self.assertEqual(MovimientoCaja.objects.count(), 1)
        respuesta = self.client.post("/caja/cerrar/", {"clave": uuid4(), "caja_id": caja.pk, "monto_contado": "105"})
        self.assertContains(respuesta, "CUADRA")
        self.assertNotContains(respuesta, "Cerrar caja definitivamente")
        self.client.force_login(self.dueno)
        self.assertContains(self.client.get("/caja/historial/"), "CUADRA")

    def test_errores_validacion_y_campos_manipulados(self):
        self.client.force_login(self.vendedor)
        for extra in ({"usuario": self.dueno.pk}, {"estado": "CERRADA"}, {"monto_inicial": "-1"}):
            respuesta = self.client.post("/caja/abrir/", {"clave": uuid4(), "monto_inicial": "0", **extra})
            self.assertEqual(respuesta.status_code, 422)
        self.assertFalse(Caja.objects.exists())
        caja = s.abrir_caja(self.vendedor, "0", clave=uuid4())
        respuesta = self.client.post("/caja/movimientos/nuevo/", {"clave": uuid4(), "caja_id": caja.pk,
                         "tipo": "INGRESO", "monto": "0", "concepto": "x"}, HTTP_HX_REQUEST="true")
        self.assertEqual(respuesta.status_code, 422)
        self.assertFalse(MovimientoCaja.objects.exists())

    def test_verbos_csrf_y_anonimos(self):
        rutas = ("/caja/abrir/", "/caja/movimientos/nuevo/", "/caja/cerrar/")
        for ruta in ("/caja/", "/caja/historial/", *rutas):
            self.assertEqual(self.client.get(ruta).status_code, 302)
            self.assertEqual(self.client.post(ruta, {}).status_code, 302)
        self.client.force_login(self.dueno)
        for ruta in rutas:
            self.assertEqual(self.client.get(ruta).status_code, 405)
        estricto = Client(enforce_csrf_checks=True)
        estricto.force_login(self.dueno)
        for ruta in rutas:
            self.assertEqual(estricto.post(ruta, {}).status_code, 403)

    def test_permisos_rutas_y_menu(self):
        self.client.force_login(self.vendedor)
        respuesta = self.client.get("/caja/")
        self.assertContains(respuesta, 'href="/caja/"')
        self.assertNotContains(respuesta, 'href="/caja/historial/"')
        self.assertEqual(self.client.get("/caja/historial/").status_code, 403)
        ajena = s.abrir_caja(self.dueno, "1", clave=uuid4())
        self.assertEqual(self.client.get(f"/caja/?caja_id={ajena.pk}").status_code, 403)
        self.assertEqual(self.client.post("/caja/cerrar/", {"clave": uuid4(), "caja_id": ajena.pk, "monto_contado": "1"}).status_code, 403)
        self.assertEqual(self.client.get("/caja/?caja_id=no").status_code, 404)
        self.assertEqual(self.client.get("/caja/?caja_id=999999").status_code, 404)

    def test_sin_rol_e_inactivo_en_http(self):
        for activo in (True, False):
            actor = Usuario.objects.create_user(f"actor{activo}", is_active=activo)
            self.client.force_login(actor)
            esperado = 403 if activo else 302
            self.assertEqual(self.client.get("/caja/").status_code, esperado)
            self.assertEqual(self.client.post("/caja/abrir/", {}).status_code, esperado)
