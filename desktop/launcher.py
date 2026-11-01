"""Launcher experimental: siempre requiere un directorio temporal explícito."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datos-temporales', required=True)
    parser.add_argument('--inicializar', action='store_true')
    parser.add_argument('--respaldo', action='store_true')
    parser.add_argument('--navegador', action='store_true')
    parser.add_argument('--puerto', type=int, default=8000)
    parser.add_argument('--diagnostico', action='store_true', help='Prueba HTTP y cierre sin abrir interfaz, solo en TEMP.')
    args = parser.parse_args()
    from desktop.rutas import validar_temporal, recursos
    ruta = validar_temporal(args.datos_temporales)
    ruta.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(recursos() / 'backend'))
    from apps.core.respaldos import _bloqueo, crear_copia
    from desktop.inicializacion import configurar
    from django.db import connections
    servidor = None
    # Modo respaldo no toma el bloqueo de interfaz: el motor controla sus copias.
    from contextlib import nullcontext
    try:
        with (nullcontext() if args.respaldo else _bloqueo(ruta)):
            configurar(ruta, args.inicializar and not args.respaldo, solo_respaldo=args.respaldo)
            if args.respaldo:
                from django.conf import settings
                resultado = crear_copia(settings.DB_PATH, settings.BACKUP_DIR, settings.BACKUP_CONSERVAR)
                print('Respaldo verificado:', resultado['archivo'], resultado['sha256'])
                return 0
            from apps.core.primer_uso import habilitar
            from apps.core.frontend import recursos_faltantes
            from django.conf import settings
            if not getattr(sys, 'frozen', False):
                # En origen nunca se escribe backend/staticfiles: se recolecta
                # en la carpeta temporal de esta instalación.
                settings.STATIC_ROOT = ruta / 'staticfiles'
                from django.core.management import call_command
                call_command('collectstatic', interactive=False, verbosity=0)
            faltantes = recursos_faltantes(settings.STATIC_ROOT)
            if faltantes:
                raise RuntimeError(
                    'Faltan recursos estáticos obligatorios en el paquete: '
                    + ', '.join(faltantes)
                )
            token = habilitar()
            from django.core.wsgi import get_wsgi_application
            from desktop.servidor import Servidor
            servidor = Servidor(get_wsgi_application(), args.puerto)
            servidor.iniciar()
            if args.diagnostico:
                from urllib.request import urlopen
                from apps.core.frontend import RECURSOS_FRONTEND
                for recurso in RECURSOS_FRONTEND:
                    with urlopen(servidor.url + '/static/' + recurso, timeout=10) as respuesta:
                        if respuesta.status != 200:
                            raise RuntimeError('Falta un recurso local.')
                servidor.cerrar()
                servidor = None
                print('Diagnóstico HTTP y cierre aprobados.')
                return 0
            url = servidor.url + ('/configuracion-inicial/' if token else '/')
            if token:
                print('Código local de un solo uso:', token, flush=True)
            if not args.navegador:
                try:
                    import webview
                    webview.settings['ALLOW_DOWNLOADS'] = True
                    webview.create_window('Sistema de inventarios', url)
                    webview.start(gui='edgechromium', private_mode=True)
                    servidor.cerrar()
                    servidor = None
                    return 0
                except Exception:
                    print('No se pudo abrir WebView2. Se usará el navegador local.')
            import webbrowser
            webbrowser.open(url)
            input('Servidor local activo. Pulsa ENTER aquí para cerrarlo: ')
            servidor.cerrar()
            servidor = None
            return 0
    except Exception as error:
        print('No se pudo iniciar el sistema:', str(error), file=sys.stderr)
        return 1
    finally:
        if servidor:
            servidor.cerrar()
        from django.conf import settings
        if settings.configured:
            connections.close_all()


if __name__ == '__main__':
    sys.exit(main())
