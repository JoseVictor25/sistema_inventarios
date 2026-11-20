"""Reconstruye sin imprimir el raster ESC/POS de un ticket ficticio."""
from pathlib import Path
import sys

from PIL import Image, ImageOps

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'backend'))
from apps.ventas.escpos import bytes_raster  # noqa: E402


def decodificar(datos):
    """Lee bandas GS v 0; bit 1 significa punto negro en ESC/POS."""
    if not datos.startswith(b'\x1b@'):
        raise ValueError('Falta la cabecera ESC/POS.')
    posicion = 2
    bandas = []
    while datos[posicion:posicion + 4] == b'\x1d\x76\x30\x00':
        ancho_bytes = datos[posicion + 4] + 256 * datos[posicion + 5]
        alto = datos[posicion + 6] + 256 * datos[posicion + 7]
        inicio = posicion + 8
        final = inicio + ancho_bytes * alto
        banda = Image.frombytes('1', (ancho_bytes * 8, alto), datos[inicio:final])
        bandas.append(ImageOps.invert(banda.convert('RGB')))
        posicion = final
    if not bandas:
        raise ValueError('No hay bandas raster.')
    imagen = Image.new('RGB', (bandas[0].width, sum(b.height for b in bandas)), 'white')
    y = 0
    for banda in bandas:
        imagen.paste(banda, (0, y))
        y += banda.height
    return imagen


def main():
    fuente = RAIZ / 'docs/ticket_ejemplo_30.png'
    destino = RAIZ / 'docs/ticket_escpos_decodificado.png'
    with Image.open(fuente) as original:
        datos = bytes_raster(original.convert('RGB'), alimentar=0)
    imagen = decodificar(datos)
    imagen.save(destino)
    print(f'Raster reconstruido: {destino} ({imagen.width} x {imagen.height} px)')
    print(f'Bytes ESC/POS: {len(datos)}; bandas: {datos.count(bytes((29, 118, 48, 0)))}')


if __name__ == '__main__':
    main()
