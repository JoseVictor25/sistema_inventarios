"""Genera PNG y PDF continuos con datos ficticios, sin abrir la base real."""
import os
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'scripts'))
from verificar_catalogo_fase3 import preparar_entorno
from verificar_reportes_fase8 import huellas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--solo-html', action='store_true')
    args = parser.parse_args()
    if Path(sys.executable).resolve() != RAIZ / 'venv/Scripts/python.exe':
        raise RuntimeError('Usa el Python del venv.')
    antes = huellas()
    temporal = Path(tempfile.mkdtemp(prefix='Inventarios_ticket_pdf_'))
    entorno = preparar_entorno(temporal)
    comando = [sys.executable, str(RAIZ / 'backend/manage.py'), 'migrate', '--noinput']
    subprocess.run(comando, cwd=RAIZ / 'backend', env=entorno, check=True, stdout=subprocess.DEVNULL)
    os.environ.update(entorno)
    sys.path[:0] = [str(temporal), str(RAIZ / 'backend')]
    import django
    django.setup()
    from django.test import Client
    from apps.reportes.tests.datos import crear_datos
    from apps.ventas.models import DetalleVenta
    datos = crear_datos()
    venta = datos['venta']
    modelo = venta.detalles.first()
    modelo.cantidad_presentaciones = 1
    modelo.unidades_totales = modelo.presentacion.unidades_equivalentes
    modelo.subtotal = modelo.precio_aplicado
    modelo.save(update_fields=['cantidad_presentaciones', 'unidades_totales', 'subtotal'])
    cliente = Client(HTTP_HOST='127.0.0.1')
    cliente.force_login(datos['dueno'])
    trabajos = []
    for cantidad in (1, 5, 10, 15, 30):
        venta.detalles.exclude(pk=modelo.pk).delete()
        while venta.detalles.count() < cantidad:
            DetalleVenta.objects.create(venta=venta, presentacion=modelo.presentacion,
                cantidad_presentaciones=1, unidades_totales=3,
                precio_aplicado=modelo.precio_aplicado, subtotal=modelo.precio_aplicado)
        venta.total = modelo.precio_aplicado * cantidad
        venta.save(update_fields=['total'])
        venta.pagos.filter(metodo__nombre='Efectivo').update(monto=venta.total * 2 / 3)
        venta.pagos.filter(metodo__nombre='QR').update(monto=venta.total / 3)
        html = temporal / f'ticket_{cantidad}.html'
        html.write_bytes(cliente.get(f'/ventas/{venta.pk}/comprobante/').content)
        pdf = temporal / f'ticket_{cantidad}.pdf'
        png = temporal / f'ticket_{cantidad}.png'
        png.write_bytes(cliente.get(f'/ventas/{venta.pk}/comprobante/imagen/').content)
        if not args.solo_html:
            respuesta = cliente.get(f'/ventas/{venta.pk}/comprobante/pdf/')
            assert respuesta.status_code == 200, respuesta.status_code
            pdf.write_bytes(respuesta.content)
        trabajos.append((cantidad, html, pdf))
    print('Tickets ficticios HTML:', temporal, flush=True)
    if args.solo_html:
        assert antes == huellas(), 'Cambió un archivo protegido.'
        return
    for cantidad, html, pdf in trabajos:
        contenido = pdf.read_bytes()
        paginas = len(re.findall(rb'/Type\s*/Page\b', contenido))
        assert paginas == 1, paginas
        print(cantidad, 'productos:', pdf, 'bytes:', len(contenido), 'páginas:', paginas, flush=True)
    assert antes == huellas(), 'Cambió un archivo protegido.'
    print('Archivos protegidos intactos; evidencia:', temporal)


if __name__ == '__main__':
    main()
