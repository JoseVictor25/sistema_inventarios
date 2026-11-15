"""Adaptador raster ESC/POS para colas Windows expresamente configuradas."""
import ctypes
from ctypes import wintypes
import os
from PIL import Image


def bytes_raster(imagen, *, alimentar=2, cortar=False):
    """GS v 0 en bandas; los bytes solo proceden de nuestra imagen renderizada."""
    if imagen.mode != 'RGB' or imagen.width % 8 or not 0 <= alimentar <= 8:
        raise ValueError('Parámetros ESC/POS inválidos.')
    monocroma = imagen.convert('L').point(lambda pixel: 0 if pixel < 180 else 255, '1')
    ancho_bytes = imagen.width // 8
    resultado = bytearray(b'\x1b@')
    for inicio in range(0, imagen.height, 256):
        banda = monocroma.crop((0, inicio, imagen.width, min(inicio + 256, imagen.height)))
        alto = banda.height
        resultado += b'\x1d\x76\x30\x00' + bytes((ancho_bytes & 255, ancho_bytes >> 8, alto & 255, alto >> 8))
        resultado += banda.tobytes()
    resultado += b'\n' * alimentar
    if cortar:
        resultado += b'\x1d\x56\x01'  # corte parcial; solo con permiso explícito.
    return bytes(resultado)


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
