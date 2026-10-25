"""Gestión ordinaria de proveedores; no registra compras."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from apps.core.exceptions import ErrorDeNegocio
from apps.core.permissions import permiso_requerido
from .forms import ProveedorForm
from .models import Proveedor
from .services import CAMPOS_PROVEEDOR, guardar_proveedor


@permiso_requerido("gestionar_compras")
@require_GET
def proveedor_lista(request):
    return render(request, "compras/proveedor_lista.html", {"proveedores": Proveedor.objects.all()})


@permiso_requerido("gestionar_compras")
@require_http_methods(["GET", "POST"])
def proveedor_form(request, pk=None):
    proveedor = get_object_or_404(Proveedor, pk=pk) if pk else None
    form = ProveedorForm(request.POST if request.method == "POST" else None, instance=proveedor)
    if request.method == "POST" and form.is_valid():
        try:
            guardar_proveedor(request.user, {c: form.cleaned_data[c] for c in CAMPOS_PROVEEDOR}, pk)
        except ErrorDeNegocio as error:
            form.add_error(None, error.mensaje)
        else:
            messages.success(request, "Proveedor guardado correctamente.")
            return redirect("compras:proveedor_lista")
    return render(request, "compras/proveedor_form.html", {"form": form, "editando": pk is not None})
