"""Datos inmutables y renderizado continuo de comprobantes no fiscales."""
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import math
import os

from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import reportlab


@dataclass(frozen=True)
class Linea:
    nombre: str
    presentacion: str
    cantidad: int
    precio: Decimal
    subtotal: Decimal


@dataclass(frozen=True)
class PagoTicket:
    metodo: str
    monto: Decimal


@dataclass(frozen=True)
class Ticket:
    negocio: str
    numero: int
    fecha: object
    cajero: str
    lineas: tuple[Linea, ...]
    pagos: tuple[PagoTicket, ...]
    total: Decimal
    mensaje: str


def desde_venta(venta, mensaje):
    """El llamador obtiene la venta con obtener_venta() y sus permisos."""
    return Ticket(str(settings.NOMBRE_NEGOCIO), venta.pk, venta.fecha,
        venta.usuario.get_username(),
        tuple(Linea(d.presentacion.producto.nombre, d.presentacion.nombre,
                    d.cantidad_presentaciones, d.precio_aplicado, d.subtotal)
              for d in venta.detalles.all()),
        tuple(PagoTicket(p.metodo.nombre, p.monto) for p in venta.pagos.all()),
        venta.total, mensaje)


def _fuente(tamano):
    ruta = Path(reportlab.__file__).parent / 'fonts' / 'Vera.ttf'
    return ImageFont.truetype(str(ruta), tamano)


def _envolver(texto, fuente, maximo):
    """Divide por ancho real; conserva palabras largas completas en varias líneas."""
    lineas = []
    for parrafo in str(texto).splitlines() or ['']:
        actual = ''
        for palabra in parrafo.split(' '):
            candidato = (actual + ' ' + palabra).strip()
            if fuente.getlength(candidato) <= maximo:
                actual = candidato
                continue
            if actual:
                lineas.append(actual)
                actual = ''
            for letra in palabra:
                if actual and fuente.getlength(actual + letra) > maximo:
                    lineas.append(actual)
                    actual = ''
                actual += letra
        lineas.append(actual)
    return lineas


def _envolver_columnas(texto, primera, siguientes):
    """Respeta palabras; divide solo las que exceden una línea completa."""
    palabras = ' '.join(str(texto).split()).split(' ')
    salida = []
    while palabras:
        limite = primera if not salida else siguientes
        renglon = ''
        while palabras:
            palabra = palabras[0]
            candidato = f'{renglon} {palabra}'.strip()
            if len(candidato) <= limite:
                renglon = candidato
                palabras.pop(0)
            elif renglon:
                break
            else:
                renglon = palabra[:limite]
                if len(palabra) == limite:
                    palabras.pop(0)
                else:
                    palabras[0] = palabra[limite:]
                break
        salida.append(renglon)
    return salida


def formatear_par(etiqueta, monto, columnas):
    """Líneas (texto izquierdo, importe derecho); el importe ocupa la primera."""
    if not 2 <= len(monto) < columnas:
        raise ValueError('El importe no cabe en el ancho configurado.')
    partes = _envolver_columnas(etiqueta, columnas - len(monto) - 1, columnas)
    return [(partes[0], monto), *((parte, None) for parte in partes[1:])]


def formatear_item(detalle, columnas):
    """Nombre e importe juntos, seguidos de cantidad, precio y unidad."""
    filas = formatear_par(detalle.nombre, f'Bs {detalle.subtotal:.2f}', columnas)
    descripcion = f'  {detalle.cantidad} x {detalle.precio:.2f} · {detalle.presentacion}'
    filas.extend((f'  {parte}', None) for parte in _envolver_columnas(
        descripcion[2:], columnas - 2, columnas - 2))
    return filas


def renderizar(ticket, configuracion):
    """Una sola imagen RGB; devuelve dimensiones y zonas para pruebas de margen."""
    ancho = 576 if configuracion['ancho'] == 80 else 384
    escala = ancho / configuracion['ancho']  # 8 puntos/mm para 80; conservador en 58.
    margen_lateral = round(4 * escala)
    arriba = round(configuracion['margen_superior_mm'] * escala)
    abajo = round(configuracion['margen_inferior_mm'] * escala)
    letra, titulo = _fuente(19), _fuente(23)
    columnas = configuracion.get('columnas_80', 48) if configuracion['ancho'] == 80 else configuracion.get('columnas_58', 32)
    ruta_mono = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'consola.ttf'
    if not ruta_mono.exists():
        ruta_mono = Path(reportlab.__file__).parent / 'fonts' / 'Vera.ttf'
    tamano_mono = 19
    while tamano_mono > 8 and ImageFont.truetype(str(ruta_mono), tamano_mono).getlength('W' * columnas) > ancho - 2 * margen_lateral:
        tamano_mono -= 1
    mono = ImageFont.truetype(str(ruta_mono), tamano_mono)
    alto_linea = 27
    contenido = ancho - 2 * margen_lateral
    operaciones = []
    importes = []
    y = arriba

    def linea(texto, *, centrado=False, derecha=False, fuente=letra, ancho_texto=contenido):
        nonlocal y
        for renglon in _envolver(texto, fuente, ancho_texto):
            x = margen_lateral
            if centrado:
                x += round((contenido - fuente.getlength(renglon)) / 2)
            if derecha:
                x += round(contenido - fuente.getlength(renglon))
            operaciones.append((x, y, renglon, fuente))
            y += alto_linea + (5 if fuente is titulo else 0)

    def par(filas):
        nonlocal y
        for izquierda, importe in filas:
            operaciones.append((margen_lateral, y, izquierda, mono))
            if importe:
                x = margen_lateral + round(contenido - mono.getlength(importe))
                operaciones.append((x, y, importe, mono))
                importes.append((y, x, round(mono.getlength(importe))))
            y += alto_linea

    linea(ticket.negocio, centrado=True, fuente=titulo)
    linea('DOCUMENTO NO FISCAL', centrado=True)
    y += 8
    linea(f'Venta #{ticket.numero}')
    linea(ticket.fecha.strftime('Fecha: %d/%m/%Y %H:%M:%S'))
    linea(f'Cajero: {ticket.cajero}')
    y += 8
    for detalle in ticket.lineas:
        par(formatear_item(detalle, columnas))
        y += 5
    y += 6
    par(formatear_par('TOTAL', f'Bs {ticket.total:.2f}', columnas))
    y += 8
    for pago in ticket.pagos:
        par(formatear_par(pago.metodo, f'Bs {pago.monto:.2f}', columnas))
    y += 9
    linea(ticket.mensaje, centrado=True)
    linea('DOCUMENTO NO FISCAL', centrado=True)
    ultimo_texto = y
    alto = ultimo_texto + abajo
    imagen = Image.new('RGB', (ancho, alto), 'white')
    lapiz = ImageDraw.Draw(imagen)
    for x, py, texto, fuente in operaciones:
        lapiz.text((x, py), texto, font=fuente, fill='black')
    return imagen, {'ancho_px': ancho, 'alto_px': alto, 'ultimo_texto_px': ultimo_texto,
                    'margen_superior_px': arriba, 'margen_inferior_px': abajo,
                    'importes': importes}


def medidas_pagina(meta, configuracion):
    """Devuelve una hoja vertical para la ruta navegador/controlador.

    El alto se deriva de la misma imagen del ticket. Si es menor que el ancho,
    algunos navegadores interpretan la hoja como horizontal y giran el papel.
    """
    ancho = configuracion['ancho']
    alto = math.ceil(ancho * meta['alto_px'] / meta['ancho_px'])
    return {'ancho': ancho, 'alto': max(alto, ancho + 1)}


def png(ticket, configuracion):
    imagen, meta = renderizar(ticket, configuracion)
    salida = BytesIO()
    imagen.save(salida, format='PNG')
    return salida.getvalue(), meta


def pdf(ticket, configuracion):
    imagen, meta = renderizar(ticket, configuracion)
    ancho_pt = configuracion['ancho'] * 72 / 25.4
    alto_pt = meta['alto_px'] * ancho_pt / meta['ancho_px']
    if alto_pt > 14400:  # límite de página PDF habitual: no truncar silenciosamente.
        raise ValueError('El comprobante supera el alto máximo de una página PDF.')
    salida = BytesIO()
    documento = canvas.Canvas(salida, pagesize=(ancho_pt, alto_pt), pageCompression=1)
    documento.drawImage(ImageReader(imagen), 0, 0, width=ancho_pt, height=alto_pt)
    documento.showPage()
    documento.save()
    return salida.getvalue(), meta
