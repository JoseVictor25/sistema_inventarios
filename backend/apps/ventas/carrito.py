"""Carrito de ventas almacenado en sesión (§8.1, §9.6)."""
from decimal import Decimal
import uuid

from django.db.models import F
from django.utils import timezone

from apps.catalogo.models import Presentacion
from apps.core.exceptions import ErrorDeNegocio
from apps.inventario.models import Lote

SESSION_KEY = "carrito_ventas"


def _marcar_modificado(session):
    if hasattr(session, "modified"):
        session.modified = True


def _obtener_datos_sesion(session):
    carrito = session.get(SESSION_KEY)
    if not isinstance(carrito, dict):
        carrito = {
            "lineas": [],
            "clave": str(uuid.uuid4()),
        }
        session[SESSION_KEY] = carrito
        _marcar_modificado(session)
    elif "clave" not in carrito or not carrito["clave"]:
        carrito["clave"] = str(uuid.uuid4())
        session[SESSION_KEY] = carrito
        _marcar_modificado(session)
    return carrito


def obtener_carrito(session):
    """Devuelve el carrito crudo almacenado en la sesión."""
    return _obtener_datos_sesion(session)


def obtener_clave(session):
    """Obtiene la clave UUID de idempotencia asociada al carrito actual."""
    return _obtener_datos_sesion(session)["clave"]


def renovar_clave(session):
    """Genera una nueva clave UUID para el carrito."""
    carrito = _obtener_datos_sesion(session)
    carrito["clave"] = str(uuid.uuid4())
    session[SESSION_KEY] = carrito
    _marcar_modificado(session)
    return carrito["clave"]


def agregar_linea(session, presentacion_id, cantidad=1):
    """Agrega una presentación al carrito o incrementa su cantidad si ya existe.

    Pasos:
        1. Validar que la presentación exista y esté activa.
        2. Validar que la cantidad sea un entero >= 1.
        3. Comprobar que el producto tenga stock disponible (D5).
        4. Si ya está en el carrito, sumar la cantidad; si no, agregar nueva línea.
    """
    try:
        presentacion = Presentacion.objects.select_related("producto").get(pk=presentacion_id)
    except (Presentacion.DoesNotExist, ValueError, TypeError):
        raise ErrorDeNegocio("La presentación seleccionada no existe.") from None

    if not presentacion.activa or not presentacion.producto.activo:
        raise ErrorDeNegocio("El producto o presentación no está activo.")

    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad < 1:
        raise ErrorDeNegocio("La cantidad debe ser un número entero mayor o igual a 1.")

    stock = presentacion.producto.stock_actual
    if stock <= 0:
        raise ErrorDeNegocio(f"No hay stock disponible de {presentacion.producto.nombre}.")

    carrito = _obtener_datos_sesion(session)
    lineas = carrito.setdefault("lineas", [])

    encontrada = False
    for linea in lineas:
        if linea.get("presentacion_id") == presentacion.pk:
            linea["cantidad"] = linea.get("cantidad", 1) + cantidad
            encontrada = True
            break

    if not encontrada:
        lineas.append({
            "presentacion_id": presentacion.pk,
            "cantidad": cantidad,
        })

    session[SESSION_KEY] = carrito
    _marcar_modificado(session)
    return carrito


def cambiar_cantidad(session, indice, cantidad):
    """Actualiza la cantidad de una línea específica del carrito."""
    if not isinstance(cantidad, int) or isinstance(cantidad, bool) or cantidad < 1:
        raise ErrorDeNegocio("La cantidad debe ser un número entero mayor o igual a 1.")

    carrito = _obtener_datos_sesion(session)
    lineas = carrito.get("lineas", [])

    if not isinstance(indice, int) or indice < 0 or indice >= len(lineas):
        raise ErrorDeNegocio("La línea del carrito indicada no existe.")

    lineas[indice]["cantidad"] = cantidad
    session[SESSION_KEY] = carrito
    _marcar_modificado(session)
    return carrito


def cambiar_presentacion(session, indice, presentacion_id):
    """Cambia la presentación de una línea específica del carrito."""
    try:
        presentacion = Presentacion.objects.select_related("producto").get(pk=presentacion_id)
    except (Presentacion.DoesNotExist, ValueError, TypeError):
        raise ErrorDeNegocio("La presentación seleccionada no existe.") from None

    if not presentacion.activa or not presentacion.producto.activo:
        raise ErrorDeNegocio("El producto o presentación no está activo.")

    carrito = _obtener_datos_sesion(session)
    lineas = carrito.get("lineas", [])

    if not isinstance(indice, int) or indice < 0 or indice >= len(lineas):
        raise ErrorDeNegocio("La línea del carrito indicada no existe.")

    lineas[indice]["presentacion_id"] = presentacion.pk
    session[SESSION_KEY] = carrito
    _marcar_modificado(session)
    return carrito


def quitar_linea(session, indice):
    """Elimina una línea del carrito según su índice."""
    carrito = _obtener_datos_sesion(session)
    lineas = carrito.get("lineas", [])

    if not isinstance(indice, int) or indice < 0 or indice >= len(lineas):
        raise ErrorDeNegocio("La línea del carrito indicada no existe.")

    lineas.pop(indice)
    session[SESSION_KEY] = carrito
    _marcar_modificado(session)
    return carrito


def vaciar_carrito(session):
    """Vacía todas las líneas del carrito y regenera la clave de idempotencia."""
    carrito = {
        "lineas": [],
        "clave": str(uuid.uuid4()),
    }
    session[SESSION_KEY] = carrito
    _marcar_modificado(session)
    return carrito


def enriquecer_carrito(session_o_carrito):
    """Convierte las líneas crudas en la estructura completa requerida por _carrito.html.

    Estructura requerida (§9.6):
    {
      "lineas": [
        {
          "indice": 0,
          "presentacion": <obj>,
          "producto": <obj>,
          "cantidad": 2,
          "unidades": 24,
          "precio": Decimal("480.00"),
          "subtotal": Decimal("960.00"),
          "lote_proximo": <obj o None>,
        }
      ],
      "total": Decimal("960.00"),
      "unidades_totales": 24,
      "clave": "uuid...",
    }
    """
    if hasattr(session_o_carrito, "get"):
        if "lineas" in session_o_carrito:
            carrito_crudo = session_o_carrito
        else:
            carrito_crudo = _obtener_datos_sesion(session_o_carrito)
    else:
        carrito_crudo = {"lineas": [], "clave": str(uuid.uuid4())}

    lineas_crudas = carrito_crudo.get("lineas", [])
    clave = carrito_crudo.get("clave") or str(uuid.uuid4())

    ids_pres = [l["presentacion_id"] for l in lineas_crudas if "presentacion_id" in l]
    pres_map = {
        p.pk: p
        for p in Presentacion.objects.filter(pk__in=ids_pres)
        .select_related("producto", "producto__categoria")
        .prefetch_related("producto__presentaciones")
    }

    lineas_enriquecidas = []
    total = Decimal("0.00")
    unidades_totales = 0

    for i, l in enumerate(lineas_crudas):
        pid = l.get("presentacion_id")
        cant = l.get("cantidad", 1)
        pres = pres_map.get(pid)
        if not pres:
            continue

        precio = pres.precio_venta
        unidades = cant * pres.unidades_equivalentes
        subtotal = precio * cant

        # Lote más próximo para visualización según mockup §9.11
        lote_proximo = (
            Lote.objects.filter(producto=pres.producto, cantidad_actual__gt=0)
            .exclude(fecha_vencimiento__lt=timezone.localdate())
            .order_by(F("fecha_vencimiento").asc(nulls_last=True), "id")
            .first()
        )

        lineas_enriquecidas.append({
            "indice": i,
            "presentacion": pres,
            "producto": pres.producto,
            "cantidad": cant,
            "unidades": unidades,
            "precio": precio,
            "subtotal": subtotal,
            "lote_proximo": lote_proximo,
        })
        total += subtotal
        unidades_totales += unidades

    return {
        "lineas": lineas_enriquecidas,
        "total": total,
        "unidades_totales": unidades_totales,
        "clave": clave,
    }
