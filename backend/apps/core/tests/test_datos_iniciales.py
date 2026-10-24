"""Pruebas para el comando de gestión cargar_datos_iniciales."""
from django.core.management import call_command
from django.test import TestCase

from apps.usuarios.models import Permiso, Rol
from apps.ventas.models import MetodoPago


class CargarDatosInicialesTest(TestCase):
    def test_carga_inicial_y_permisos_matriz(self):
        # Ejecutar por primera vez
        call_command("cargar_datos_iniciales")

        # 12 permisos esperados según especificación §10
        self.assertEqual(Permiso.objects.count(), 12)
        codigos_esperados = {
            "vender",
            "gestionar_caja",
            "ver_stock",
            "gestionar_catalogo",
            "gestionar_compras",
            "ajustar_inventario",
            "ver_costos",
            "ver_reportes",
            "ver_historial_caja",
            "gestionar_usuarios",
            "ver_auditoria",
            "respaldar",
        }
        self.assertEqual(set(Permiso.objects.values_list("codigo", flat=True)), codigos_esperados)

        # 2 roles esperados
        self.assertEqual(Rol.objects.count(), 2)
        rol_dueno = Rol.objects.get(nombre="Dueño")
        rol_vendedor = Rol.objects.get(nombre="Vendedor")

        # Dueño tiene los 12 permisos
        self.assertEqual(rol_dueno.permisos.count(), 12)

        # Vendedor tiene exactamente 3 permisos
        permisos_vendedor = set(rol_vendedor.permisos.values_list("codigo", flat=True))
        self.assertEqual(permisos_vendedor, {"vender", "gestionar_caja", "ver_stock"})

        # 3 métodos de pago esperados
        self.assertEqual(MetodoPago.objects.count(), 3)
        efectivo = MetodoPago.objects.get(nombre="Efectivo")
        qr = MetodoPago.objects.get(nombre="QR")
        transf = MetodoPago.objects.get(nombre="Transferencia")

        self.assertTrue(efectivo.es_efectivo)
        self.assertFalse(qr.es_efectivo)
        self.assertFalse(transf.es_efectivo)

    def test_idempotencia_comando(self):
        # Ejecutar dos veces
        call_command("cargar_datos_iniciales")
        call_command("cargar_datos_iniciales")

        self.assertEqual(Permiso.objects.count(), 12)
        self.assertEqual(Rol.objects.count(), 2)
        self.assertEqual(MetodoPago.objects.count(), 3)
