"""Pantallas del catálogo: autorización en cada ruta y escrituras en servicios."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.exceptions import ErrorDeNegocio
from apps.core.permissions import permiso_requerido, tiene_permiso
from . import services
from .forms import AtributoForm, CategoriaForm, FiltroProductoForm, PrecioForm, PresentacionForm, PresentacionFormSet, ProductoForm
from .models import AtributoProducto, Categoria, Presentacion, Producto


def _datos(form, campos):
    return {c: form.cleaned_data[c] for c in campos}


@permiso_requerido("gestionar_catalogo")
@require_GET
def categoria_lista(request):
    try:
        categorias = services.arbol_categorias(request.user)
        error = None
    except ErrorDeNegocio as exc:
        categorias, error = [], exc.mensaje
    return render(request, "catalogo/categoria_lista.html", {"categorias": categorias, "error": error})


@permiso_requerido("gestionar_catalogo")
@require_http_methods(["GET", "POST"])
def categoria_form(request, pk=None):
    categoria = get_object_or_404(Categoria, pk=pk) if pk else None
    form = CategoriaForm(request.POST if request.method == "POST" else None, instance=categoria)
    if request.method == "POST" and form.is_valid():
        try:
            services.guardar_categoria(request.user, _datos(form, services.CAMPOS_CATEGORIA), pk)
        except ErrorDeNegocio as error:
            form.add_error(None, error.mensaje)
        else:
            messages.success(request, "Categoría guardada correctamente.")
            return redirect("catalogo:categoria_lista")
    return render(request, "catalogo/categoria_form.html", {"form": form, "editando": pk is not None})


@permiso_requerido("gestionar_catalogo")
@require_GET
def producto_lista(request):
    form = FiltroProductoForm(request.GET)
    validos = form.is_valid()
    filtros = request.GET.copy()
    filtros.pop("page", None)
    return render(request, "catalogo/producto_lista.html", {
        "form_filtros": form, "q": request.GET.get("q", ""), "categorias": Categoria.objects.all(),
        "page_obj": services.listar_productos(request.user, form.cleaned_data, request.GET.get("page")) if validos else None,
        "filtros_query": filtros.urlencode(),
    })


@permiso_requerido("gestionar_catalogo")
@require_http_methods(["GET", "POST"])
def producto_form(request, pk=None):
    producto = get_object_or_404(Producto, pk=pk) if pk else Producto()
    datos = request.POST if request.method == "POST" else None
    form = ProductoForm(datos, instance=producto)
    formset = PresentacionFormSet(datos, instance=producto, prefix="presentaciones")
    if request.method == "POST":
        valido, lineas_validas = form.is_valid(), formset.is_valid()
        if valido and lineas_validas:
            lineas = []
            for f in formset:
                if f.cleaned_data:
                    linea = _datos(f, services.CAMPOS_PRESENTACION)
                    if pk:
                        linea["id"] = f.cleaned_data["id"].pk if f.cleaned_data.get("id") else None
                    lineas.append(linea)
            try:
                datos_producto = _datos(form, services.CAMPOS_PRODUCTO)
                guardado = (services.editar_producto(request.user, pk, datos_producto, lineas) if pk else
                            services.crear_producto(request.user, datos_producto, lineas))
            except ErrorDeNegocio as error:
                form.add_error(error.campo if error.campo in form.fields else None, error.mensaje)
            else:
                messages.success(request, "Producto guardado correctamente.")
                return redirect("catalogo:producto_detalle", pk=guardado.pk)
    return render(request, "catalogo/producto_form.html", {
        "form": form, "formset_presentaciones": formset, "editando": pk is not None,
    })


def _presentaciones(producto, form=None, error=None):
    return {"producto": producto, "presentaciones": producto.presentaciones.all(),
            "form": form if form is not None else PresentacionForm(), "error": error}


def _atributos(producto, form=None, error=None):
    return {"producto": producto, "atributos": producto.atributos.all(),
            "form": form if form is not None else AtributoForm(auto_id="atributo_%s"), "error": error}


@permiso_requerido("gestionar_catalogo")
@require_GET
def producto_detalle(request, pk):
    producto = get_object_or_404(Producto.objects.select_related("categoria"), pk=pk)
    # Proyección explícita: los costos no llegan al contexto sin su permiso.
    campos = ["codigo_lote", "fecha_vencimiento", "cantidad_actual"]
    if tiene_permiso(request.user, "ver_costos"):
        campos.append("costo_unitario")
    return render(request, "catalogo/producto_detalle.html", {
        "producto": producto, "presentaciones": producto.presentaciones.all(),
        "atributos": producto.atributos.all(), "lotes": list(producto.lotes.values(*campos)),
        "stock_actual": producto.stock_actual, "form_presentacion": PresentacionForm(), "form_atributo": AtributoForm(auto_id="atributo_%s"),
    })


@permiso_requerido("gestionar_catalogo")
@require_POST
def producto_desactivar(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    try:
        services.desactivar_producto(request.user, producto)
    except ErrorDeNegocio as error:
        messages.error(request, error.mensaje)
    else:
        messages.success(request, "Producto desactivado. Su historial se conserva.")
    return redirect("catalogo:producto_detalle", pk=pk)


@permiso_requerido("gestionar_catalogo")
@require_POST
def presentacion_crear(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    form = PresentacionForm(request.POST)
    if form.is_valid():
        try:
            services.agregar_presentacion(request.user, pk, _datos(form, services.CAMPOS_PRESENTACION))
        except ErrorDeNegocio as error:
            form.add_error(None, error.mensaje)
        else:
            return render(request, "catalogo/partials/_presentaciones.html", _presentaciones(producto))
    return render(request, "catalogo/partials/_presentaciones.html", _presentaciones(producto, form), status=422)


@permiso_requerido("gestionar_catalogo")
@require_POST
def presentacion_precio(request, pk):
    presentacion = get_object_or_404(Presentacion.objects.select_related("producto"), pk=pk)
    form = PrecioForm(request.POST)
    if form.is_valid():
        try:
            services.cambiar_precio(request.user, presentacion, form.cleaned_data["precio_venta"])
        except ErrorDeNegocio as error:
            form.add_error(None, error.mensaje)
        else:
            return render(request, "catalogo/partials/_presentaciones.html", _presentaciones(presentacion.producto))
    error = " ".join(mensaje for errores in form.errors.values() for mensaje in errores)
    return render(request, "catalogo/partials/_presentaciones.html",
                  _presentaciones(presentacion.producto, error=error), status=422)


@permiso_requerido("gestionar_catalogo")
@require_POST
def atributo_crear(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    form = AtributoForm(request.POST, auto_id="atributo_%s")
    if form.is_valid():
        try:
            services.guardar_atributo(request.user, pk, _datos(form, services.CAMPOS_ATRIBUTO))
        except ErrorDeNegocio as error:
            form.add_error(None, error.mensaje)
        else:
            return render(request, "catalogo/partials/_atributos.html", _atributos(producto))
    return render(request, "catalogo/partials/_atributos.html", _atributos(producto, form), status=422)


@permiso_requerido("gestionar_catalogo")
@require_http_methods(["GET", "POST"])
def atributo_editar(request, pk, atributo_pk):
    atributo = get_object_or_404(AtributoProducto, pk=atributo_pk, producto_id=pk)
    form = AtributoForm(request.POST if request.method == "POST" else None, instance=atributo)
    if request.method == "POST" and form.is_valid():
        try:
            services.guardar_atributo(request.user, pk, _datos(form, services.CAMPOS_ATRIBUTO), atributo_pk)
        except ErrorDeNegocio as error:
            form.add_error(None, error.mensaje)
        else:
            messages.success(request, "Atributo actualizado.")
            return redirect("catalogo:producto_detalle", pk=pk)
    return render(request, "catalogo/atributo_form.html", {"form": form, "producto": atributo.producto})
