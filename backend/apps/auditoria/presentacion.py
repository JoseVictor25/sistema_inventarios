"""Presentación de históricos; no modifica ni crea eventos."""
from decimal import Decimal, InvalidOperation

ACCIONES = {'CAMBIO_PRECIO': 'Cambio de precio', 'AJUSTE_INVENTARIO': 'Ajuste de inventario', 'CIERRE_CAJA': 'Cierre de caja'}
ETIQUETAS = {'precio_venta': 'Precio de venta', 'cantidad_actual': 'Existencias', 'usuario_id': 'Usuario', 'caja_id': 'Caja', 'monto_inicial': 'Monto inicial', 'monto_contado': 'Efectivo contado', 'efectivo_esperado': 'Efectivo esperado', 'diferencia': 'Diferencia', 'fecha_cierre': 'Fecha de cierre'}
SENSIBLES = ('password', 'contrasena', 'contraseña', 'secret', 'token', 'credencial', 'clave', 'authorization')


def filas(valor, prefijo='', profundidad=0):
    if profundidad > 12:
        return [(prefijo, 'Estructura demasiado profunda para mostrar')]
    if isinstance(valor, (dict, list)) and valor:
        salida = []
        elementos = valor.items() if isinstance(valor, dict) else enumerate(valor, 1)
        for clave, contenido in elementos:
            clave = str(clave)
            if any(s in clave.lower() for s in SENSIBLES):
                continue
            etiqueta = ETIQUETAS.get(clave, clave.replace('_', ' ').capitalize())
            salida.extend(filas(contenido, f'{prefijo} / {etiqueta}' if prefijo else etiqueta, profundidad + 1))
        return salida
    if valor is None:
        texto = 'Sin valor'
    elif isinstance(valor, bool):
        texto = 'Sí' if valor else 'No'
    elif isinstance(valor, (dict, list)):
        texto = 'Sin elementos'
    else:
        texto = str(valor)
        if prefijo.split(' / ')[-1] in ('Precio de venta', 'Monto inicial', 'Efectivo contado', 'Efectivo esperado', 'Diferencia'):
            try:
                numero = Decimal(texto)
                if numero.is_finite():
                    from django.conf import settings
                    texto = settings.MONEDA_SIMBOLO + ' ' + format(numero, '.2f').replace('.', ',')
            except InvalidOperation:
                pass
    return [(prefijo or 'Valor', texto)]


def preparar(evento):
    evento.accion_legible = ACCIONES.get(evento.accion, evento.accion.replace('_', ' ').capitalize())
    anterior, nuevo = dict(filas(evento.valor_anterior)), dict(filas(evento.valor_nuevo))
    evento.detalles = [dict(campo=k, anterior=anterior.get(k, 'No registrado'), nuevo=nuevo.get(k, 'No registrado'),
                           cambio=anterior.get(k) != nuevo.get(k)) for k in dict.fromkeys([*anterior, *nuevo])]
    return evento
