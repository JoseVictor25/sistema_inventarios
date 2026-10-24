"""Comando de gestión: carga datos iniciales de roles, permisos y métodos de pago.

Cumple con la especificación §10 y §14.
Puede ejecutarse múltiples veces sin duplicar datos. Conserva descripciones y
métodos existentes; repone los permisos iniciales de cada rol si fueron retirados.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.usuarios.models import Permiso, Rol
from apps.ventas.models import MetodoPago


class Command(BaseCommand):
    help = "Carga roles, permisos iniciales y métodos de pago del sistema (idempotente)."

    PERMISOS = [
        ("vender", "Usar la pantalla de venta"),
        ("gestionar_caja", "Abrir, mover y cerrar su propia caja"),
        ("ver_stock", "Ver el stock, los lotes y las alertas"),
        ("gestionar_catalogo", "Crear y editar categorías, productos, presentaciones y atributos; cambiar precios"),
        ("gestionar_compras", "Registrar compras y proveedores"),
        ("ajustar_inventario", "Registrar ajustes y mermas"),
        ("ver_costos", "Ver costos de compra y ganancias"),
        ("ver_reportes", "Ver y exportar reportes"),
        ("ver_historial_caja", "Ver el historial de cierres de todos los usuarios"),
        ("gestionar_usuarios", "Crear usuarios y asignar roles"),
        ("ver_auditoria", "Ver la bitácora"),
        ("respaldar", "Crear y ver respaldos"),
    ]

    ROLES = {
        "Dueño": {
            "descripcion": "Acceso total a todas las operaciones y configuraciones del sistema.",
            "permisos": [codigo for codigo, _ in PERMISOS],
        },
        "Vendedor": {
            "descripcion": "Acceso a venta, apertura/cierre de su propia caja y consulta de stock.",
            "permisos": ["vender", "gestionar_caja", "ver_stock"],
        },
    }

    METODOS_PAGO = [
        {"nombre": "Efectivo", "es_efectivo": True, "activo": True},
        {"nombre": "QR", "es_efectivo": False, "activo": True},
        {"nombre": "Transferencia", "es_efectivo": False, "activo": True},
    ]

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Iniciando carga de datos iniciales...")

        # 1. Permisos
        permisos_creados = 0
        permisos_existentes = 0
        permisos_dict = {}

        for codigo, descripcion in self.PERMISOS:
            permiso, created = Permiso.objects.get_or_create(
                codigo=codigo,
                defaults={"descripcion": descripcion},
            )
            permisos_dict[codigo] = permiso
            if created:
                permisos_creados += 1
            else:
                permisos_existentes += 1

        self.stdout.write(
            f"  Permisos: {permisos_creados} creados, {permisos_existentes} ya existían (Total: {len(permisos_dict)})."
        )

        # 2. Roles
        roles_creados = 0
        roles_existentes = 0

        for nombre_rol, config in self.ROLES.items():
            rol, created = Rol.objects.get_or_create(
                nombre=nombre_rol,
                defaults={"descripcion": config["descripcion"]},
            )
            # Asignar permisos especificados
            permisos_a_asignar = [
                permisos_dict[cod] for cod in config["permisos"] if cod in permisos_dict
            ]
            rol.permisos.add(*permisos_a_asignar)

            if created:
                roles_creados += 1
            else:
                roles_existentes += 1

        self.stdout.write(
            f"  Roles: {roles_creados} creados, {roles_existentes} ya existían."
        )

        # 3. Métodos de pago
        metodos_creados = 0
        metodos_existentes = 0

        for mp_data in self.METODOS_PAGO:
            _, created = MetodoPago.objects.get_or_create(
                nombre=mp_data["nombre"],
                defaults={
                    "es_efectivo": mp_data["es_efectivo"],
                    "activo": mp_data["activo"],
                },
            )
            if created:
                metodos_creados += 1
            else:
                metodos_existentes += 1

        self.stdout.write(
            f"  Métodos de pago: {metodos_creados} creados, {metodos_existentes} ya existían."
        )

        self.stdout.write(self.style.SUCCESS("Carga de datos iniciales completada exitosamente."))
