"""Registro interno de cambios; la autorización corresponde al servicio invocante."""
from .models import LogAuditoria


def listar_eventos(usuario, filtros=None):
    """Consulta la bitácora sin duplicar ni modificar sus eventos.

    Pasos: 1. Autorizar/validar. 2. Filtrar y paginar. 3. Formatear JSON seguro.
    Lanza: PermissionDenied o ErrorDeNegocio por filtros inválidos.
    """
    import json
    from datetime import datetime, time, timedelta
    from django.core.paginator import Paginator
    from django.utils import timezone
    from apps.core.operaciones import autorizar
    from apps.core.exceptions import ErrorDeNegocio
    from .forms import FiltrosAuditoriaForm
    # Paso 1: comprobar acceso antes de resolver filtros de usuarios.
    autorizar(usuario, 'ver_auditoria')
    form = FiltrosAuditoriaForm(filtros or {})
    if not form.is_valid():
        raise ErrorDeNegocio(' '.join(str(e) for errores in form.errors.values() for e in errores))
    datos = form.cleaned_data
    # Paso 2: fecha local y orden estable, sin límite temporal de reportes.
    consulta = LogAuditoria.objects.select_related('usuario').order_by('-fecha', '-pk')
    for campo in ('usuario', 'entidad'):
        if datos.get(campo):
            consulta = consulta.filter(**{campo: datos[campo]})
    if datos.get('desde'):
        consulta = consulta.filter(fecha__gte=timezone.make_aware(datetime.combine(datos['desde'], time.min)))
    if datos.get('hasta'):
        consulta = consulta.filter(fecha__lt=timezone.make_aware(datetime.combine(datos['hasta'] + timedelta(days=1), time.min)))
    pagina = Paginator(consulta, 20).get_page(datos.get('page') or 1)
    # Paso 3: las plantillas escapan estos textos; nunca marcar JSON como safe.
    for evento in pagina:
        evento.anterior_texto = json.dumps(evento.valor_anterior, ensure_ascii=False, indent=2)
        evento.nuevo_texto = json.dumps(evento.valor_nuevo, ensure_ascii=False, indent=2)
    return pagina


def registrar_cambio(usuario, accion, entidad, entidad_id, anterior, nuevo):
    """Registra valores serializables en la transacción del servicio invocante.

    Pasos:
        1. Construir y validar la entrada con su autor.
        2. Guardar y devolver el registro inmutable.
    Lanza:
        ValidationError: entrada inválida; el servicio revierte la operación.
    """
    # Paso 1: no recibe datos de request ni expone una ruta de escritura.
    entrada = LogAuditoria(usuario=usuario, accion=accion, entidad=entidad,
                           entidad_id=entidad_id, valor_anterior=anterior, valor_nuevo=nuevo)
    entrada.full_clean()
    # Paso 2: la transacción externa incluye el precio y esta entrada.
    entrada.save()
    return entrada
