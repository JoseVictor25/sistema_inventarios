"""Servicios, integración HTTP y seguridad del catálogo sobre SQLite de pruebas."""
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, OperationalError, transaction
from django.test import Client, RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse

from apps.auditoria.models import LogAuditoria
from apps.catalogo import services
from apps.catalogo.forms import PresentacionFormSet
from apps.catalogo.models import AtributoProducto, Categoria, Presentacion, Producto
from apps.compras.models import Compra, Proveedor
from apps.compras.services import guardar_proveedor
from apps.core.exceptions import ErrorDeNegocio
from apps.core.tests.test_regresiones_fase1 import crear_historial
from apps.inventario.models import Lote
from apps.usuarios.models import Permiso, Rol, Usuario


class CatalogoFase3Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos_iniciales", stdout=StringIO())
        cls.dueno = Usuario.objects.create_user("dueno3", rol=Rol.objects.get(nombre="Dueño"))
        cls.vendedor = Usuario.objects.create_user("vendedor3", rol=Rol.objects.get(nombre="Vendedor"))
        cls.superusuario = Usuario.objects.create_superuser("super3", password=None)
        cls.sin_rol = Usuario.objects.create_user("sinrol3")
        cls.inactivo = Usuario.objects.create_user("inactivo3", rol=cls.dueno.rol, is_active=False)
        cls.categoria = Categoria.objects.create(nombre="Naturales")
        cls.producto = services.crear_producto(cls.dueno, cls.datos_producto(), [cls.linea()])
        cls.presentacion = cls.producto.presentaciones.get()
        cls.atributo = services.guardar_atributo(cls.dueno, cls.producto.pk, {"nombre": "Origen", "valor": "La Paz"})
        cls.proveedor = guardar_proveedor(cls.dueno, {"nombre": "Proveedor", "tipo": "EMPRESA"})

    @classmethod
    def datos_producto(cls, **cambios):
        return {"codigo": "CAT-1", "nombre": "Aceite", "descripcion": "Natural", "categoria": cls.categoria,
                "stock_minimo": 5, "activo": True, **cambios}

    @staticmethod
    def linea(**cambios):
        return {"nombre": "Unidad", "unidades_equivalentes": 1, "precio_venta": Decimal("10.00"),
                "activa": True, **cambios}

    def setUp(self):
        self.client.force_login(self.dueno)

    def rutas(self):
        return [
            ("catalogo:categoria_lista", []), ("catalogo:categoria_crear", []),
            ("catalogo:categoria_editar", [self.categoria.pk]), ("catalogo:producto_lista", []),
            ("catalogo:producto_crear", []), ("catalogo:producto_editar", [self.producto.pk]),
            ("catalogo:producto_detalle", [self.producto.pk]), ("catalogo:producto_desactivar", [self.producto.pk]),
            ("catalogo:presentacion_crear", [self.producto.pk]), ("catalogo:presentacion_precio", [self.presentacion.pk]),
            ("catalogo:atributo_crear", [self.producto.pk]), ("catalogo:atributo_editar", [self.producto.pk, self.atributo.pk]),
            ("compras:proveedor_lista", []), ("compras:proveedor_crear", []),
            ("compras:proveedor_editar", [self.proveedor.pk]),
        ]

    def post_producto(self, editar=False, **cambios):
        datos = {"codigo": "CAT-1" if editar else "NUEVO", "nombre": "Producto nuevo", "descripcion": "",
                 "categoria": self.categoria.pk, "stock_minimo": "5", "activo": "on",
                 "presentaciones-TOTAL_FORMS": "1", "presentaciones-INITIAL_FORMS": "1" if editar else "0",
                 "presentaciones-MIN_NUM_FORMS": "1", "presentaciones-MAX_NUM_FORMS": "1000",
                 "presentaciones-0-nombre": "Unidad", "presentaciones-0-unidades_equivalentes": "1",
                 "presentaciones-0-precio_venta": "12.50", "presentaciones-0-activa": "on"}
        if editar:
            datos["presentaciones-0-id"] = self.presentacion.pk
            datos["presentaciones-0-producto"] = self.producto.pk
        datos.update(cambios)
        return datos

    def test_categoria_duplicados_raiz_y_hermanas(self):
        for padre in (None, self.categoria):
            services.guardar_categoria(self.dueno, {"nombre": "Duplicada", "padre": padre})
            with self.assertRaises(ErrorDeNegocio):
                services.guardar_categoria(self.dueno, {"nombre": "Duplicada", "padre": padre})
        otra = services.guardar_categoria(self.dueno, {"nombre": "Otra"})
        services.guardar_categoria(self.dueno, {"nombre": "Duplicada", "padre": otra})

    def test_movimiento_valido_y_ciclos(self):
        hija = services.guardar_categoria(self.dueno, {"nombre": "Hija", "padre": self.categoria})
        nieta = services.guardar_categoria(self.dueno, {"nombre": "Nieta", "padre": hija})
        for destino in (self.categoria, hija, nieta):
            with self.assertRaises(ErrorDeNegocio):
                services.mover_categoria(self.categoria, destino, usuario=self.dueno)
        services.mover_categoria(nieta, None, usuario=self.dueno)
        nieta.refresh_from_db()
        self.assertIsNone(nieta.padre)

    def test_ciclo_preexistente_no_provoca_bucle(self):
        a = Categoria.objects.create(nombre="A")
        b = Categoria.objects.create(nombre="B", padre=a)
        Categoria.objects.filter(pk=a.pk).update(padre=b)
        with self.assertRaises(ValidationError):
            Categoria(nombre="C", padre=b).full_clean()
        with self.assertRaises(ErrorDeNegocio):
            services.arbol_categorias(self.dueno)
        self.assertContains(self.client.get(reverse("catalogo:categoria_lista")), "contiene un ciclo")

    def test_categoria_inactiva_sin_cascada_y_edicion_existente(self):
        hija = Categoria.objects.create(nombre="Hija", padre=self.categoria)
        services.guardar_categoria(self.dueno, {"activa": False}, self.categoria.pk)
        hija.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertTrue(hija.activa)
        self.assertTrue(self.producto.activo)
        with self.assertRaises(ErrorDeNegocio):
            services.crear_producto(self.dueno, self.datos_producto(codigo="OTRO"), [self.linea()])
        services.editar_producto(self.dueno, self.producto.pk, {"nombre": "Editado"},
                                 [self.linea(id=self.presentacion.pk)])

    def test_creacion_completa_auditoria_equivalencias_y_cero(self):
        producto = services.crear_producto(self.dueno, self.datos_producto(codigo="CAJA"),
            [self.linea(nombre="Caja", unidades_equivalentes=17, precio_venta=Decimal("0"), activa=False)])
        self.assertEqual(producto.creado_por, self.dueno)
        p = producto.presentaciones.get()
        self.assertEqual(p.unidades_equivalentes, 17)
        self.assertFalse(p.activa)
        self.assertEqual(p.creado_por, self.dueno)

    def test_producto_sin_presentaciones_no_se_guarda(self):
        with self.assertRaises(ErrorDeNegocio):
            services.crear_producto(self.dueno, self.datos_producto(codigo="VACIO"), [])
        self.assertFalse(Producto.objects.filter(codigo="VACIO").exists())

    def test_rollback_si_segunda_presentacion_falla(self):
        antes = (Producto.objects.count(), Presentacion.objects.count())
        with self.assertRaises(ErrorDeNegocio):
            services.crear_producto(self.dueno, self.datos_producto(codigo="ROLLBACK"), [self.linea(), self.linea()])
        self.assertEqual(antes, (Producto.objects.count(), Presentacion.objects.count()))

    def test_datos_producto_invalidos(self):
        for cambios in ({"codigo": "CAT-1"}, {"stock_minimo": -1}, {"stock_minimo": True}, {"stock_minimo": 1.5}, {"creado_por": self.vendedor}):
            with self.subTest(cambios=cambios), self.assertRaises(ErrorDeNegocio):
                services.crear_producto(self.dueno, self.datos_producto(codigo="INVALIDO", **cambios) if "codigo" not in cambios else self.datos_producto(), [self.linea()])

    def test_precios_y_equivalencias_invalidos(self):
        casos = [self.linea(precio_venta=v) for v in (Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), Decimal("0.001"), Decimal("10000000000"), 1.5)]
        casos += [self.linea(unidades_equivalentes=v) for v in (0, -1, 1.5, True)]
        for datos in casos:
            with self.subTest(datos=datos), self.assertRaises(ErrorDeNegocio):
                services.agregar_presentacion(self.dueno, self.producto.pk, {**datos, "nombre": "Inválida"})
        self.assertEqual(self.producto.presentaciones.count(), 1)

    def test_restricciones_bd_presentaciones(self):
        for campo, valor in (("precio_venta", Decimal("-1")), ("unidades_equivalentes", 0)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Presentacion.objects.filter(pk=self.presentacion.pk).update(**{campo: valor})

    def test_precio_auditado_y_noop(self):
        resultado = services.cambiar_precio(self.dueno, self.presentacion, Decimal("15.20"))
        log = LogAuditoria.objects.get()
        self.assertEqual(log.usuario, self.dueno)
        self.assertEqual(log.accion, "CAMBIO_PRECIO")
        self.assertEqual(log.entidad_id, self.presentacion.pk)
        self.assertEqual(log.valor_anterior, {"precio_venta": "10.00"})
        self.assertEqual(log.valor_nuevo, {"precio_venta": "15.20"})
        self.assertIsNotNone(log.fecha)
        self.assertEqual(resultado.modificado_por, self.dueno)
        services.cambiar_precio(self.dueno, self.presentacion, Decimal("15.20"))
        self.assertEqual(LogAuditoria.objects.count(), 1)

    def test_precio_lee_valor_persistido_no_instancia(self):
        services.cambiar_precio(self.dueno, self.presentacion, Decimal("12"))
        services.cambiar_precio(self.dueno, self.presentacion, Decimal("13"))
        self.assertEqual(LogAuditoria.objects.order_by("pk").last().valor_anterior, {"precio_venta": "12.00"})

    def test_fallo_bitacora_revierte_precio(self):
        with patch("apps.catalogo.services.auditoria.registrar_cambio", side_effect=RuntimeError("prueba")):
            with self.assertRaises(RuntimeError):
                services.cambiar_precio(self.dueno, self.presentacion, Decimal("20"))
        self.presentacion.refresh_from_db()
        self.assertEqual(self.presentacion.precio_venta, Decimal("10"))
        self.assertFalse(LogAuditoria.objects.exists())

    def test_historial_ventas_y_desactivacion_intactos(self):
        historial = crear_historial()
        modelos = [type(historial[n]) for n in ("venta", "detalle_venta", "salida", "pago", "compra", "lote", "movimiento")]
        antes = {m: list(m.objects.values()) for m in modelos}
        services.cambiar_precio(self.dueno, historial["presentacion"], Decimal("99"))
        services.desactivar_producto(self.dueno, historial["producto"])
        self.assertEqual(antes, {m: list(m.objects.values()) for m in modelos})
        self.assertTrue(Presentacion.objects.filter(pk=historial["presentacion"].pk).exists())
        historial["producto"].refresh_from_db()
        self.assertFalse(historial["producto"].activo)

    def test_edicion_formset_audita_y_conserva_autor(self):
        services.editar_producto(self.superusuario, self.producto.pk, {"nombre": "Actualizado"},
                                 [self.linea(id=self.presentacion.pk, precio_venta=Decimal("11"))])
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.creado_por, self.dueno)
        self.assertEqual(self.producto.modificado_por, self.superusuario)
        self.assertEqual(LogAuditoria.objects.count(), 1)

    def test_edicion_rechaza_ids_ajenos_duplicados_y_omisiones(self):
        otra = services.crear_producto(self.dueno, self.datos_producto(codigo="OTRO"), [self.linea()]).presentaciones.get()
        for lineas in ([], [self.linea(id=otra.pk)], [self.linea(id=self.presentacion.pk)] * 2):
            with self.assertRaises(ErrorDeNegocio):
                services.editar_producto(self.dueno, self.producto.pk, {"nombre": "No guardar"}, lineas)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.nombre, "Aceite")

    def test_atributos_edicion_unicidad_y_producto_inmutable(self):
        services.guardar_atributo(self.dueno, self.producto.pk, {"valor": "Tarija"}, self.atributo.pk)
        self.atributo.refresh_from_db()
        self.assertEqual(self.atributo.valor, "Tarija")
        for datos in ({"nombre": "Origen", "valor": "Otro"}, {"nombre": "", "valor": ""}, {"producto_id": 9}):
            with self.assertRaises(ErrorDeNegocio):
                services.guardar_atributo(self.dueno, self.producto.pk, datos)

    def test_proveedores_tipos_autoria_duplicados_y_edicion(self):
        propio = guardar_proveedor(self.dueno, {"nombre": "Viaje", "tipo": "COMPRA_PROPIA", "origen": "Tarija"})
        guardar_proveedor(self.superusuario, {"activo": False, "telefono": "123"}, propio.pk)
        propio.refresh_from_db()
        self.assertFalse(propio.activo)
        self.assertEqual(propio.creado_por, self.dueno)
        self.assertEqual(propio.modificado_por, self.superusuario)
        for datos in ({"nombre": "Proveedor", "tipo": "EMPRESA"}, {"nombre": "Malo", "tipo": "OTRO"}):
            with self.assertRaises(ErrorDeNegocio):
                guardar_proveedor(self.dueno, datos)
        self.assertEqual(Compra.objects.count(), 0)

    def test_autorizacion_servicios_para_todos_los_actores(self):
        operaciones = [
            lambda u: services.arbol_categorias(u),
            lambda u: services.listar_productos(u, {}, 1),
            lambda u: services.guardar_categoria(u, {"nombre": "X"}),
            lambda u: services.mover_categoria(self.categoria, None, usuario=u),
            lambda u: services.crear_producto(u, self.datos_producto(codigo="X"), [self.linea()]),
            lambda u: services.editar_producto(u, self.producto.pk, {}, [self.linea(id=self.presentacion.pk)]),
            lambda u: services.cambiar_precio(u, self.presentacion, Decimal("1")),
            lambda u: services.agregar_presentacion(u, self.producto.pk, self.linea()),
            lambda u: services.desactivar_producto(u, self.producto),
            lambda u: services.guardar_atributo(u, self.producto.pk, {"nombre": "X", "valor": "X"}),
            lambda u: guardar_proveedor(u, {"nombre": "X", "tipo": "EMPRESA"}),
        ]
        from django.contrib.auth.models import AnonymousUser
        for usuario in (self.vendedor, self.inactivo, self.sin_rol, AnonymousUser()):
            for operacion in operaciones:
                with self.assertRaises(PermissionDenied):
                    operacion(usuario)

    def test_gets_autorizados_y_contrato_plantillas(self):
        solo_post = {"producto_desactivar", "presentacion_crear", "presentacion_precio", "atributo_crear"}
        for usuario in (self.dueno, self.superusuario):
            self.client.force_login(usuario)
            for nombre, args in self.rutas():
                with self.subTest(nombre=nombre):
                    respuesta = self.client.get(reverse(nombre, args=args))
                    self.assertEqual(respuesta.status_code, 405 if nombre.split(":")[1] in solo_post else 200)
                    if respuesta.status_code == 200:
                        self.assertTemplateUsed(respuesta, "base.html")
                        self.assertContains(respuesta, "vendor/adminlte/css/adminlte.min.css")

    def test_get_post_denegados_sin_permiso(self):
        for usuario in (self.vendedor, self.sin_rol):
            self.client.force_login(usuario)
            for nombre, args in self.rutas():
                url = reverse(nombre, args=args)
                for metodo in (self.client.get, self.client.post):
                    self.assertEqual(metodo(url).status_code, 403, url)

    def test_anonimo_e_inactivo_redirigidos(self):
        for usuario in (None, self.inactivo):
            self.client.logout()
            if usuario:
                self.client.force_login(usuario)
            for nombre, args in self.rutas():
                for metodo in (self.client.get, self.client.post):
                    self.assertEqual(metodo(reverse(nombre, args=args)).status_code, 302)

    def test_menu_no_concede_acceso_al_vendedor(self):
        self.assertContains(self.client.get("/"), 'href="/catalogo/productos/"')
        self.assertContains(self.client.get("/"), 'href="/compras/proveedores/"')
        self.client.force_login(self.vendedor)
        respuesta = self.client.get("/")
        self.assertNotContains(respuesta, 'href="/catalogo/productos/"')
        self.assertNotContains(respuesta, 'href="/compras/proveedores/"')
        self.assertEqual(set(self.vendedor.rol.permisos.values_list("codigo", flat=True)), {"vender", "gestionar_caja", "ver_stock"})

    def test_alta_edicion_http_y_auditoria(self):
        respuesta = self.client.post(reverse("catalogo:producto_crear"), self.post_producto())
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Producto.objects.get(codigo="NUEVO").presentaciones.count(), 1)
        respuesta = self.client.post(reverse("catalogo:producto_editar", args=[self.producto.pk]), self.post_producto(editar=True))
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(LogAuditoria.objects.count(), 1)

    def test_formset_post_manipulado_no_escribe(self):
        otra = services.crear_producto(self.dueno, self.datos_producto(codigo="OTRO"), [self.linea()])
        for cambios in ({"presentaciones-0-id": otra.presentaciones.get().pk},
                        {"presentaciones-TOTAL_FORMS": "0", "presentaciones-INITIAL_FORMS": "0"},
                        {"presentaciones-0-producto": otra.pk}, {"presentaciones-0-DELETE": "on"},
                        {"creado_por": self.vendedor.pk}, {"stock_actual": "999"}):
            respuesta = self.client.post(reverse("catalogo:producto_editar", args=[self.producto.pk]), self.post_producto(editar=True, **cambios))
            self.assertEqual(respuesta.status_code, 200)
            self.producto.refresh_from_db()
            self.assertEqual(self.producto.nombre, "Aceite")
        self.assertFalse(LogAuditoria.objects.exists())

    def test_htmx_presentaciones_atributos_y_precio(self):
        casos = [
            ("catalogo:presentacion_crear", self.producto.pk, {"nombre": "Caja", "unidades_equivalentes": "6", "precio_venta": "45", "activa": "on"}, "presentaciones"),
            ("catalogo:atributo_crear", self.producto.pk, {"nombre": "Aroma", "valor": "Menta"}, "atributos"),
            ("catalogo:presentacion_precio", self.presentacion.pk, {"precio_venta": "11"}, "presentaciones"),
        ]
        for nombre, pk, datos, destino in casos:
            respuesta = self.client.post(reverse(nombre, args=[pk]), datos, HTTP_HX_REQUEST="true")
            self.assertContains(respuesta, f'id="{destino}"')
        self.assertEqual(LogAuditoria.objects.count(), 1)

    def test_htmx_errores_422_y_campos_protegidos(self):
        casos = [("catalogo:presentacion_crear", {"nombre": "Mal", "unidades_equivalentes": "0", "precio_venta": "-1"}),
                 ("catalogo:atributo_crear", {"nombre": "Origen", "valor": "Duplicado"}),
                 ("catalogo:atributo_crear", {"nombre": "Mal", "valor": "X", "producto_id": "99"})]
        for nombre, datos in casos:
            self.assertEqual(self.client.post(reverse(nombre, args=[self.producto.pk]), datos, HTTP_HX_REQUEST="true").status_code, 422)
        self.assertEqual(self.client.post(reverse("catalogo:presentacion_precio", args=[self.presentacion.pk]), {"precio_venta": "-1"}).status_code, 422)

    def test_atributo_editar_escapado_y_pertenencia(self):
        url = reverse("catalogo:atributo_editar", args=[self.producto.pk, self.atributo.pk])
        self.assertEqual(self.client.post(url, {"nombre": "Origen", "valor": "<script>alert(1)</script>"}).status_code, 302)
        html = self.client.get(reverse("catalogo:producto_detalle", args=[self.producto.pk]))
        self.assertContains(html, "&lt;script&gt;")
        self.assertNotContains(html, "<script>alert(1)</script>")
        self.assertEqual(self.client.get(reverse("catalogo:atributo_editar", args=[999, self.atributo.pk])).status_code, 404)

    def test_filtros_paginacion_y_pareja_atributo(self):
        url = reverse("catalogo:producto_lista")
        self.assertContains(self.client.get(url, {"q": "CAT-1"}), "Aceite")
        self.assertContains(self.client.get(url, {"atributo": "Origen", "valor": "La Paz"}), "Aceite")
        self.assertNotContains(self.client.get(url, {"atributo": "Origen", "valor": "Tarija"}), "Aceite")
        self.assertTrue(self.client.get(url, {"atributo": "Origen"}).context["form_filtros"].errors)
        self.assertTrue(self.client.get(url, {"categoria": "999"}).context["form_filtros"].errors)
        for n in range(21):
            services.crear_producto(self.dueno, self.datos_producto(codigo=f"P-{n}", nombre=f"Lista {n}"), [self.linea()])
        respuesta = self.client.get(url, {"q": "Lista", "page": "2"})
        self.assertEqual(len(respuesta.context["page_obj"]), 1)
        self.assertContains(respuesta, "q=Lista")

    def test_costos_no_llegan_al_contexto_sin_permiso(self):
        rol = Rol.objects.create(nombre="Prueba catálogo sin costos")
        rol.permisos.add(Permiso.objects.get(codigo="gestionar_catalogo"))
        usuario = Usuario.objects.create_user("solo_catalogo", rol=rol)
        Lote.objects.create(producto=self.producto, codigo_lote="TEMP", cantidad_inicial=1,
                            cantidad_actual=1, costo_unitario=Decimal("87.65"))
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse("catalogo:producto_detalle", args=[self.producto.pk]))
        self.assertNotIn("costo_unitario", respuesta.context["lotes"][0])
        self.assertNotContains(respuesta, "Costo unitario")
        self.assertEqual(self.client.get(reverse("compras:proveedor_lista")).status_code, 403)

    def test_csrf_rechazo_y_post_valido(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.dueno)
        for nombre, args in self.rutas():
            self.assertEqual(cliente.post(reverse(nombre, args=args), {}).status_code, 403)
        url = reverse("catalogo:categoria_crear")
        cliente.get(url)
        respuesta = cliente.post(url, {"nombre": "CSRF", "activa": "on"}, HTTP_X_CSRFTOKEN=cliente.cookies["csrftoken"].value)
        self.assertEqual(respuesta.status_code, 302)

    def test_proveedor_http_alta_edicion_y_validacion(self):
        url = reverse("compras:proveedor_crear")
        self.assertEqual(self.client.post(url, {"nombre": "Nuevo", "tipo": "COMPRA_PROPIA", "activo": "on"}).status_code, 302)
        nuevo = Proveedor.objects.get(nombre="Nuevo")
        url = reverse("compras:proveedor_editar", args=[nuevo.pk])
        self.assertEqual(self.client.post(url, {"nombre": "Nuevo", "tipo": "EMPRESA"}).status_code, 302)
        nuevo.refresh_from_db()
        self.assertFalse(nuevo.activo)
        self.assertEqual(self.client.post(url, {"nombre": "Proveedor", "tipo": "EMPRESA"}).status_code, 200)
        self.assertEqual(self.client.post(url, {"nombre": "X", "tipo": "EMPRESA", "modificado_por": 999}).status_code, 200)

    def test_admin_solo_consulta_y_post_directo_denegado(self):
        self.client.force_login(self.superusuario)
        request = RequestFactory().get("/admin/")
        request.user = self.superusuario
        for obj in (self.categoria, self.producto, self.presentacion, self.atributo, self.proveedor):
            prefijo = f"admin:{obj._meta.app_label}_{obj._meta.model_name}"
            self.assertEqual(self.client.get(reverse(prefijo + "_change", args=[obj.pk])).status_code, 200)
            for accion in ("change", "delete", "add"):
                self.assertEqual(self.client.post(reverse(prefijo + "_" + accion, args=[] if accion == "add" else [obj.pk]), {}).status_code, 403)
            administrador = admin.site._registry[type(obj)]
            self.assertNotIn("delete_selected", administrador.get_actions(request))
            for inline in administrador.get_inline_instances(request, obj):
                self.assertFalse(inline.has_change_permission(request, obj))
                self.assertFalse(inline.has_delete_permission(request, obj))
                self.assertFalse(inline.has_add_permission(request, obj))

    def test_bloqueo_sqlite_es_error_controlado(self):
        with patch("apps.catalogo.services.Presentacion.objects.get", side_effect=OperationalError("database is locked")):
            with self.assertRaisesMessage(ErrorDeNegocio, "Otro proceso"):
                services.cambiar_precio(self.dueno, self.presentacion, Decimal("12"))

    def test_objetos_inexistentes_404_y_sin_crear_datos(self):
        for nombre in ("catalogo:producto_detalle", "catalogo:producto_editar", "catalogo:categoria_editar", "compras:proveedor_editar"):
            self.assertEqual(self.client.get(reverse(nombre, args=[99999])).status_code, 404)

    def test_categoria_alta_edicion_http_y_ciclo_rechazado(self):
        self.assertEqual(self.client.post(reverse("catalogo:categoria_crear"),
            {"nombre": "HTTP", "padre": self.categoria.pk, "activa": "on"}).status_code, 302)
        hija = Categoria.objects.get(nombre="HTTP")
        url = reverse("catalogo:categoria_editar", args=[self.categoria.pk])
        respuesta = self.client.post(url, {"nombre": "Naturales", "padre": hija.pk, "activa": "on"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].errors)
        self.categoria.refresh_from_db()
        self.assertIsNone(self.categoria.padre_id)

    def test_desactivar_post_sin_borrar_relaciones(self):
        url = reverse("catalogo:producto_desactivar", args=[self.producto.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.producto.refresh_from_db()
        self.assertFalse(self.producto.activo)
        self.assertEqual(self.producto.presentaciones.count(), 1)
        self.assertEqual(self.producto.atributos.count(), 1)

    def test_gets_no_modifican_catalogo(self):
        modelos = (Categoria, Producto, Presentacion, AtributoProducto, Proveedor, LogAuditoria)
        antes = {m: list(m.objects.values()) for m in modelos}
        for nombre, args in self.rutas():
            self.client.get(reverse(nombre, args=args))
        self.assertEqual(antes, {m: list(m.objects.values()) for m in modelos})

    def test_error_formato_http_no_guarda_parcial(self):
        for cambios in ({"presentaciones-0-unidades_equivalentes": "0"},
                        {"presentaciones-0-precio_venta": "-1"},
                        {"presentaciones-TOTAL_FORMS": ""}):
            respuesta = self.client.post(reverse("catalogo:producto_crear"), self.post_producto(**cambios))
            self.assertEqual(respuesta.status_code, 200)
            self.assertFalse(Producto.objects.filter(codigo="NUEVO").exists())


class ConcurrenciaPreciosTests(TransactionTestCase):
    """Conexiones independientes; el verificador configura un archivo SQLite temporal."""

    def setUp(self):
        self.usuario = Usuario.objects.create_superuser("concurrencia", password=None)
        categoria = Categoria.objects.create(nombre="Concurrente")
        producto = services.crear_producto(self.usuario, {"codigo": "CONC", "nombre": "Prueba", "categoria": categoria},
            [{"nombre": "Unidad", "unidades_equivalentes": 1, "precio_venta": Decimal("2")}])
        self.presentacion = producto.presentaciones.get()

    def test_dos_cambios_concurrentes_bitacora_coherente(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections
        barrera = Barrier(2)

        def cambiar(precio):
            try:
                usuario = Usuario.objects.get(pk=self.usuario.pk)
                presentacion = Presentacion.objects.get(pk=self.presentacion.pk)
                barrera.wait(timeout=5)
                try:
                    services.cambiar_precio(usuario, presentacion, Decimal(precio))
                except ErrorDeNegocio:
                    return False
                return True
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            resultados = list(ejecutor.map(cambiar, ("3", "4")))
        self.assertGreaterEqual(sum(resultados), 1)
        logs = list(LogAuditoria.objects.order_by("pk"))
        self.assertEqual(len(logs), sum(resultados))
        precio = Decimal("2")
        for log in logs:
            self.assertEqual(Decimal(log.valor_anterior["precio_venta"]), precio)
            precio = Decimal(log.valor_nuevo["precio_venta"])
        self.presentacion.refresh_from_db()
        self.assertEqual(self.presentacion.precio_venta, precio)

    def test_bloqueo_real_desde_otra_conexion_no_deja_cambios(self):
        import sqlite3
        from django.db import connection
        segunda = sqlite3.connect(str(connection.settings_dict["NAME"]), uri=True, timeout=0.1)
        try:
            segunda.execute("BEGIN IMMEDIATE")
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA busy_timeout=30")
            with self.assertRaisesMessage(ErrorDeNegocio, "Otro proceso"):
                services.cambiar_precio(self.usuario, self.presentacion, Decimal("5"))
        finally:
            segunda.rollback()
            segunda.close()
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA busy_timeout=5000")
        self.presentacion.refresh_from_db()
        self.assertEqual(self.presentacion.precio_venta, Decimal("2"))
        self.assertFalse(LogAuditoria.objects.exists())
