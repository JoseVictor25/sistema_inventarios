"""Catálogo transaccional: RN-02, RN-03, RN-04, RN-08, RN-17, RN-18 y RN-21."""
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from apps.auditoria import services as auditoria
from apps.core.exceptions import ErrorDeNegocio
from apps.core.operaciones import asignar_campos, autorizar, operacion
from apps.core.utils import asignar_auditoria
from apps.core.validators import validar_cantidad, validar_dinero
from .models import AtributoProducto, Categoria, Presentacion, Producto

CAMPOS_PRODUCTO = ("codigo", "nombre", "descripcion", "categoria", "stock_minimo", "activo")
CAMPOS_PRESENTACION = ("nombre", "unidades_equivalentes", "precio_venta", "activa")
CAMPOS_CATEGORIA = ("nombre", "padre", "activa")
CAMPOS_ATRIBUTO = ("nombre", "valor")


def _guardar(objeto, usuario):
    if hasattr(objeto, "creado_por"):
        asignar_auditoria(objeto, usuario)
    objeto.full_clean()
    objeto.save()
    return objeto


@operacion("gestionar_catalogo")
def guardar_categoria(usuario, datos, categoria_id=None):
    """Crea o edita una categoría sin cascadas.

    Pasos:
        1. Recuperar el estado actual y asignar campos permitidos.
        2. Validar ciclos/unicidad y guardar.
    Lanza:
        ErrorDeNegocio: ciclo, duplicado o campos inválidos.
    """
    # Paso 1: se relee el objeto, sin confiar en instancias alteradas por formularios.
    categoria = Categoria.objects.get(pk=categoria_id) if categoria_id else Categoria()
    asignar_campos(categoria, datos, CAMPOS_CATEGORIA)
    # Paso 2: clean recorre los ancestros; las restricciones cubren duplicados.
    return _guardar(categoria, usuario)


def mover_categoria(categoria, nuevo_padre, *, usuario):
    """Mueve una categoría mediante el servicio autorizado.

    Pasos:
        1. Delegar la validación del árbol y la escritura atómica.
    Lanza:
        ErrorDeNegocio: padre propio, descendiente o nombre duplicado.
    """
    # Paso 1: conservar el contrato de movimiento y exigir un actor autorizado.
    return guardar_categoria(usuario, {"padre": nuevo_padre}, categoria.pk)


def _categoria_producto(producto, categoria_anterior=None):
    categoria = Categoria.objects.get(pk=producto.categoria_id)
    if not categoria.activa and categoria.pk != categoria_anterior:
        raise ErrorDeNegocio("Selecciona una categoría activa.", "categoria")
    if isinstance(producto.stock_minimo, bool) or not isinstance(producto.stock_minimo, int):
        raise ErrorDeNegocio("El stock mínimo debe ser un entero mayor o igual a cero.", "stock_minimo")


def _nueva_presentacion(usuario, producto, datos):
    presentacion = Presentacion(producto=producto)
    asignar_campos(presentacion, datos, CAMPOS_PRESENTACION)
    validar_cantidad(presentacion.unidades_equivalentes)
    validar_dinero(presentacion.precio_venta)
    return _guardar(presentacion, usuario)


@operacion("gestionar_catalogo")
def crear_producto(usuario, datos, presentaciones):
    """Crea el producto completo o no guarda nada (RN-03).

    Pasos:
        1. Validar campos, categoría y existencia de presentaciones.
        2. Guardar producto y todas las presentaciones en una transacción.
    Lanza:
        ErrorDeNegocio: código duplicado, categoría inactiva o presentación inválida.
    """
    # Paso 1: no se impone nombre Unidad ni una presentación activa adicional.
    if not presentaciones:
        raise ErrorDeNegocio("Agrega al menos una presentación.")
    producto = Producto()
    asignar_campos(producto, datos, CAMPOS_PRODUCTO)
    _categoria_producto(producto)
    # Paso 2: el decorador revierte también el producto si una línea falla.
    _guardar(producto, usuario)
    for datos_presentacion in presentaciones:
        _nueva_presentacion(usuario, producto, datos_presentacion)
    return producto


@operacion("gestionar_catalogo")
def cambiar_precio(usuario, presentacion, nuevo_precio):
    """Actualiza precio y bitácora juntos sin tocar ventas (RN-08, RN-21).

    Pasos:
        1. Validar dinero y releer el precio persistido.
        2. Actualizar condicionalmente y registrar los dos valores.
    Lanza:
        ErrorDeNegocio: precio inválido o conflicto concurrente.
    """
    # Paso 1: el anterior nunca se toma del formulario ni de una instancia obsoleta.
    validar_dinero(nuevo_precio)
    actual = Presentacion.objects.get(pk=presentacion.pk)
    anterior = actual.precio_venta
    actual.precio_venta = nuevo_precio
    actual.full_clean()
    # Paso 2: comparación explícita; no se presupone bloqueo por fila en SQLite.
    if anterior != nuevo_precio:
        cantidad = Presentacion.objects.filter(pk=actual.pk, precio_venta=anterior).update(
            precio_venta=nuevo_precio, modificado_por=usuario, modificado_en=timezone.now())
        if cantidad != 1:
            raise ErrorDeNegocio("El precio cambió en otra operación. Actualiza la página.")
        auditoria.registrar_cambio(usuario, "CAMBIO_PRECIO", "Presentacion", actual.pk,
                                  {"precio_venta": str(anterior)}, {"precio_venta": format(nuevo_precio, ".2f")})
    actual.refresh_from_db()
    return actual


@operacion("gestionar_catalogo")
def editar_producto(usuario, producto_id, datos, presentaciones):
    """Edita sin borrar ni trasladar presentaciones y audita cada precio.

    Pasos:
        1. Validar producto y correspondencia completa de las presentaciones.
        2. Guardar campos y presentaciones con precios centralizados.
    Lanza:
        ErrorDeNegocio: identificadores manipulados, omisiones o datos inválidos.
    """
    # Paso 1: se exige conservar exactamente las presentaciones existentes.
    producto = Producto.objects.get(pk=producto_id)
    categoria_anterior = producto.categoria_id
    asignar_campos(producto, datos, CAMPOS_PRODUCTO)
    _categoria_producto(producto, categoria_anterior)
    existentes = set(producto.presentaciones.values_list("pk", flat=True))
    enviados = [p["id"] for p in presentaciones if p.get("id") is not None]
    if not presentaciones or set(enviados) != existentes or len(enviados) != len(set(enviados)):
        raise ErrorDeNegocio("Las presentaciones cambiaron o no pertenecen a este producto. Recarga la página.")
    # Paso 2: nunca se ejecuta formset.save ni una eliminación implícita.
    _guardar(producto, usuario)
    for entrada in presentaciones:
        valores = dict(entrada)
        pk = valores.pop("id", None)
        if pk is None:
            _nueva_presentacion(usuario, producto, valores)
        else:
            actual = producto.presentaciones.get(pk=pk)
            precio = valores.pop("precio_venta")
            asignar_campos(actual, valores, ("nombre", "unidades_equivalentes", "activa"))
            validar_cantidad(actual.unidades_equivalentes)
            _guardar(actual, usuario)
            cambiar_precio(usuario, actual, precio)
    return producto


@operacion("gestionar_catalogo")
def agregar_presentacion(usuario, producto_id, datos):
    """Añade una presentación sin modificar las existentes.

    Pasos:
        1. Recuperar producto y validar/guardar la presentación.
    Lanza:
        ErrorDeNegocio: producto inexistente o presentación inválida/duplicada.
    """
    # Paso 1: producto fijado por la ruta, nunca por un campo editable.
    return _nueva_presentacion(usuario, Producto.objects.get(pk=producto_id), datos)


@operacion("gestionar_catalogo")
def desactivar_producto(usuario, producto):
    """Desactiva sin borrar historial (RN-17).

    Pasos:
        1. Releer, marcar inactivo y guardar autoría.
    Lanza:
        ErrorDeNegocio: producto inexistente.
    """
    # Paso 1: ni las presentaciones ni lotes reciben cambios en cascada.
    actual = Producto.objects.get(pk=producto.pk)
    actual.activo = False
    return _guardar(actual, usuario)


@operacion("gestionar_catalogo")
def guardar_atributo(usuario, producto_id, datos, atributo_id=None):
    """Crea o edita un atributo del producto autorizado.

    Pasos:
        1. Recuperar el producto y comprobar pertenencia del atributo.
        2. Validar campos/unicidad y guardar.
    Lanza:
        ErrorDeNegocio: atributo ajeno, duplicado o datos inválidos.
    """
    # Paso 1: no se permite trasladar atributos.
    producto = Producto.objects.get(pk=producto_id)
    atributo = (producto.atributos.get(pk=atributo_id) if atributo_id
                else AtributoProducto(producto=producto))
    # Paso 2: el contrato solo admite nombre y valor.
    asignar_campos(atributo, datos, CAMPOS_ATRIBUTO)
    return _guardar(atributo, usuario)


def arbol_categorias(usuario):
    """Construye el árbol con una consulta; falla con mensaje si encuentra un ciclo.

    Pasos:
        1. Consultar categorías y enlazar nodos en memoria.
        2. Verificar que cada cadena alcanza una raíz.
    Lanza:
        ErrorDeNegocio: jerarquía existente inconsistente.
    """
    # Paso 1: `hijos` es una lista; el HTML no consulta relaciones recursivamente.
    autorizar(usuario, "gestionar_catalogo")
    nodos = {c.pk: {"categoria": c, "hijos": []} for c in Categoria.objects.all()}
    raices = []
    for nodo in nodos.values():
        padre = nodo["categoria"].padre_id
        (nodos[padre]["hijos"] if padre in nodos else raices).append(nodo)
    # Paso 2: detectar componentes cíclicos incluso sin raíz visible.
    for pk in nodos:
        visitados = set()
        while pk in nodos:
            if pk in visitados:
                raise ErrorDeNegocio("La jerarquía contiene un ciclo. Revisa las categorías antes de continuar.")
            visitados.add(pk)
            pk = nodos[pk]["categoria"].padre_id
    return raices


def listar_productos(usuario, filtros, pagina):
    """Filtra y pagina sin mutar el catálogo.

    Pasos:
        1. Aplicar búsqueda y filtros validados.
        2. Paginar con orden estable.
    Lanza:
        No lanza errores de negocio; recibe filtros ya validados.
    """
    # Paso 1: la pareja de atributo corresponde a una misma fila relacionada.
    autorizar(usuario, "gestionar_catalogo")
    productos = Producto.objects.select_related("categoria").order_by("nombre", "pk")
    if filtros.get("q"):
        productos = productos.filter(Q(nombre__icontains=filtros["q"]) | Q(codigo__icontains=filtros["q"]))
    if filtros.get("categoria"):
        productos = productos.filter(categoria=filtros["categoria"])
    if filtros.get("atributo"):
        productos = productos.filter(atributos__nombre=filtros["atributo"], atributos__valor=filtros["valor"])
    # Paso 2: conservar filtros en los enlaces desde la vista.
    return Paginator(productos, 20).get_page(pagina)
