"""Suite exhaustiva de pruebas para Fase 4: Compras y Lotes.

Cubre modelos, servicios, transacciones, unicidad de lotes, prevención de duplicados,
permisos de negocio (gestionar_compras, ver_costos), endpoints HTTP y HTMX, y rollback.
"""
import datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from apps.catalogo.models import Categoria, Producto
from apps.compras.models import Compra, DetalleCompra, Proveedor
from apps.compras import services
from apps.core.exceptions import ErrorDeNegocio
from apps.inventario.models import Lote, MovimientoInventario
from apps.usuarios.models import Permiso, Rol, Usuario


class ComprasFase4Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos_iniciales", stdout=StringIO())

        cls.dueno = Usuario.objects.create_user("dueno4", rol=Rol.objects.get(nombre="Dueño"))
        cls.vendedor = Usuario.objects.create_user("vendedor4", rol=Rol.objects.get(nombre="Vendedor"))
        cls.superusuario = Usuario.objects.create_superuser("super4", password=None)
        cls.sin_rol = Usuario.objects.create_user("sinrol4")
        cls.inactivo = Usuario.objects.create_user("inactivo4", rol=cls.dueno.rol, is_active=False)

        # Usuario especial con gestionar_compras pero sin ver_costos para probar RN-20
        rol_comprador_sin_costos = Rol.objects.create(nombre="CompradorSinCostos")
        perm_compras = Permiso.objects.get(codigo="gestionar_compras")
        rol_comprador_sin_costos.permisos.add(perm_compras)
        cls.comprador_sin_costos = Usuario.objects.create_user(
            "comprador_sin_costos",
            rol=rol_comprador_sin_costos,
        )

        cls.categoria = Categoria.objects.create(nombre="Insumos Cosméticos")
        cls.prod1 = Producto.objects.create(
            codigo="INS-01",
            nombre="Aceite de Ricino",
            categoria=cls.categoria,
            creado_por=cls.dueno,
            modificado_por=cls.dueno,
        )
        cls.prod2 = Producto.objects.create(
            codigo="INS-02",
            nombre="Manteca de Karité",
            categoria=cls.categoria,
            creado_por=cls.dueno,
            modificado_por=cls.dueno,
        )
        cls.prod_inactivo = Producto.objects.create(
            codigo="INS-99",
            nombre="Producto Descontinuado",
            categoria=cls.categoria,
            activo=False,
            creado_por=cls.dueno,
            modificado_por=cls.dueno,
        )

        cls.proveedor = Proveedor.objects.create(
            nombre="Distribuidora Botánica",
            tipo=Proveedor.TipoProveedor.EMPRESA,
            creado_por=cls.dueno,
            modificado_por=cls.dueno,
        )
        cls.prov_inactivo = Proveedor.objects.create(
            nombre="Proveedor Cerrado",
            tipo=Proveedor.TipoProveedor.EMPRESA,
            activo=False,
            creado_por=cls.dueno,
            modificado_por=cls.dueno,
        )

    def setUp(self):
        self.client.force_login(self.dueno)

    # --- 1. Pruebas del servicio registrar_compra (Casos Correctos) ------------

    def test_compra_una_linea_exitosa(self):
        """Registra compra simple, genera detalle, lote y movimiento ENTRADA."""
        lineas = [{
            "producto": self.prod1,
            "cantidad": 10,
            "costo_unitario": Decimal("15.50"),
            "fecha_vencimiento": None,
        }]
        compra = services.registrar_compra(
            usuario=self.dueno,
            proveedor=self.proveedor,
            lineas=lineas,
            observacion="Primera compra de prueba",
        )

        self.assertIsInstance(compra, Compra)
        self.assertEqual(compra.total, Decimal("155.00"))
        self.assertEqual(compra.usuario, self.dueno)
        self.assertEqual(compra.creado_por, self.dueno)
        self.assertEqual(compra.detalles.count(), 1)

        detalle = compra.detalles.first()
        self.assertEqual(detalle.producto, self.prod1)
        self.assertEqual(detalle.cantidad_unidades, 10)
        self.assertEqual(detalle.costo_unitario, Decimal("15.50"))
        self.assertEqual(detalle.subtotal, Decimal("155.00"))

        # Verificar Lote generado (RN-05)
        lote = detalle.lote
        self.assertIsNotNone(lote)
        self.assertEqual(lote.producto, self.prod1)
        self.assertEqual(lote.cantidad_inicial, 10)
        self.assertEqual(lote.cantidad_actual, 10)
        self.assertEqual(lote.costo_unitario, Decimal("15.50"))
        self.assertIsNone(lote.fecha_vencimiento)
        self.assertTrue(lote.codigo_lote.startswith(f"L-{datetime.date.today().year}-"))

        # Verificar MovimientoInventario de ENTRADA
        movs = lote.movimientos.all()
        self.assertEqual(movs.count(), 1)
        mov = movs.first()
        self.assertEqual(mov.tipo, MovimientoInventario.TipoMovimiento.ENTRADA)
        self.assertEqual(mov.cantidad, 10)
        self.assertEqual(mov.usuario, self.dueno)
        self.assertEqual(mov.motivo, f"Compra #{compra.pk}")

        # Stock actualizado en unidades (RN-01)
        self.assertEqual(self.prod1.stock_actual, 10)

    def test_compra_multiples_lineas_exitosa(self):
        """Registra compra con varias líneas, vencimientos futuros y cálculo total."""
        venc = datetime.date.today() + datetime.timedelta(days=90)
        lineas = [
            {"producto_id": self.prod1.pk, "cantidad": 5, "costo_unitario": Decimal("20.00"), "fecha_vencimiento": venc},
            {"producto_id": self.prod2.pk, "cantidad": 12, "costo_unitario": Decimal("10.00"), "fecha_vencimiento": None},
        ]
        compra = services.registrar_compra(
            usuario=self.dueno,
            proveedor=self.proveedor.pk,
            lineas=lineas,
        )

        self.assertEqual(compra.detalles.count(), 2)
        self.assertEqual(compra.total, Decimal("220.00"))  # 5*20 + 12*10 = 100 + 120 = 220

        # Lotes generados correlativamente
        lotes = [d.lote for d in compra.detalles.all()]
        self.assertEqual(len(lotes), 2)
        self.assertNotEqual(lotes[0].codigo_lote, lotes[1].codigo_lote)
        self.assertEqual(lotes[0].fecha_vencimiento, venc)
        self.assertIsNone(lotes[1].fecha_vencimiento)

        # Movimientos ENTRADA para cada lote
        self.assertEqual(MovimientoInventario.objects.filter(lote__in=lotes, tipo="ENTRADA").count(), 2)

    def test_generacion_codigos_lote_correlativo_y_sin_duplicados(self):
        """Genera códigos L-AAAA-NNNN consecutivos y evita colisiones si ya existen."""
        anio = 2026
        codigo1 = services.generar_codigo_lote(anio=anio)
        self.assertEqual(codigo1, "L-2026-0001")

        # Crear lote con ese código manualmente
        linea = [{"producto": self.prod1, "cantidad": 1, "costo_unitario": Decimal("5.00")}]
        services.registrar_compra(self.dueno, self.proveedor, linea, fecha=datetime.date(anio, 1, 15))

        # El siguiente debe ser L-2026-0002
        codigo2 = services.generar_codigo_lote(anio=anio)
        self.assertEqual(codigo2, "L-2026-0002")

        # Si creamos artificialmente L-2026-0002 sin pasar por compra, el generador salta a 0003
        Lote.objects.create(
            producto=self.prod1,
            codigo_lote="L-2026-0002",
            cantidad_inicial=1,
            cantidad_actual=1,
            costo_unitario=Decimal("5.00"),
        )
        codigo3 = services.generar_codigo_lote(anio=anio)
        self.assertEqual(codigo3, "L-2026-0003")

    # --- 2. Validaciones de Negocio y Casos de Error ---------------------------

    def test_rechazo_proveedor_inactivo(self):
        lineas = [{"producto": self.prod1, "cantidad": 5, "costo_unitario": Decimal("10.00")}]
        with self.assertRaises(ErrorDeNegocio) as ctx:
            services.registrar_compra(self.dueno, self.prov_inactivo, lineas)
        self.assertIn("inactivo", str(ctx.exception))

    def test_rechazo_producto_inactivo(self):
        lineas = [{"producto": self.prod_inactivo, "cantidad": 5, "costo_unitario": Decimal("10.00")}]
        with self.assertRaises(ErrorDeNegocio) as ctx:
            services.registrar_compra(self.dueno, self.proveedor, lineas)
        self.assertIn("inactivo", str(ctx.exception))

    def test_rechazo_sin_lineas(self):
        with self.assertRaises(ErrorDeNegocio) as ctx:
            services.registrar_compra(self.dueno, self.proveedor, [])
        self.assertIn("al menos una línea", str(ctx.exception))

    def test_rechazo_cantidad_cero_o_negativa(self):
        with self.assertRaises(ErrorDeNegocio):
            services.registrar_compra(
                self.dueno, self.proveedor,
                [{"producto": self.prod1, "cantidad": 0, "costo_unitario": Decimal("10.00")}],
            )
        with self.assertRaises(ErrorDeNegocio):
            services.registrar_compra(
                self.dueno, self.proveedor,
                [{"producto": self.prod1, "cantidad": -5, "costo_unitario": Decimal("10.00")}],
            )

    def test_rechazo_costo_negativo_o_decimales_excesivos(self):
        with self.assertRaises(ErrorDeNegocio):
            services.registrar_compra(
                self.dueno, self.proveedor,
                [{"producto": self.prod1, "cantidad": 5, "costo_unitario": Decimal("-1.00")}],
            )
        with self.assertRaises(ErrorDeNegocio):
            services.registrar_compra(
                self.dueno, self.proveedor,
                [{"producto": self.prod1, "cantidad": 5, "costo_unitario": Decimal("10.999")}],
            )

    def test_rechazo_vencimiento_en_el_pasado(self):
        ayer = datetime.date.today() - datetime.timedelta(days=1)
        lineas = [{"producto": self.prod1, "cantidad": 5, "costo_unitario": Decimal("10.00"), "fecha_vencimiento": ayer}]
        with self.assertRaises(ErrorDeNegocio) as ctx:
            services.registrar_compra(self.dueno, self.proveedor, lineas)
        self.assertIn("anterior a la fecha actual", str(ctx.exception))

    # --- 3. Atomicidad y Rollback ---------------------------------------------

    def test_rollback_total_ante_fallo_en_linea_intermedia(self):
        """Verifica que si falla una línea posterior, no se guarda nada."""
        compras_antes = Compra.objects.count()
        detalles_antes = DetalleCompra.objects.count()
        lotes_antes = Lote.objects.count()
        movs_antes = MovimientoInventario.objects.count()

        lineas = [
            {"producto": self.prod1, "cantidad": 5, "costo_unitario": Decimal("10.00")},
            {"producto": self.prod_inactivo, "cantidad": 5, "costo_unitario": Decimal("10.00")},  # Fallará aquí
        ]

        with self.assertRaises(ErrorDeNegocio):
            services.registrar_compra(self.dueno, self.proveedor, lineas)

        # Ningún registro debe haber sido persistido
        self.assertEqual(Compra.objects.count(), compras_antes)
        self.assertEqual(DetalleCompra.objects.count(), detalles_antes)
        self.assertEqual(Lote.objects.count(), lotes_antes)
        self.assertEqual(MovimientoInventario.objects.count(), movs_antes)

    # --- 4. Permisos de Negocio en Servicios ----------------------------------

    def test_permisos_servicios(self):
        lineas = [{"producto": self.prod1, "cantidad": 1, "costo_unitario": Decimal("10.00")}]

        # Dueño tiene gestionar_compras: permitido
        compra = services.registrar_compra(self.dueno, self.proveedor, lineas)
        self.assertIsNotNone(compra.pk)

        # Vendedor no tiene gestionar_compras: PermissionDenied
        with self.assertRaises(PermissionDenied):
            services.registrar_compra(self.vendedor, self.proveedor, lineas)

        # Usuario sin rol: PermissionDenied
        with self.assertRaises(PermissionDenied):
            services.registrar_compra(self.sin_rol, self.proveedor, lineas)

        # Usuario inactivo: PermissionDenied
        with self.assertRaises(PermissionDenied):
            services.registrar_compra(self.inactivo, self.proveedor, lineas)

    # --- 5. Vistas HTTP y Respuestas ------------------------------------------

    def test_compra_lista_http(self):
        # GET Dueño -> 200
        res = self.client.get(reverse("compras:compra_lista"))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "compras/compra_lista.html")

        # GET Vendedor -> 403
        self.client.force_login(self.vendedor)
        res_vendedor = self.client.get(reverse("compras:compra_lista"))
        self.assertEqual(res_vendedor.status_code, 403)

        # GET Anónimo -> 302 a login
        self.client.logout()
        res_anon = self.client.get(reverse("compras:compra_lista"))
        self.assertEqual(res_anon.status_code, 302)

    def test_compra_crear_get_http(self):
        res = self.client.get(reverse("compras:compra_crear"))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "compras/compra_form.html")
        self.assertIn("compra_token", res.context)

    def test_compra_linea_htmx(self):
        res = self.client.get(reverse("compras:compra_linea") + "?indice=3")
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "compras/partials/_linea_compra.html")
        self.assertContains(res, 'id="linea-3"')

    def test_compra_crear_post_valido_y_redireccion(self):
        # 1. Obtener formulario para generar token
        get_res = self.client.get(reverse("compras:compra_crear"))
        token = get_res.context["compra_token"]

        # 2. Enviar POST válido
        data = {
            "token_idempotencia": token,
            "proveedor": str(self.proveedor.pk),
            "fecha": datetime.date.today().isoformat(),
            "observacion": "Compra vía HTTP",
            "linea_producto": [str(self.prod1.pk)],
            "linea_cantidad": ["4"],
            "linea_costo": ["25.00"],
            "linea_vencimiento": [""],
        }
        post_res = self.client.post(reverse("compras:compra_crear"), data)
        self.assertEqual(post_res.status_code, 302)

        compra = Compra.objects.filter(observacion="Compra vía HTTP").first()
        self.assertIsNotNone(compra)
        self.assertRedirects(post_res, reverse("compras:compra_detalle", kwargs={"pk": compra.pk}))
        self.assertEqual(compra.total, Decimal("100.00"))

    def test_prevencion_envios_duplicados(self):
        """Si se envía un POST repetido con el mismo token, se rechaza y no se duplica la compra."""
        get_res = self.client.get(reverse("compras:compra_crear"))
        token = get_res.context["compra_token"]

        data = {
            "token_idempotencia": token,
            "proveedor": str(self.proveedor.pk),
            "fecha": datetime.date.today().isoformat(),
            "observacion": "Compra no duplicable",
            "linea_producto": [str(self.prod1.pk)],
            "linea_cantidad": ["2"],
            "linea_costo": ["10.00"],
            "linea_vencimiento": [""],
        }

        # Primer envío: exitoso
        res1 = self.client.post(reverse("compras:compra_crear"), data)
        self.assertEqual(res1.status_code, 302)
        self.assertEqual(Compra.objects.filter(observacion="Compra no duplicable").count(), 1)

        # Segundo envío idéntico (simulando doble clic o reenvío con el mismo token):
        res2 = self.client.post(reverse("compras:compra_crear"), data)
        self.assertEqual(res2.status_code, 302)
        # Sigue habiendo solo 1 compra registrada
        self.assertEqual(Compra.objects.filter(observacion="Compra no duplicable").count(), 1)

    def test_compra_crear_post_invalido(self):
        get_res = self.client.get(reverse("compras:compra_crear"))
        token = get_res.context["compra_token"]

        data = {
            "token_idempotencia": token,
            "proveedor": str(self.proveedor.pk),
            "fecha": datetime.date.today().isoformat(),
            "linea_producto": [str(self.prod1.pk)],
            "linea_cantidad": ["-3"],  # Cantidad inválida
            "linea_costo": ["10.00"],
            "linea_vencimiento": [""],
        }
        res = self.client.post(reverse("compras:compra_crear"), data)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "mayor o igual a 1")

    def test_compra_detalle_http(self):
        lineas = [{"producto": self.prod1, "cantidad": 2, "costo_unitario": Decimal("10.00")}]
        compra = services.registrar_compra(self.dueno, self.proveedor, lineas)

        res = self.client.get(reverse("compras:compra_detalle", kwargs={"pk": compra.pk}))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "compras/compra_detalle.html")
        self.assertContains(res, f"Compra #{compra.pk}")

        # 404 para compra inexistente
        res_404 = self.client.get(reverse("compras:compra_detalle", kwargs={"pk": 999999}))
        self.assertEqual(res_404.status_code, 404)

        # 403 para vendedor
        self.client.force_login(self.vendedor)
        res_vend = self.client.get(reverse("compras:compra_detalle", kwargs={"pk": compra.pk}))
        self.assertEqual(res_vend.status_code, 403)

    # --- 6. Seguridad: visualización de costos (ver_costos) ---------------------

    def test_ocultamiento_de_costos_sin_permiso_ver_costos(self):
        lineas = [{"producto": self.prod1, "cantidad": 2, "costo_unitario": Decimal("123.45")}]
        compra = services.registrar_compra(self.dueno, self.proveedor, lineas)

        # Dueño tiene ver_costos: ve el monto 123,45 y 246,90 (formato floatformat español)
        res_dueno = self.client.get(reverse("compras:compra_detalle", kwargs={"pk": compra.pk}))
        self.assertContains(res_dueno, "123,45")
        self.assertContains(res_dueno, "246,90")

        # Comprador sin ver_costos: no debe ver montos de costos ni total
        self.client.force_login(self.comprador_sin_costos)
        res_sin_costos = self.client.get(reverse("compras:compra_detalle", kwargs={"pk": compra.pk}))
        self.assertEqual(res_sin_costos.status_code, 200)
        self.assertNotContains(res_sin_costos, "123,45")
        self.assertNotContains(res_sin_costos, "246,90")

    # --- 7. Inmutabilidad de compras (RN-19) -----------------------------------

    def test_inmutabilidad_en_admin(self):
        compra_admin = admin.site._registry[Compra]
        detalle_admin = admin.site._registry[DetalleCompra]

        self.assertFalse(compra_admin.has_delete_permission(None))
        self.assertFalse(detalle_admin.has_delete_permission(None))

    # --- 8. Filtro por fechas en compra_lista ---------------------------------

    def test_filtro_fechas_compra_lista(self):
        hoy = datetime.date.today()
        hace_mes = hoy - datetime.timedelta(days=30)
        lineas = [{"producto": self.prod1, "cantidad": 1, "costo_unitario": Decimal("10.00")}]

        compra_hoy = services.registrar_compra(self.dueno, self.proveedor, lineas, observacion="Hoy", fecha=hoy)
        compra_mes = services.registrar_compra(self.dueno, self.proveedor, lineas, observacion="Hace un mes", fecha=hace_mes)

        # Filtrar solo hoy
        res = self.client.get(reverse("compras:compra_lista") + f"?desde={hoy.isoformat()}&hasta={hoy.isoformat()}")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Hoy")
        self.assertNotContains(res, "Hace un mes")

    def test_reenvio_tras_error_validacion_permite_guardar(self):
        """Un fallo de validación inicial permite corregir los datos y guardar la compra."""
        get_res = self.client.get(reverse("compras:compra_crear"))
        token_inicial = self.client.session.get("compra_token")

        # 1. Enviar con cantidad inválida (0)
        data_invalida = {
            "token_idempotencia": token_inicial,
            "proveedor": str(self.proveedor.pk),
            "fecha": datetime.date.today().isoformat(),
            "observacion": "Reintento corregido",
            "linea_producto": [str(self.prod1.pk)],
            "linea_cantidad": ["0"],
            "linea_costo": ["10.00"],
            "linea_vencimiento": [""],
        }
        res_error = self.client.post(reverse("compras:compra_crear"), data_invalida)
        self.assertEqual(res_error.status_code, 200)
        self.assertEqual(Compra.objects.filter(observacion="Reintento corregido").count(), 0)

        # El token se renueva en la sesión para el reenvío
        token_nuevo = self.client.session.get("compra_token")
        self.assertIsNotNone(token_nuevo)

        # 2. Corregir cantidad a 5 y reenviar con el nuevo token
        data_valida = data_invalida.copy()
        data_valida["token_idempotencia"] = token_nuevo
        data_valida["linea_cantidad"] = ["5"]

        res_ok = self.client.post(reverse("compras:compra_crear"), data_valida)
        self.assertEqual(res_ok.status_code, 302)
        compra = Compra.objects.filter(observacion="Reintento corregido").first()
        self.assertIsNotNone(compra)
        self.assertEqual(compra.detalles.first().cantidad_unidades, 5)


class ConcurrenciaComprasTests(TransactionTestCase):
    """Pruebas de concurrencia e idempotencia sobre conexiones independientes."""

    def setUp(self):
        call_command("cargar_datos_iniciales", stdout=StringIO())
        self.dueno = Usuario.objects.create_user("dueno_conc", rol=Rol.objects.get(nombre="Dueño"))
        self.cat = Categoria.objects.create(nombre="Cat Concurrente")
        self.prod = Producto.objects.create(
            codigo="CONC-01",
            nombre="Prod Concurrente",
            categoria=self.cat,
            creado_por=self.dueno,
            modificado_por=self.dueno,
        )
        self.prov = Proveedor.objects.create(
            nombre="Prov Concurrente",
            tipo=Proveedor.TipoProveedor.EMPRESA,
            creado_por=self.dueno,
            modificado_por=self.dueno,
        )
        self.client = Client()
        self.client.force_login(self.dueno)

    def test_post_simultaneo_concurrente_mismo_token(self):
        """Verifica que dos hilos simultáneos con el mismo token no duplican compras."""
        import threading
        from django.db import connections

        get_res = self.client.get(reverse("compras:compra_crear"))
        token = self.client.session.get("compra_token")
        session_id = self.client.cookies["sessionid"].value

        data = {
            "token_idempotencia": token,
            "proveedor": str(self.prov.pk),
            "fecha": datetime.date.today().isoformat(),
            "observacion": "Concurrencia thread test",
            "linea_producto": [str(self.prod.pk)],
            "linea_cantidad": ["3"],
            "linea_costo": ["15.00"],
            "linea_vencimiento": [""],
        }

        respuestas = []
        barrera = threading.Barrier(2)

        def enviar(idx):
            try:
                c = Client()
                c.cookies["sessionid"] = session_id
                barrera.wait(timeout=5)
                r = c.post(reverse("compras:compra_crear"), data)
                respuestas.append((idx, r.status_code, r.headers.get("Location", "")))
            finally:
                connections.close_all()

        t1 = threading.Thread(target=enviar, args=(1,))
        t2 = threading.Thread(target=enviar, args=(2,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # Debe haberse creado exactamente una compra
        compras = Compra.objects.filter(observacion="Concurrencia thread test")
        self.assertEqual(compras.count(), 1)

        # Ambas solicitudes terminan con 302 (una al detalle, la otra redirigida al listado)
        self.assertEqual(len(respuestas), 2)
        status_codes = [r[1] for r in respuestas]
        self.assertEqual(status_codes, [302, 302])
