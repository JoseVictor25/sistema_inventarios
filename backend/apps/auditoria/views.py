from django.shortcuts import render
from django.views.decorators.http import require_GET
from apps.core.permissions import permiso_requerido
from .forms import FiltrosAuditoriaForm
from .services import listar_eventos


@permiso_requerido('ver_auditoria')
@require_GET
def lista(request):
    form = FiltrosAuditoriaForm(request.GET)
    pagina = listar_eventos(request.user, request.GET) if form.is_valid() else None
    filtros = request.GET.copy()
    filtros.pop('page', None)
    respuesta = render(request, 'auditoria/lista.html', dict(form=form, page_obj=pagina, filtros_query=filtros.urlencode()), status=200 if pagina is not None else 422)
    respuesta['Cache-Control'] = 'private, no-store'
    return respuesta
