"""Pruebas de modelos para la app usuarios: Permiso, Rol y Usuario."""
from django.db.models import ProtectedError
from django.db.utils import IntegrityError
from django.test import TestCase

from apps.usuarios.models import Permiso, Rol, Usuario


class PermisoModelTest(TestCase):
    def test_creacion_y_str(self):
        p = Permiso.objects.create(codigo="vender", descripcion="Permite vender")
        self.assertEqual(str(p), "vender")

    def test_codigo_unico(self):
        Permiso.objects.create(codigo="vender", descripcion="Permite vender")
        with self.assertRaises(IntegrityError):
            Permiso.objects.create(codigo="vender", descripcion="Duplicado")


class RolModelTest(TestCase):
    def test_creacion_y_permisos(self):
        p1 = Permiso.objects.create(codigo="vender", descripcion="Venta")
        p2 = Permiso.objects.create(codigo="ver_stock", descripcion="Stock")
        rol = Rol.objects.create(nombre="Vendedor", descripcion="Rol de mostrador")
        rol.permisos.add(p1, p2)
        self.assertEqual(str(rol), "Vendedor")
        self.assertEqual(rol.permisos.count(), 2)

    def test_nombre_unico(self):
        Rol.objects.create(nombre="Dueño")
        with self.assertRaises(IntegrityError):
            Rol.objects.create(nombre="Dueño")


class UsuarioModelTest(TestCase):
    def test_usuario_sin_rol(self):
        u = Usuario.objects.create_user(username="admin_user", password="secret_password")
        self.assertIsNone(u.rol)
        self.assertEqual(str(u), "admin_user")

    def test_usuario_con_rol_y_protect(self):
        rol = Rol.objects.create(nombre="Vendedor")
        u = Usuario.objects.create_user(username="empleado1", password="secret_password", rol=rol)
        self.assertEqual(u.rol, rol)
        # RN / Arquitectura: no se puede eliminar el rol si tiene usuarios asignados
        with self.assertRaises(ProtectedError):
            rol.delete()
