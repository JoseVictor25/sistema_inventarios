"""Formularios y consultas de caja, incluidas regresiones de cierres antiguos."""
from decimal import Decimal
from io import StringIO
from uuid import uuid4

from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.caja.forms import AbrirCajaForm, CerrarCajaForm, MovimientoCajaForm
from apps.caja.models import Caja, MovimientoCaja
from apps.caja.services import calcular_resumen_caja, listar_cierres, obtener_caja, puede_cerrar_ajena
from apps.usuarios.models import Permiso, Rol, Usuario
from apps.ventas.models import MetodoPago, Pago, Venta


class FormulariosCajaTests(SimpleTestCase):
    def test_apertura_cero_y_turno_opcional(self):
        form = AbrirCajaForm({"clave": uuid4(), "monto_inicial": "0", "turno": "   "})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["turno"], "")
        self.assertIsInstance(form.cleaned_data["monto_inicial"], Decimal)

    def test_apertura_limites_y_clave(self):
        for cambios in ({"clave": ""}, {"monto_inicial": "-1"}, {"monto_inicial": "NaN"},
                        {"monto_inicial": "1.001"}, {"monto_inicial": "10000000000"}, {"turno": "x" * 31}):
            with self.subTest(cambios=cambios):
                self.assertFalse(AbrirCajaForm({"clave": uuid4(), "monto_inicial": "10", **cambios}).is_valid())

    def test_movimiento_valido_y_concepto_limpio(self):
        for tipo in ("INGRESO", "EGRESO"):
            form = MovimientoCajaForm({"clave": uuid4(), "caja_id": 1, "tipo": tipo, "monto": "0.01", "concepto": "  Cambio  "})
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["concepto"], "Cambio")

    def test_movimiento_invalido_y_turno_obligatorio(self):
        datos = {"clave": uuid4(), "caja_id": 1, "tipo": "INGRESO", "monto": "1", "concepto": "Cambio"}
        for cambios in ({"caja_id": ""}, {"caja_id": 0}, {"monto": "0"}, {"monto": "-1"},
                        {"tipo": "OTRO"}, {"concepto": " "}, {"concepto": "x" * 121}):
            self.assertFalse(MovimientoCajaForm({**datos, **cambios}).is_valid())

    def test_cierre_identifica_turno_y_admite_cero(self):
        datos = {"clave": uuid4(), "caja_id": 42, "monto_contado": "0"}
        self.assertTrue(CerrarCajaForm(datos).is_valid())
        for cambios in ({"caja_id": ""}, {"monto_contado": ""}, {"monto_contado": "-1"}):
            self.assertFalse(CerrarCajaForm({**datos, **cambios}).is_valid())

    def test_campos_manipulados_rechazados(self):
        for campo in ("usuario", "cerrada_por", "fecha_cierre", "estado", "esperado", "diferencia"):
            form = CerrarCajaForm({"clave": uuid4(), "caja_id": 1, "monto_contado": "0", campo: "999"})
            self.assertFalse(form.is_valid())


class ConsultasCajaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos_iniciales", stdout=StringIO())
        cls.dueno = Usuario.objects.create_user("dueno5", rol=Rol.objects.get(nombre="Dueño"))
        cls.vendedor = Usuario.objects.create_user("vendedor5", rol=Rol.objects.get(nombre="Vendedor"))
        cls.otro = Usuario.objects.create_user("otro5", rol=cls.vendedor.rol)
        cls.superusuario = Usuario.objects.create_superuser("super5", password=None)
        rol_historial = Rol.objects.create(nombre="Consulta de prueba")
        rol_historial.permisos.add(Permiso.objects.get(codigo="ver_historial_caja"))
        cls.lector = Usuario.objects.create_user("lector5", rol=rol_historial)
        cls.caja = Caja.objects.create(usuario=cls.vendedor, monto_inicial=Decimal("100"))

    def test_cierre_ajeno_no_se_concede_por_historial(self):
        self.assertTrue(puede_cerrar_ajena(self.dueno))
        self.assertTrue(puede_cerrar_ajena(self.superusuario))
        for usuario in (self.vendedor, self.lector, AnonymousUser()):
            self.assertFalse(puede_cerrar_ajena(usuario))
        self.dueno.is_active = False
        self.assertFalse(puede_cerrar_ajena(self.dueno))

    def test_consulta_propia_y_denegacion_ajena(self):
        self.assertEqual(obtener_caja(self.vendedor, self.caja.pk), self.caja)
        for usuario in (self.otro, self.lector, AnonymousUser()):
            with self.assertRaises(PermissionDenied):
                obtener_caja(usuario, self.caja.pk)

    def test_pagos_mixtos_y_movimientos_sin_duplicar_sumas(self):
        venta = Venta.objects.create(caja=self.caja, usuario=self.vendedor, total=Decimal("90"))
        for nombre, monto in (("Efectivo", "40"), ("QR", "30"), ("Transferencia", "20")):
            Pago.objects.create(venta=venta, metodo=MetodoPago.objects.get(nombre=nombre), monto=Decimal(monto))
        for tipo, monto in (("INGRESO", "10"), ("INGRESO", "5"), ("EGRESO", "7")):
            MovimientoCaja.objects.create(caja=self.caja, usuario=self.vendedor, tipo=tipo, monto=Decimal(monto), concepto="Prueba")
        MetodoPago.objects.filter(nombre="QR").update(activo=False)
        resumen = calcular_resumen_caja(self.caja, usuario=self.vendedor)
        self.assertEqual(resumen["esperado"], Decimal("148"))
        self.assertEqual(resumen["ventas_efectivo"], Decimal("40"))
        self.assertEqual(sum(p["monto"] for p in resumen["otros_metodos"]), Decimal("50"))
        self.assertEqual(resumen["esperado"], self.caja.monto_esperado())
        self.assertIsNone(resumen["diferencia"])

    def test_cierre_antiguo_recalculado_y_tres_resultados(self):
        self.caja.estado = "CERRADA"
        self.caja.fecha_cierre = timezone.now()
        for contado, resultado in (("100", "CUADRA"), ("101", "SOBRA"), ("99", "FALTA")):
            self.caja.monto_contado = Decimal(contado)
            self.caja.save()
            resumen = calcular_resumen_caja(self.caja, usuario=self.vendedor)
            self.assertTrue(resumen["recalculado"])
            self.assertEqual(resumen["resultado"], resultado)
        self.assertFalse(LogAuditoria.objects.exists())

    def test_resumen_guardado_se_conserva_sin_recalcular(self):
        self.caja.estado = "CERRADA"
        self.caja.monto_contado = Decimal("100")
        self.caja.fecha_cierre = timezone.now()
        self.caja.cerrada_por = self.dueno
        self.caja.save()
        resumen = calcular_resumen_caja(self.caja, usuario=self.dueno)
        resumen = {k: format(v, ".2f") if isinstance(v, Decimal) else v for k, v in resumen.items()}
        LogAuditoria.objects.create(usuario=self.dueno, accion="CIERRE_CAJA", entidad="Caja", entidad_id=self.caja.pk, valor_nuevo=resumen)
        # Solo fixture: simular una fuente posterior distinta, sin alterar el log.
        Caja.objects.filter(pk=self.caja.pk).update(monto_inicial=Decimal("200"))
        guardado = calcular_resumen_caja(self.caja, usuario=self.dueno)
        self.assertFalse(guardado["recalculado"])
        self.assertEqual(guardado["esperado"], Decimal("100"))
        self.assertEqual(guardado["cerrado_por_id"], self.dueno.pk)

    def test_historial_paginado_solo_cerradas_y_permiso(self):
        for _ in range(21):
            Caja.objects.create(usuario=self.otro, estado="CERRADA", monto_inicial=Decimal("0"),
                                monto_contado=Decimal("0"), fecha_cierre=timezone.now())
        self.assertEqual(len(listar_cierres(self.lector)), 20)
        self.assertEqual(len(listar_cierres(self.dueno, 2)), 1)
        with self.assertRaises(PermissionDenied):
            listar_cierres(self.vendedor)

    def test_admin_abierta_solo_consulta_e_inlines_protegidos(self):
        self.client.force_login(self.superusuario)
        movimiento = MovimientoCaja.objects.create(caja=self.caja, usuario=self.vendedor, tipo="INGRESO", monto=Decimal("1"), concepto="Prueba")
        request = RequestFactory().get("/admin/")
        request.user = self.superusuario
        for obj in (self.caja, movimiento):
            prefijo = f"admin:caja_{obj._meta.model_name}"
            self.assertEqual(self.client.get(reverse(prefijo + "_change", args=[obj.pk])).status_code, 200)
            antes = type(obj).objects.values().get(pk=obj.pk)
            for accion in ("add", "change", "delete"):
                url = reverse(prefijo + "_" + accion, args=[] if accion == "add" else [obj.pk])
                self.assertEqual(self.client.post(url, {"estado": "CERRADA"}).status_code, 403)
            self.assertEqual(type(obj).objects.values().get(pk=obj.pk), antes)
            administrador = admin.site._registry[type(obj)]
            self.assertNotIn("delete_selected", administrador.get_actions(request))
            for inline in administrador.get_inline_instances(request, obj):
                self.assertFalse(inline.has_add_permission(request, obj))
                self.assertFalse(inline.has_change_permission(request, obj))
                self.assertFalse(inline.has_delete_permission(request, obj))
