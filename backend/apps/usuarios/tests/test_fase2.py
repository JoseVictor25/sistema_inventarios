"""Pruebas de fase 2; usuarios y sesiones exclusivos de la base temporal."""
from io import StringIO

from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.core.exceptions import ErrorDeNegocio
from apps.core.permissions import codigos_permitidos, tiene_permiso
from apps.usuarios import services, views
from apps.usuarios.models import Permiso, Rol, Usuario


CLAVE = "Solo-pruebas-fase2-9462!"


class Fase2Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos_iniciales", stdout=StringIO())
        cls.dueno = Usuario.objects.create_user("dueno", password=CLAVE, rol=Rol.objects.get(nombre="Dueño"))
        cls.vendedor = Usuario.objects.create_user("vendedor", password=CLAVE, rol=Rol.objects.get(nombre="Vendedor"))
        cls.sin_rol = Usuario.objects.create_user("sin_rol", password=CLAVE)
        cls.superusuario = Usuario.objects.create_superuser("superusuario", password=CLAVE)
        cls.inactivo = Usuario.objects.create_user("inactivo", password=CLAVE, rol=cls.dueno.rol, is_active=False)

    def alta(self, **cambios):
        datos = dict(username="nuevo", first_name="Ana", last_name="Prueba",
                     rol=self.vendedor.rol_id, is_active="on", password1=CLAVE, password2=CLAVE)
        datos.update(cambios)
        return datos

    def edicion(self, usuario=None, **cambios):
        usuario = usuario or self.vendedor
        datos = dict(username=usuario.username, first_name="Actualizado", last_name="Prueba",
                     rol=usuario.rol_id or "", is_active="on")
        datos.update(cambios)
        return datos

    def url_editar(self, usuario=None):
        return reverse("usuarios:usuario_editar", args=[(usuario or self.vendedor).pk])

    def rutas(self):
        return [reverse("usuarios:lista"), reverse("usuarios:usuario_crear"),
                self.url_editar(), reverse("usuarios:rol_lista")]

    def test_matriz_inicial_y_superusuario_activo(self):
        todos = set(Permiso.objects.values_list("codigo", flat=True))
        self.assertEqual(len(todos), 12)
        self.assertEqual(set(codigos_permitidos(self.dueno)), todos)
        self.assertEqual(set(codigos_permitidos(self.superusuario)), todos)
        self.assertEqual(set(codigos_permitidos(self.vendedor)), {"vender", "gestionar_caja", "ver_stock"})
        for codigo in todos:
            self.assertTrue(tiene_permiso(self.dueno, codigo))
            self.assertTrue(tiene_permiso(self.superusuario, codigo))
            self.assertEqual(tiene_permiso(self.vendedor, codigo), codigo in codigos_permitidos(self.vendedor))

    def test_denegacion_sin_rol_rol_vacio_inactivo_anonimo(self):
        vacio = Rol.objects.create(nombre="Solo prueba")
        self.sin_rol.rol = vacio
        for usuario in [self.sin_rol, self.inactivo, AnonymousUser()]:
            with self.subTest(usuario=type(usuario).__name__):
                self.assertFalse(tiene_permiso(usuario, "gestionar_usuarios"))
                self.assertEqual(codigos_permitidos(usuario), [])
        self.superusuario.is_active = False
        self.assertFalse(tiene_permiso(self.superusuario, "gestionar_usuarios"))
        self.assertEqual(codigos_permitidos(self.superusuario), [])
        self.assertFalse(tiene_permiso(self.dueno, "permiso_inexistente"))

    def test_anonimo_redirigido_en_get_y_post(self):
        for ruta in self.rutas():
            for metodo in [self.client.get, self.client.post]:
                respuesta = metodo(ruta)
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta.url.startswith("/login/?next="))

    def test_vendedor_y_sin_rol_reciben_403_get_y_post(self):
        for usuario in [self.vendedor, self.sin_rol]:
            self.client.force_login(usuario)
            for ruta in self.rutas():
                for metodo in [self.client.get, self.client.post]:
                    with self.subTest(usuario=usuario.username, ruta=ruta), self.assertLogs("django.request", level="WARNING"):
                        respuesta = metodo(ruta, self.alta())
                    self.assertEqual(respuesta.status_code, 403)
                    self.assertContains(respuesta, "No tienes permiso para esta acción.", status_code=403)
        self.assertFalse(Usuario.objects.filter(username="nuevo").exists())

    def test_inactivo_denegado_por_decorador_y_por_login(self):
        for metodo in ("get", "post"):
            request = getattr(RequestFactory(), metodo)("/usuarios/nuevo/")
            request.user = self.inactivo
            with self.assertRaises(PermissionDenied):
                views.usuario_crear(request)
        self.assertFalse(self.client.login(username=self.inactivo.username, password=CLAVE))

    def test_superusuario_y_dueno_acceden_a_las_pantallas(self):
        for usuario in [self.superusuario, self.dueno]:
            self.client.force_login(usuario)
            for ruta in self.rutas():
                with self.subTest(usuario=usuario.username, ruta=ruta):
                    self.assertEqual(self.client.get(ruta).status_code, 200)

    def test_crear_usuario_con_hash_y_rol_sin_privilegios(self):
        for indice, actor in enumerate([self.dueno, self.superusuario]):
            self.client.force_login(actor)
            nombre = f"nuevo{indice}"
            respuesta = self.client.post(reverse("usuarios:usuario_crear"), self.alta(username=nombre), follow=True)
            self.assertContains(respuesta, "Usuario creado correctamente.")
            usuario = Usuario.objects.get(username=nombre)
            self.assertTrue(usuario.check_password(CLAVE))
            self.assertNotEqual(usuario.password, CLAVE)
            self.assertEqual(usuario.rol_id, self.vendedor.rol_id)
            self.assertTrue(usuario.is_active)
            self.assertFalse(usuario.is_staff)
            self.assertFalse(usuario.is_superuser)
            self.assertFalse(usuario.groups.exists())
            self.assertFalse(usuario.user_permissions.exists())

    def test_campos_y_contrasenas_invalidos_no_crean_cuentas(self):
        self.client.force_login(self.dueno)
        casos = [dict(password1="123", password2="123"),
                 dict(password1="password", password2="password"),
                 dict(password2="No-coincide-982!"), dict(password1="", password2=""),
                 dict(username=""), dict(username="invalido espacio"),
                 dict(username=self.vendedor.username), dict(rol="999999"),
                 dict(first_name="x" * 151)]
        antes = Usuario.objects.count()
        for caso in casos:
            with self.subTest(caso=list(caso)):
                respuesta = self.client.post(reverse("usuarios:usuario_crear"), self.alta(**caso))
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context["form"].errors)
                self.assertEqual(Usuario.objects.count(), antes)

    def test_alta_sin_rol_no_otorga_permisos(self):
        self.client.force_login(self.dueno)
        respuesta = self.client.post(reverse("usuarios:usuario_crear"), self.alta(rol=""))
        self.assertEqual(respuesta.status_code, 302)
        usuario = Usuario.objects.get(username="nuevo")
        self.assertIsNone(usuario.rol)
        self.assertFalse(tiene_permiso(usuario, "gestionar_usuarios"))

    def test_editar_activar_desactivar_y_cambiar_rol(self):
        self.client.force_login(self.dueno)
        password = self.vendedor.password
        for estado in ("", "on"):
            respuesta = self.client.post(self.url_editar(), self.edicion(rol=self.dueno.rol_id, is_active=estado), follow=True)
            self.assertContains(respuesta, "Usuario actualizado correctamente.")
            self.vendedor.refresh_from_db()
            self.assertEqual(self.vendedor.is_active, bool(estado))
            self.assertEqual(self.vendedor.password, password)
            self.assertEqual(self.vendedor.rol_id, self.dueno.rol_id)
            self.assertEqual(self.vendedor.first_name, "Actualizado")

    def test_post_vacio_no_desactiva_por_accidente(self):
        self.client.force_login(self.dueno)
        respuesta = self.client.post(self.url_editar(), {})
        self.assertTrue(respuesta.context["form"].errors)
        self.vendedor.refresh_from_db()
        self.assertTrue(self.vendedor.is_active)

    def test_edicion_duplicada_no_altera_registro(self):
        self.client.force_login(self.dueno)
        antes = Usuario.objects.values().get(pk=self.vendedor.pk)
        respuesta = self.client.post(self.url_editar(), self.edicion(username=self.dueno.username))
        self.assertIn("username", respuesta.context["form"].errors)
        self.assertEqual(Usuario.objects.values().get(pk=self.vendedor.pk), antes)

    def test_cuenta_inexistente_devuelve_404(self):
        self.client.force_login(self.dueno)
        with self.assertLogs("django.request", level="WARNING"):
            self.assertEqual(self.client.get(reverse("usuarios:usuario_editar", args=[999999])).status_code, 404)

    def test_cuenta_propia_y_superusuarios_protegidos_get_post(self):
        for actor in [self.dueno, self.superusuario]:
            self.client.force_login(actor)
            for objetivo in [actor, self.superusuario]:
                antes = Usuario.objects.values().get(pk=objetivo.pk)
                for metodo in [self.client.get, self.client.post]:
                    with self.assertLogs("django.request", level="WARNING"):
                        respuesta = metodo(self.url_editar(objetivo), self.edicion(objetivo, is_active=""))
                    self.assertEqual(respuesta.status_code, 403)
                self.assertEqual(Usuario.objects.values().get(pk=objetivo.pk), antes)
            html = self.client.get(reverse("usuarios:lista"))
            self.assertNotContains(html, f'href="{self.url_editar(actor)}"')
            self.assertNotContains(html, f'href="{self.url_editar(self.superusuario)}"')

    def test_post_privilegios_tecnicos_rechazado_en_alta_y_edicion(self):
        self.client.force_login(self.dueno)
        for campo in ("is_staff", "is_superuser", "groups", "user_permissions", "password", "id"):
            with self.subTest(campo=campo):
                respuesta = self.client.post(reverse("usuarios:usuario_crear"), self.alta(**{campo: "1"}))
                self.assertTrue(respuesta.context["form"].non_field_errors())
                self.assertFalse(Usuario.objects.filter(username="nuevo").exists())
                antes = Usuario.objects.values().get(pk=self.vendedor.pk)
                respuesta = self.client.post(self.url_editar(), self.edicion(**{campo: "1"}))
                self.assertTrue(respuesta.context["form"].non_field_errors())
                self.assertEqual(Usuario.objects.values().get(pk=self.vendedor.pk), antes)

    def test_edicion_conserva_privilegios_tecnicos_existentes(self):
        self.client.force_login(self.dueno)
        self.vendedor.is_staff = True
        self.vendedor.save(update_fields=["is_staff"])
        grupo = Group.objects.create(name="Solo prueba")
        permiso = Permission.objects.first()
        self.vendedor.groups.add(grupo)
        self.vendedor.user_permissions.add(permiso)
        self.client.post(self.url_editar(), self.edicion())
        self.vendedor.refresh_from_db()
        self.assertTrue(self.vendedor.is_staff)
        self.assertFalse(self.vendedor.is_superuser)
        self.assertEqual(list(self.vendedor.groups.all()), [grupo])
        self.assertEqual(list(self.vendedor.user_permissions.all()), [permiso])

    def test_no_cambio_de_contrasena_por_edicion(self):
        self.client.force_login(self.dueno)
        respuesta = self.client.post(self.url_editar(), self.edicion(password1=CLAVE, password2=CLAVE))
        self.assertTrue(respuesta.context["form"].non_field_errors())
        self.vendedor.refresh_from_db()
        self.assertEqual(self.vendedor.password, type(self).vendedor.password)

    def test_roles_solo_consulta_sin_modificar_matriz(self):
        self.client.force_login(self.dueno)
        antes = list(Rol.permisos.through.objects.order_by("pk").values())
        respuesta = self.client.get(reverse("usuarios:rol_lista"))
        self.assertEqual(len(respuesta.context["roles"]), 2)
        self.assertEqual(len(respuesta.context["catalogo_permisos"]), 12)
        self.assertEqual(set(respuesta.context["permisos"]), set(codigos_permitidos(self.dueno)))
        with self.assertLogs("django.request", level="WARNING"):
            self.assertEqual(self.client.post(reverse("usuarios:rol_lista"), {"nombre": "Otro", "permisos": []}).status_code, 405)
        self.assertEqual(list(Rol.permisos.through.objects.order_by("pk").values()), antes)

    def test_menu_y_contexto_coherentes_con_permisos(self):
        for actor, permitido in [(self.dueno, True), (self.superusuario, True), (self.vendedor, False), (self.sin_rol, False)]:
            self.client.force_login(actor)
            respuesta = self.client.get("/")
            self.assertEqual(set(respuesta.context["permisos"]), set(codigos_permitidos(actor)))
            comprobar = self.assertContains if permitido else self.assertNotContains
            comprobar(respuesta, 'href="/usuarios/"')
            comprobar(respuesta, 'href="/usuarios/roles/"')
        self.client.logout()
        self.assertEqual(self.client.get("/login/").context["permisos"], [])

    def test_cambio_de_rol_aplica_en_siguiente_peticion(self):
        self.client.force_login(self.dueno)
        self.assertEqual(self.client.get("/usuarios/").status_code, 200)
        Usuario.objects.filter(pk=self.dueno.pk).update(rol=self.vendedor.rol)
        with self.assertLogs("django.request", level="WARNING"):
            self.assertEqual(self.client.get("/usuarios/").status_code, 403)

    def test_desactivacion_invalida_acceso_de_sesion_existente(self):
        self.client.force_login(self.dueno)
        Usuario.objects.filter(pk=self.dueno.pk).update(is_active=False)
        self.assertEqual(self.client.get("/usuarios/").status_code, 302)

    def test_csrf_en_creacion_y_edicion(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.dueno)
        for ruta, datos in [(reverse("usuarios:usuario_crear"), self.alta()), (self.url_editar(), self.edicion())]:
            with self.assertLogs("django.security.csrf", level="WARNING"):
                self.assertEqual(cliente.post(ruta, datos).status_code, 403)
            cliente.get(ruta)
            datos["csrfmiddlewaretoken"] = cliente.cookies["csrftoken"].value
            self.assertEqual(cliente.post(ruta, datos).status_code, 302)

    def test_plantillas_locales_y_get_no_escribe(self):
        self.client.force_login(self.dueno)
        antes = list(Usuario.objects.order_by("pk").values())
        for ruta in self.rutas():
            respuesta = self.client.get(ruta)
            self.assertContains(respuesta, 'id="mensajes"')
            self.assertContains(respuesta, "vendor/adminlte/css/adminlte.min.css")
            self.assertNotContains(respuesta, "https://")
            self.assertNotContains(respuesta, "http://")
        self.assertEqual(list(Usuario.objects.order_by("pk").values()), antes)

    def test_servicios_rechazan_actores_no_autorizados_y_objetivos_protegidos(self):
        datos = dict(username="nuevo", first_name="", last_name="", rol=None, is_active=True)
        for actor in [self.vendedor, self.sin_rol, self.inactivo, AnonymousUser()]:
            with self.assertRaises(PermissionDenied):
                services.crear_usuario(actor, **datos, password=CLAVE)
            with self.assertRaises(PermissionDenied):
                services.editar_usuario(actor, self.vendedor.pk, **datos)
        for objetivo in [self.dueno, self.superusuario]:
            with self.assertRaises(PermissionDenied):
                services.editar_usuario(self.dueno, objetivo.pk, **datos)

    def test_servicios_validan_password_duplicados_y_cuenta_inexistente(self):
        datos = dict(username="nuevo", first_name="", last_name="", rol=None, is_active=True)
        with self.assertRaises(ErrorDeNegocio):
            services.crear_usuario(self.dueno, **datos, password="123")
        datos["username"] = self.vendedor.username
        with self.assertRaises(ErrorDeNegocio):
            services.crear_usuario(self.dueno, **datos, password=CLAVE)
        with self.assertRaises(ErrorDeNegocio):
            services.editar_usuario(self.dueno, 999999, **datos)
