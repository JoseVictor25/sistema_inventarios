"""Pruebas exhaustivas de Fase 6: Ventas, POS, Carrito, FEFO, Idempotencia y HTTP."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from threading import Barrier
from uuid import uuid4

from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from apps.caja import services as caja_servicios
from apps.caja.models import Caja
from apps.catalogo.models import Categoria, Presentacion, Producto
from apps.core.exceptions import ErrorDeNegocio
from apps.inventario.models import Lote, MovimientoInventario
from apps.usuarios.models import Permiso, Rol, Usuario
from apps.ventas import carrito as c
from apps.ventas import services as s
from apps.ventas.forms import leer_pagos
from apps.ventas.models import (
    DetalleVenta,
    DetalleVentaLote,
    MetodoPago,
    OperacionVenta,
    Pago,
    Venta,
)


def preparar_base_ventas():
    call_command("cargar_datos_iniciales", stdout=StringIO())
    dueno = Usuario.objects.create_user("dueno_test", password="123", rol=Rol.objects.get(nombre="Dueño"))
    vendedor = Usuario.objects.create_user("vendedor_test", password="123", rol=Rol.objects.get(nombre="Vendedor"))
    sin_permiso = Usuario.objects.create_user("sin_permiso", password="123")

    categoria = Categoria.objects.create(nombre="Suplementos")
    p1 = Producto.objects.create(codigo="COL-300", nombre="Colágeno 300g", categoria=categoria, stock_minimo=5)
    pres1_unidad = Presentacion.objects.create(producto=p1, nombre="Unidad", unidades_equivalentes=1, precio_venta=Decimal("50.00"))
    pres1_cuarta = Presentacion.objects.create(producto=p1, nombre="Cuarta", unidades_equivalentes=3, precio_venta=Decimal("135.00"))

    p2 = Producto.objects.create(codigo="ACE-250", nombre="Aceite de coco", categoria=categoria, stock_minimo=5)
    pres2_unidad = Presentacion.objects.create(producto=p2, nombre="Unidad", unidades_equivalentes=1, precio_venta=Decimal("35.00"))

    hoy = timezone.localdate()
    Lote.objects.create(producto=p1, codigo_lote="L-COL-01", cantidad_inicial=20, cantidad_actual=20, costo_unitario=Decimal("30.00"), fecha_vencimiento=hoy + timedelta(days=10))
    Lote.objects.create(producto=p1, codigo_lote="L-COL-02", cantidad_inicial=10, cantidad_actual=10, costo_unitario=Decimal("32.00"), fecha_vencimiento=hoy + timedelta(days=60))
    Lote.objects.create(producto=p2, codigo_lote="L-ACE-01", cantidad_inicial=15, cantidad_actual=15, costo_unitario=Decimal("20.00"), fecha_vencimiento=hoy + timedelta(days=30))

    return {
        "dueno": dueno,
        "vendedor": vendedor,
        "sin_permiso": sin_permiso,
        "p1": p1,
        "pres1_unidad": pres1_unidad,
        "pres1_cuarta": pres1_cuarta,
        "p2": p2,
        "pres2_unidad": pres2_unidad,
    }


class ServiciosVentasTests(TestCase):
    def setUp(self):
        self.datos = preparar_base_ventas()
        self.vendedor = self.datos["vendedor"]
        self.caja = caja_servicios.abrir_caja(self.vendedor, "100", "Mañana", clave=uuid4())
        self.efectivo = MetodoPago.objects.get(nombre="Efectivo")
        self.qr = MetodoPago.objects.get(nombre="QR")

    def test_venta_simple_exitosa(self):
        """Venta de 2 unidades descuenta stock FEFO, genera detalles, lotes y pago."""
        pres = self.datos["pres1_unidad"]
        lineas = [{"presentacion_id": pres.pk, "cantidad": 2}]
        pagos = [{"metodo_id": self.efectivo.pk, "monto": Decimal("100.00"), "referencia": ""}]
        clave = uuid4()

        venta = s.registrar_venta(self.vendedor, lineas, pagos, clave=clave)

        self.assertIsNotNone(venta.pk)
        self.assertEqual(venta.total, Decimal("100.00"))
        self.assertEqual(venta.caja.pk, self.caja.pk)
        self.assertEqual(venta.usuario.pk, self.vendedor.pk)

        # Detalles
        self.assertEqual(venta.detalles.count(), 1)
        det = venta.detalles.get()
        self.assertEqual(det.presentacion.pk, pres.pk)
        self.assertEqual(det.cantidad_presentaciones, 2)
        self.assertEqual(det.unidades_totales, 2)
        self.assertEqual(det.precio_aplicado, Decimal("50.00"))
        self.assertEqual(det.subtotal, Decimal("100.00"))

        # Desglose Lote
        self.assertEqual(det.salidas_lote.count(), 1)
        dvl = det.salidas_lote.get()
        self.assertEqual(dvl.lote.codigo_lote, "L-COL-01")
        self.assertEqual(dvl.cantidad_unidades, 2)

        # Movimiento inventario SALIDA
        mov = MovimientoInventario.objects.filter(lote=dvl.lote, motivo=f"Venta #{venta.pk}").first()
        self.assertIsNotNone(mov)
        self.assertEqual(mov.tipo, MovimientoInventario.TipoMovimiento.SALIDA)
        self.assertEqual(mov.cantidad, -2)

        # Pago
        self.assertEqual(venta.pagos.count(), 1)
        p = venta.pagos.get()
        self.assertEqual(p.metodo.pk, self.efectivo.pk)
        self.assertEqual(p.monto, Decimal("100.00"))

        # Stock descontado
        dvl.lote.refresh_from_db()
        self.assertEqual(dvl.lote.cantidad_actual, 18)

    def test_venta_presentacion_con_unidades_equivalentes(self):
        """Venta de 2 cuartas (3 u./cuarta = 6 unidades totales descontadas)."""
        pres = self.datos["pres1_cuarta"]
        lineas = [{"presentacion_id": pres.pk, "cantidad": 2}]
        pagos = [{"metodo_id": self.efectivo.pk, "monto": Decimal("270.00"), "referencia": ""}]

        venta = s.registrar_venta(self.vendedor, lineas, pagos, clave=uuid4())
        self.assertEqual(venta.total, Decimal("270.00"))
        det = venta.detalles.get()
        self.assertEqual(det.unidades_totales, 6)

        lote = Lote.objects.get(codigo_lote="L-COL-01")
        self.assertEqual(lote.cantidad_actual, 14)

    def test_venta_pagos_mixtos(self):
        """Venta con pago mixto: parte en Efectivo y parte en QR (RN-14)."""
        pres = self.datos["pres1_unidad"]
        lineas = [{"presentacion_id": pres.pk, "cantidad": 4}]  # 200 Bs
        pagos = [
            {"metodo_id": self.efectivo.pk, "monto": Decimal("120.00"), "referencia": ""},
            {"metodo_id": self.qr.pk, "monto": Decimal("80.00"), "referencia": "QR-9988"},
        ]

        venta = s.registrar_venta(self.vendedor, lineas, pagos, clave=uuid4())
        self.assertEqual(venta.total, Decimal("200.00"))
        self.assertEqual(venta.pagos.count(), 2)
        pago_ef = venta.pagos.get(metodo=self.efectivo)
        pago_qr = venta.pagos.get(metodo=self.qr)
        self.assertEqual(pago_ef.monto, Decimal("120.00"))
        self.assertEqual(pago_qr.monto, Decimal("80.00"))
        self.assertEqual(pago_qr.referencia, "QR-9988")

    def test_venta_sin_caja_abierta_rechazada(self):
        """RN-10: Rechaza venta si el usuario no tiene turno de caja abierto."""
        caja_servicios.cerrar_caja(self.vendedor, self.caja.pk, "100", clave=uuid4())
        pres = self.datos["pres1_unidad"]
        lineas = [{"presentacion_id": pres.pk, "cantidad": 1}]
        pagos = [{"metodo_id": self.efectivo.pk, "monto": Decimal("50.00")}]

        with self.assertRaises(ErrorDeNegocio) as ctx:
            s.registrar_venta(self.vendedor, lineas, pagos, clave=uuid4())
        self.assertIn("Abre tu turno de caja antes de vender", ctx.exception.mensaje)

    def test_venta_caja_ajena_rechazada(self):
        """No permite vender en la caja de otro usuario."""
        otro = Usuario.objects.create_user("otro_vend", password="123", rol=self.vendedor.rol)
        pres = self.datos["pres1_unidad"]
        lineas = [{"presentacion_id": pres.pk, "cantidad": 1}]
        pagos = [{"metodo_id": self.efectivo.pk, "monto": Decimal("50.00")}]

        with self.assertRaises(ErrorDeNegocio) as ctx:
            s.registrar_venta(otro, lineas, pagos, clave=uuid4())
        self.assertIn("Abre tu turno de caja antes de vender", ctx.exception.mensaje)

    def test_venta_total_cero_rechazada(self):
        """D4: Total == 0 se rechaza con ErrorDeNegocio."""
        pres = self.datos["pres1_unidad"]
        pres.precio_venta = Decimal("0.00")
        pres.save()

        lineas = [{"presentacion_id": pres.pk, "cantidad": 1}]
        pagos = [{"metodo_id": self.efectivo.pk, "monto": Decimal("0.00")}]

        with self.assertRaises(ErrorDeNegocio) as ctx:
            s.registrar_venta(self.vendedor, lineas, pagos, clave=uuid4())
        # Falla antes por monto de pago <= 0 o por total cero
        self.assertTrue(any(msg in ctx.exception.mensaje for msg in ("mayor que cero", "no puede ser cero")))

    def test_venta_pagos_no_coinciden_total_rechazada(self):
        """RN-14: La suma de pagos debe coincidir exactamente con el total."""
        pres = self.datos["pres1_unidad"]
        lineas = [{"presentacion_id": pres.pk, "cantidad": 2}]  # Total: 100
        pagos = [{"metodo_id": self.efectivo.pk, "monto": Decimal("90.00")}]

        with self.assertRaises(ErrorDeNegocio) as ctx:
            s.registrar_venta(self.vendedor, lineas, pagos, clave=uuid4())
        self.assertIn("no coincide con el total", ctx.exception.mensaje)

    def test_idempotencia_misma_clave_mismos_datos(self):
        """Reenviar la misma clave con los mismos datos devuelve la venta previa sin duplicar."""
        pres = self.datos["pres1_unidad"]
        lineas = [{"presentacion_id": pres.pk, "cantidad": 1}]
        pagos = [{"metodo_id": self.efectivo.pk, "monto": Decimal("50.00"), "referencia": ""}]
        clave = uuid4()

        v1 = s.registrar_venta(self.vendedor, lineas, pagos, clave=clave)
        v2 = s.registrar_venta(self.vendedor, lineas, pagos, clave=clave)

        self.assertEqual(v1.pk, v2.pk)
        self.assertEqual(Venta.objects.count(), 1)
        self.assertEqual(DetalleVenta.objects.count(), 1)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(OperacionVenta.objects.count(), 1)

        lote = Lote.objects.get(codigo_lote="L-COL-01")
        self.assertEqual(lote.cantidad_actual, 19)  # solo 1 unidad descontada, no 2

    def test_idempotencia_misma_clave_datos_distintos_rechazada(self):
        """Reutilizar una clave con otros datos lanza ErrorDeNegocio."""
        pres = self.datos["pres1_unidad"]
        clave = uuid4()

        s.registrar_venta(self.vendedor, [{"presentacion_id": pres.pk, "cantidad": 1}],
                          [{"metodo_id": self.efectivo.pk, "monto": Decimal("50.00")}], clave=clave)

        with self.assertRaises(ErrorDeNegocio) as ctx:
            s.registrar_venta(self.vendedor, [{"presentacion_id": pres.pk, "cantidad": 2}],
                              [{"metodo_id": self.efectivo.pk, "monto": Decimal("100.00")}], clave=clave)
        self.assertIn("La clave ya fue utilizada con otros datos", ctx.exception.mensaje)

    def test_idempotencia_claves_distintas_permite_ventas_identicas(self):
        """Claves distintas permiten dos ventas legítimas con los mismos productos."""
        pres = self.datos["pres1_unidad"]
        lineas = [{"presentacion_id": pres.pk, "cantidad": 1}]
        pagos = [{"metodo_id": self.efectivo.pk, "monto": Decimal("50.00")}]

        v1 = s.registrar_venta(self.vendedor, lineas, pagos, clave=uuid4())
        v2 = s.registrar_venta(self.vendedor, lineas, pagos, clave=uuid4())

        self.assertNotEqual(v1.pk, v2.pk)
        self.assertEqual(Venta.objects.count(), 2)

    def test_idempotencia_recupera_venta_con_carrito_vacio(self):
        """Si la venta ya fue confirmada, reintentar con carrito vacío recupera la venta previa."""
        pres = self.datos["pres1_unidad"]
        lineas = [{"presentacion_id": pres.pk, "cantidad": 1}]
        pagos = [{"metodo_id": self.efectivo.pk, "monto": Decimal("50.00")}]
        clave = uuid4()

        v1 = s.registrar_venta(self.vendedor, lineas, pagos, clave=clave)
        # Simular reintento de cliente cuando el carrito en sesión ya se vació (lineas=[])
        v2 = s.registrar_venta(self.vendedor, [], pagos, clave=clave)

        self.assertEqual(v1.pk, v2.pk)
        self.assertEqual(Venta.objects.count(), 1)

    def test_rollback_atomico_ante_stock_insuficiente(self):
        """Si alguna línea falla por stock, nada se persiste ni descuenta."""
        pres1 = self.datos["pres1_unidad"]  # Stock 30
        pres2 = self.datos["pres2_unidad"]  # Stock 15

        # Pedir 5 de pres1 y 20 de pres2 (pres2 solo tiene 15)
        lineas = [
            {"presentacion_id": pres1.pk, "cantidad": 5},
            {"presentacion_id": pres2.pk, "cantidad": 20},
        ]
        # Total sería 5*50 + 20*35 = 250 + 700 = 950
        pagos = [{"metodo_id": self.efectivo.pk, "monto": Decimal("950.00")}]

        with self.assertRaises(ErrorDeNegocio):
            s.registrar_venta(self.vendedor, lineas, pagos, clave=uuid4())

        self.assertEqual(Venta.objects.count(), 0)
        self.assertEqual(DetalleVenta.objects.count(), 0)
        self.assertEqual(Pago.objects.count(), 0)
        self.assertEqual(MovimientoInventario.objects.count(), 0)
        self.assertEqual(Lote.objects.get(codigo_lote="L-COL-01").cantidad_actual, 20)
        self.assertEqual(Lote.objects.get(codigo_lote="L-ACE-01").cantidad_actual, 15)

    def test_aislamiento_caja_dueno_abierta_vendedor_sin_caja(self):
        """Si el Dueño tiene caja abierta pero el Vendedor no tiene ninguna, el Vendedor no puede vender."""
        caja_servicios.cerrar_caja(self.vendedor, self.caja.pk, "100", clave=uuid4())
        caja_dueno = caja_servicios.abrir_caja(self.datos["dueno"], "200.00", "Turno Dueño", clave=uuid4())

        ventas_ini = Venta.objects.count()
        pagos_ini = Pago.objects.count()
        movs_ini = MovimientoInventario.objects.count()
        lote_ini = Lote.objects.get(codigo_lote="L-COL-01").cantidad_actual

        pres = self.datos["pres1_unidad"]
        lineas = [{"presentacion_id": pres.pk, "cantidad": 2}]
        pagos = [{"metodo_id": self.efectivo.pk, "monto": Decimal("100.00")}]

        with self.assertRaises(ErrorDeNegocio) as ctx:
            s.registrar_venta(self.vendedor, lineas, pagos, clave=uuid4())

        self.assertIn("Abre tu turno de caja antes de vender", ctx.exception.mensaje)
        self.assertEqual(Venta.objects.count(), ventas_ini)
        self.assertEqual(Pago.objects.count(), pagos_ini)
        self.assertEqual(MovimientoInventario.objects.count(), movs_ini)
        self.assertEqual(Lote.objects.get(codigo_lote="L-COL-01").cantidad_actual, lote_ini)
        caja_dueno.refresh_from_db()
        self.assertEqual(caja_dueno.estado, Caja.EstadoCaja.ABIERTA)

    def test_pagos_mixtos_formulario_qr_y_efectivo_sin_guardar_vuelto(self):
        """RN-14: Pagos mixtos (QR + Efectivo) registran solo importes aplicados; vuelto no se persiste."""
        from django.http import QueryDict

        pres = self.datos["pres1_unidad"]
        lineas = [{"presentacion_id": pres.pk, "cantidad": 4}]  # 200.00

        post_data = QueryDict(mutable=True)
        post_data.setlist("metodo_id", [str(self.qr.pk), str(self.efectivo.pk)])
        post_data.setlist("monto", ["120,00", "80,00"])  # probado con comas decimales
        post_data.setlist("referencia", ["QR-TRANSF-101", ""])
        post_data["monto_recibido"] = "100.00"  # Recibió 100 para cubrir 80 de efectivo -> Vuelto 20

        pagos = leer_pagos(post_data, total_venta=Decimal("200.00"))
        self.assertEqual(len(pagos), 2)
        self.assertEqual(pagos[0]["monto"], Decimal("120.00"))
        self.assertEqual(pagos[1]["monto"], Decimal("80.00"))

        venta = s.registrar_venta(self.vendedor, lineas, pagos, clave=uuid4())
        self.assertEqual(venta.total, Decimal("200.00"))
        self.assertEqual(venta.pagos.count(), 2)

        pago_qr = venta.pagos.get(metodo=self.qr)
        pago_ef = venta.pagos.get(metodo=self.efectivo)
        self.assertEqual(pago_qr.monto, Decimal("120.00"))
        self.assertEqual(pago_ef.monto, Decimal("80.00"))
        self.assertFalse(venta.pagos.filter(monto=Decimal("20.00")).exists())

    def test_pagos_metodo_duplicado_rechazado(self):
        """No permite duplicar el mismo método de pago en una venta."""
        from django.http import QueryDict

        post_data = QueryDict(mutable=True)
        post_data.setlist("metodo_id", [str(self.qr.pk), str(self.qr.pk)])
        post_data.setlist("monto", ["50.00", "50.00"])

        with self.assertRaises(ErrorDeNegocio) as ctx:
            leer_pagos(post_data, total_venta=Decimal("100.00"))
        self.assertIn("No se permite duplicar el mismo método de pago", ctx.exception.mensaje)

        pagos_duplicados = [
            {"metodo_id": self.qr.pk, "monto": Decimal("50.00")},
            {"metodo_id": self.qr.pk, "monto": Decimal("50.00")},
        ]
        with self.assertRaises(ErrorDeNegocio) as ctx_s:
            s.registrar_venta(
                self.vendedor,
                [{"presentacion_id": self.datos["pres1_unidad"].pk, "cantidad": 2}],
                pagos_duplicados,
                clave=uuid4(),
            )
        self.assertIn("No se permite duplicar el mismo método de pago", ctx_s.exception.mensaje)

    def test_pagos_monto_invalido_o_negativo_rechazado(self):
        """Monto de pago negativo o inválido se rechaza con ErrorDeNegocio."""
        pres = self.datos["pres1_unidad"]
        lineas = [{"presentacion_id": pres.pk, "cantidad": 1}]

        with self.assertRaises(ErrorDeNegocio) as ctx:
            s.registrar_venta(
                self.vendedor,
                lineas,
                [{"metodo_id": self.efectivo.pk, "monto": Decimal("-10.00")}],
                clave=uuid4(),
            )
        self.assertIn("mayor que cero", ctx.exception.mensaje)

        with self.assertRaises(ErrorDeNegocio):
            s.registrar_venta(
                self.vendedor,
                lineas,
                [{"metodo_id": self.efectivo.pk, "monto": "invalido"}],
                clave=uuid4(),
            )

    def test_leer_pagos_soporta_coma_decimal_y_pago_simple(self):
        """leer_pagos convierte cadenas con coma a Decimal de forma exacta."""
        from django.http import QueryDict

        post_data = QueryDict(mutable=True)
        post_data["metodo_id"] = str(self.efectivo.pk)
        post_data["monto"] = "540,50"

        pagos = leer_pagos(post_data, total_venta=Decimal("540.50"))
        self.assertEqual(len(pagos), 1)
        self.assertEqual(pagos[0]["monto"], Decimal("540.50"))


class CarritoSesionTests(TestCase):
    def setUp(self):
        self.datos = preparar_base_ventas()
        self.session = {}

    def test_agregar_actualizar_quitar_vaciar(self):
        pres1 = self.datos["pres1_unidad"]
        pres2 = self.datos["pres2_unidad"]

        # Agregar
        c.agregar_linea(self.session, pres1.pk, 2)
        car = c.enriquecer_carrito(self.session)
        self.assertEqual(len(car["lineas"]), 1)
        self.assertEqual(car["total"], Decimal("100.00"))
        self.assertEqual(car["unidades_totales"], 2)

        # Agregar existente suma cantidad
        c.agregar_linea(self.session, pres1.pk, 1)
        car = c.enriquecer_carrito(self.session)
        self.assertEqual(car["lineas"][0]["cantidad"], 3)
        self.assertEqual(car["total"], Decimal("150.00"))

        # Agregar segundo producto
        c.agregar_linea(self.session, pres2.pk, 1)
        car = c.enriquecer_carrito(self.session)
        self.assertEqual(len(car["lineas"]), 2)
        self.assertEqual(car["total"], Decimal("185.00"))

        # Cambiar cantidad
        c.cambiar_cantidad(self.session, 0, 1)
        car = c.enriquecer_carrito(self.session)
        self.assertEqual(car["lineas"][0]["cantidad"], 1)
        self.assertEqual(car["total"], Decimal("85.00"))

        # Cambiar presentación
        c.cambiar_presentacion(self.session, 0, self.datos["pres1_cuarta"].pk)
        car = c.enriquecer_carrito(self.session)
        self.assertEqual(car["lineas"][0]["presentacion"].pk, self.datos["pres1_cuarta"].pk)
        self.assertEqual(car["total"], Decimal("170.00"))  # 135 + 35

        # Quitar línea
        c.quitar_linea(self.session, 0)
        car = c.enriquecer_carrito(self.session)
        self.assertEqual(len(car["lineas"]), 1)

        # Vaciar
        clave_vieja = car["clave"]
        c.vaciar_carrito(self.session)
        car_vacio = c.enriquecer_carrito(self.session)
        self.assertEqual(len(car_vacio["lineas"]), 0)
        self.assertEqual(car_vacio["total"], Decimal("0.00"))
        self.assertNotEqual(car_vacio["clave"], clave_vieja)


class VistasVentasHTTPTests(TestCase):
    def setUp(self):
        self.datos = preparar_base_ventas()
        self.vendedor = self.datos["vendedor"]
        self.dueno = self.datos["dueno"]
        self.sin_permiso = self.datos["sin_permiso"]
        self.caja = caja_servicios.abrir_caja(self.vendedor, "100", "Turno 1", clave=uuid4())
        self.client = Client()
        self.client.force_login(self.vendedor)
        self.efectivo = MetodoPago.objects.get(nombre="Efectivo")

    def test_pos_view_permiso_requerido(self):
        """Usuarios sin permiso 'vender' reciben 403."""
        self.client.force_login(self.sin_permiso)
        res = self.client.get("/ventas/nueva/")
        self.assertEqual(res.status_code, 403)

    def test_pos_view_autorizada(self):
        """POS responde 200 con caja y metodos_pago en contexto."""
        res = self.client.get("/ventas/nueva/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("caja", res.context)
        self.assertIn("carrito", res.context)
        self.assertIn("metodos_pago", res.context)

    def test_buscar_productos_htmx(self):
        """Buscador responde 200 con fragmento _lista_productos.html."""
        res = self.client.get("/ventas/buscar/?q=Colágeno")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Colágeno 300g")
        self.assertContains(res, "id=\"lista-productos\"")

    def test_ciclo_carrito_htmx(self):
        """Flujo completo HTMX: agregar, actualizar, quitar, vaciar."""
        pres = self.datos["pres1_unidad"]

        # Agregar
        res = self.client.post("/ventas/carrito/agregar/", {"presentacion_id": pres.pk, "cantidad": 2})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Colágeno 300g")
        self.assertContains(res, "100")

        # Actualizar cantidad
        res = self.client.post("/ventas/carrito/actualizar/", {"indice": 0, "cantidad": 3})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "150")

        # Quitar
        res = self.client.post("/ventas/carrito/quitar/", {"indice": 0})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Toca un producto de la lista")

    def test_confirmar_venta_htmx_exito_y_error(self):
        """Confirmar venta responde 200 con confirmación o 422 con error."""
        pres = self.datos["pres1_unidad"]
        self.client.post("/ventas/carrito/agregar/", {"presentacion_id": pres.pk, "cantidad": 1})

        # Confirmación exitosa
        res = self.client.post("/ventas/confirmar/", {
            "metodo_id": self.efectivo.pk,
            "monto": "50.00",
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Venta registrada con éxito")

        # Intentar confirmar carrito vacío responde 422
        res2 = self.client.post("/ventas/confirmar/", {
            "metodo_id": self.efectivo.pk,
            "monto": "50.00",
        })
        self.assertEqual(res2.status_code, 422)
        self.assertContains(res2, "Agrega al menos un producto a la venta", status_code=422)

    def test_ventas_lista_y_detalle(self):
        """Historial y detalle de venta responden 200 inmutables."""
        pres = self.datos["pres1_unidad"]
        s.registrar_venta(self.vendedor, [{"presentacion_id": pres.pk, "cantidad": 1}],
                          [{"metodo_id": self.efectivo.pk, "monto": Decimal("50.00")}], clave=uuid4())
        venta = Venta.objects.first()

        res_lista = self.client.get("/ventas/")
        self.assertEqual(res_lista.status_code, 200)
        self.assertContains(res_lista, f"#{venta.pk}")

        res_detalle = self.client.get(f"/ventas/{venta.pk}/")
        self.assertEqual(res_detalle.status_code, 200)
        self.assertContains(res_detalle, "Líneas de venta y trazabilidad FEFO")
        # El vendedor no tiene ver_costos, por lo que no debe ver el costo del lote
        self.assertNotContains(res_detalle, "costo:")

        # Dueño sí tiene ver_costos y debe ver costo:
        self.client.force_login(self.dueno)
        res_dueno = self.client.get(f"/ventas/{venta.pk}/")
        self.assertEqual(res_dueno.status_code, 200)
        self.assertContains(res_dueno, "costo:")


class ConcurrenciaVentasTests(TransactionTestCase):
    def setUp(self):
        self.datos = preparar_base_ventas()
        self.vendedor = self.datos["vendedor"]
        self.caja = caja_servicios.abrir_caja(self.vendedor, "100", "Turno Concurrente", clave=uuid4())
        self.efectivo = MetodoPago.objects.get(nombre="Efectivo")

    def test_concurrencia_misma_clave_no_duplica_venta(self):
        """Dos hilos concurrentes con la misma clave no duplican venta ni descuentos."""
        clave = uuid4()
        pres = self.datos["pres1_unidad"]
        lineas = [{"presentacion_id": pres.pk, "cantidad": 2}]
        pagos = [{"metodo_id": self.efectivo.pk, "monto": Decimal("100.00"), "referencia": ""}]
        usuario_id = self.vendedor.pk
        barrera = Barrier(2)

        def intentar_venta():
            connections.close_all()
            try:
                usuario = Usuario.objects.get(pk=usuario_id)
                conexion = connections["default"]
                conexion.ensure_connection()
                identidad = id(conexion.connection)
                barrera.wait(timeout=10)
                try:
                    v = s.registrar_venta(usuario, lineas, pagos, clave=clave)
                    return identidad, True, v.pk
                except ErrorDeNegocio as error:
                    return identidad, False, error.mensaje
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            f1 = ejecutor.submit(intentar_venta)
            f2 = ejecutor.submit(intentar_venta)
            r1 = f1.result()
            r2 = f2.result()

        # Ambos hilos terminan exitosos o recuperan el mismo ID de venta
        self.assertEqual(Venta.objects.count(), 1)
        self.assertEqual(OperacionVenta.objects.count(), 1)
        self.assertEqual(DetalleVenta.objects.count(), 1)

        lote = Lote.objects.get(codigo_lote="L-COL-01")
        self.assertEqual(lote.cantidad_actual, 18)  # Solo se descontaron 2 unidades
