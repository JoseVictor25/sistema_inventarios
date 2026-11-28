"""Adaptador raster ESC/POS para colas Windows expresamente configuradas."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
from PIL import Image, ImageChops


def bytes_raster(imagen, *, avance_final_mm=0, margen_superior_mm=0,
                 ancho_mm=80, cortar=False, recortar=False):
    """GS v 0 en bandas; los bytes solo proceden de nuestra imagen renderizada."""
    if (imagen.mode != 'RGB' or imagen.width % 8
            or type(avance_final_mm) is not int or not 0 <= avance_final_mm <= 40
            or ancho_mm not in (58, 80)
            or type(margen_superior_mm) is not int or not 0 <= margen_superior_mm <= 10
            or type(cortar) is not bool):
        raise ValueError('Parámetros ESC/POS inválidos.')
    if recortar:
        limites = ImageChops.difference(imagen, Image.new('RGB', imagen.size, 'white')).getbbox()
        if limites is None:
            raise ValueError('El ticket no contiene texto.')
        margen_px = round(margen_superior_mm * imagen.width / ancho_mm)
        recorte = imagen.crop((0, limites[1], imagen.width, limites[3]))
        imagen = Image.new('RGB', (imagen.width, margen_px + recorte.height), 'white')
        imagen.paste(recorte, (0, margen_px))
    # ESC/POS: bit 1 = punto impreso (negro). Pillow modo '1': bit 1 = blanco.
    # Por eso el umbral marca el texto oscuro como 255 (1) y el fondo como 0.
    monocroma = imagen.convert('L').point(lambda pixel: 255 if pixel < 180 else 0, '1')
    ancho_bytes = imagen.width // 8
    resultado = bytearray(b'\x1b@')
    for inicio in range(0, imagen.height, 256):
        banda = monocroma.crop((0, inicio, imagen.width, min(inicio + 256, imagen.height)))
        alto = banda.height
        resultado += b'\x1d\x76\x30\x00' + bytes((ancho_bytes & 255, ancho_bytes >> 8, alto & 255, alto >> 8))
        resultado += banda.tobytes()
    # LF vacía el último renglón del raster antes del avance y del corte.
    resultado += b'\n'
    puntos = avance_final_mm * 8  # 203 dpi: aproximadamente ocho puntos/mm.
    if puntos == 0:
        resultado += b'\x1bJ\x00'
    while puntos:
        tramo = min(puntos, 255)
        resultado += b'\x1bJ' + bytes((tramo,))
        puntos -= tramo
    if cortar:
        resultado += b'\x1d\x56\x42\x00'  # avance hasta cuchilla y corte parcial.
    return bytes(resultado)


def imagen_calibracion(ancho_mm):
    """Regla vertical de 40 mm con marcas a intervalos de 5 mm."""
    from PIL import ImageDraw, ImageFont
    if ancho_mm not in (58, 80):
        raise ValueError('Ancho de papel inválido.')
    ancho = 576 if ancho_mm == 80 else 384
    escala = ancho / ancho_mm
    inicio_x = round(8 * escala)
    imagen = Image.new('RGB', (ancho, round(40 * escala) + 20), 'white')
    dibujo = ImageDraw.Draw(imagen)
    ruta_fuente = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'arial.ttf'
    if not ruta_fuente.exists():
        import reportlab
        ruta_fuente = Path(reportlab.__file__).parent / 'fonts' / 'Vera.ttf'
    fuente = ImageFont.truetype(str(ruta_fuente), 16)
    dibujo.line((inicio_x, 0, inicio_x, round(40 * escala)), fill='black', width=2)
    for mm in range(0, 41, 5):
        y = round(mm * escala)
        dibujo.line((inicio_x, y, inicio_x + round(5 * escala), y), fill='black', width=2)
        dibujo.text((inicio_x + round(6 * escala), max(0, y - 8)), f'{mm} mm',
                    fill='black', font=fuente)
    return imagen


def listar_colas():
    """Nombres de colas Windows locales/conectadas; sin acceder a puertos USB."""
    if os.name != 'nt':
        return []
    spool = ctypes.WinDLL('winspool.drv', use_last_error=True)
    class Impresora(ctypes.Structure):
        _fields_ = [('pPrinterName', wintypes.LPWSTR), ('pServerName', wintypes.LPWSTR),
                    ('Attributes', wintypes.DWORD)]
    spool.EnumPrintersW.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    spool.EnumPrintersW.restype = wintypes.BOOL
    requerido, cantidad = wintypes.DWORD(), wintypes.DWORD()
    flags = 2 | 4  # local y conexiones
    spool.EnumPrintersW(flags, None, 4, None, 0, ctypes.byref(requerido), ctypes.byref(cantidad))
    if not requerido.value:
        return []
    buffer = ctypes.create_string_buffer(requerido.value)
    if not spool.EnumPrintersW(flags, None, 4, buffer, requerido.value,
                               ctypes.byref(requerido), ctypes.byref(cantidad)):
        raise OSError(ctypes.get_last_error(), 'No se pudieron consultar las impresoras.')
    registros = ctypes.cast(buffer, ctypes.POINTER(Impresora))
    return sorted({registros[i].pPrinterName for i in range(cantidad.value) if registros[i].pPrinterName})


def enviar_cola(nombre, datos, *, backend=None):
    """Devuelve ID del trabajo aceptado por el spooler; no acredita impresión física."""
    if os.name != 'nt':
        raise RuntimeError('La cola RAW requiere Windows.')
    if not nombre or not isinstance(nombre, str) or not isinstance(datos, bytes):
        raise ValueError('Trabajo de impresión inválido.')
    if backend is not None:  # Punto de inyección de cola simulada en pruebas.
        return backend(nombre, datos)
    spool = ctypes.WinDLL('winspool.drv', use_last_error=True)
    class Documento(ctypes.Structure):
        _fields_ = [('pDocName', wintypes.LPWSTR), ('pOutputFile', wintypes.LPWSTR),
                    ('pDatatype', wintypes.LPWSTR)]
    spool.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    spool.OpenPrinterW.restype = wintypes.BOOL
    spool.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(Documento)]
    spool.StartDocPrinterW.restype = wintypes.DWORD
    spool.WritePrinter.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                    ctypes.POINTER(wintypes.DWORD)]
    spool.WritePrinter.restype = wintypes.BOOL
    spool.EndDocPrinter.argtypes = [wintypes.HANDLE]
    spool.ClosePrinter.argtypes = [wintypes.HANDLE]
    manejador = wintypes.HANDLE()
    if not spool.OpenPrinterW(nombre, ctypes.byref(manejador), None):
        raise OSError(ctypes.get_last_error(), 'No se pudo abrir la cola de impresión.')
    trabajo = 0
    try:
        info = Documento('Comprobante no fiscal', None, 'RAW')
        trabajo = spool.StartDocPrinterW(manejador, 1, ctypes.byref(info))
        if not trabajo:
            raise OSError(ctypes.get_last_error(), 'No se pudo iniciar el trabajo.')
        try:
            enviados = wintypes.DWORD()
            buffer = ctypes.create_string_buffer(datos)
            if not spool.WritePrinter(manejador, buffer, len(datos), ctypes.byref(enviados)) or enviados.value != len(datos):
                raise OSError(ctypes.get_last_error(), 'La cola no aceptó el trabajo completo.')
        finally:
            spool.EndDocPrinter(manejador)
        return trabajo
    finally:
        spool.ClosePrinter(manejador)
