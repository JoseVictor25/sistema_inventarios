"""Preferencias locales de tickets; no contienen datos de ventas."""
import json
import os
from pathlib import Path
import tempfile
from django.conf import settings
from django.core.exceptions import ValidationError

DEFAULT = {'ancho': 80, 'vista_previa': True, 'ofrecer_al_finalizar': False,
           'impresion_manual': True, 'metodo': 'Windows', 'mensaje': 'Gracias por su compra',
           'margen_superior_mm': 2, 'margen_inferior_mm': 5,
           'impresora': '', 'escpos_confirmado': False, 'alimentar_lineas': 2,
           'corte_automatico': False, 'columnas_80': 48, 'columnas_58': 32,
           'avance_final_mm': None}


def avance_final(datos):
    """Un valor explícito, incluso cero, prevalece sobre el defecto por modo."""
    valor = datos['avance_final_mm']
    return (8 if datos['corte_automatico'] else 32) if valor is None else valor


def ruta():
    base = Path(settings.DATA_DIR).absolute()
    archivo = base / 'impresion.json'
    if any(p.is_symlink() or p.is_junction() for p in (archivo, *archivo.parents)):
        raise ValidationError('Ruta de configuración insegura.')
    if base.resolve().is_relative_to(Path(settings.BASE_DIR).parent.resolve()):
        raise ValidationError('La configuración debe estar fuera del programa.')
    return archivo


def leer():
    archivo = ruta()
    if not archivo.exists():
        return DEFAULT.copy()
    try:
        datos = json.loads(archivo.read_text(encoding='utf-8'))
        if not isinstance(datos, dict):
            raise ValueError()
        return {**DEFAULT, **{k: datos[k] for k in DEFAULT if k in datos}}
    except (OSError, ValueError):
        raise ValidationError('No se pudo leer la configuración de impresión.') from None


def guardar(datos):
    if (datos.get('ancho') not in (58, 80) or datos.get('metodo') not in ('Windows', 'ESC/POS')
            or type(datos.get('margen_superior_mm')) is not int
            or not 1 <= datos['margen_superior_mm'] <= 10
            or type(datos.get('margen_inferior_mm')) is not int
            or not 2 <= datos['margen_inferior_mm'] <= 15
            or any(type(datos.get(k)) is not bool for k in ('vista_previa', 'ofrecer_al_finalizar', 'impresion_manual'))
            or not isinstance(datos.get('mensaje'), str) or len(datos['mensaje']) > 120
            or not isinstance(datos.get('impresora'), str) or len(datos['impresora']) > 200
            or type(datos.get('escpos_confirmado')) is not bool
            or type(datos.get('corte_automatico')) is not bool
            or type(datos.get('alimentar_lineas')) is not int
            or not 0 <= datos['alimentar_lineas'] <= 8
            or type(datos.get('columnas_80')) is not int or not 24 <= datos['columnas_80'] <= 64
            or type(datos.get('columnas_58')) is not int or not 16 <= datos['columnas_58'] <= 48
            or (datos.get('avance_final_mm') is not None and
                (type(datos['avance_final_mm']) is not int or not 0 <= datos['avance_final_mm'] <= 40))
            or (datos['metodo'] == 'ESC/POS' and
                (not datos['escpos_confirmado'] or not datos['impresora'].strip()))):
        raise ValidationError('Configuración de impresión inválida.')
    destino = ruta()
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destino.parent,
                                         prefix='.impresion_', delete=False) as f:
            temporal = Path(f.name)
            json.dump({k: datos[k] for k in DEFAULT}, f, ensure_ascii=False)
            f.flush(); os.fsync(f.fileno())
        os.replace(temporal, destino)
    finally:
        if temporal:
            temporal.unlink(missing_ok=True)
