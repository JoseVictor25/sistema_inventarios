"""Launcher del sistema: soporta modo temporal (Bloque A) y modo instalado persistente (Bloque B3)."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datos-temporales', help='Ruta absoluta dentro de TEMP para modo experimental/pruebas.')
    parser.add_argument('--datos-instalados', help='Ruta absoluta en ProgramData para modo instalado persistente.')
    parser.add_argument('--instalado', action='store_true', help='Ejecuta en modo instalado permanente (usa ProgramData).')
    parser.add_argument('--inicializar', action='store_true', help='Autoriza crear una instalación nueva.')
    parser.add_argument('--respaldo', action='store_true', help='Crea copia de seguridad y finaliza sin abrir interfaz.')
    parser.add_argument('--navegador', action='store_true', help='Usa navegador predeterminado en lugar de WebView2.')
    parser.add_argument('--puerto', type=int, default=8000, help='Puerto local HTTP preferido.')
    parser.add_argument('--diagnostico', action='store_true', help='Prueba HTTP y cierre sin abrir interfaz.')
    parser.add_argument('--operador-sid', help='SID específico del operador para validación de acceso.')
    args = parser.parse_args()

    from desktop.rutas import validar_temporal, validar_datos_instalados, recursos
    from desktop.bloqueo_instancia import bloqueo_instancia
    modo = None
    ruta = None

    if args.datos_temporales:
        modo = 'temporal'
        ruta = validar_temporal(args.datos_temporales)
    elif args.datos_instalados or args.instalado or getattr(sys, 'frozen', False):
        modo = 'instalado'
        ruta = validar_datos_instalados(args.datos_instalados)
    else:
        parser.error('Se requiere indicar --datos-temporales (para pruebas) o --instalado (para uso persistente).')

    ruta.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(recursos() / 'backend'))

    from apps.core.respaldos import crear_copia
    from desktop.inicializacion import configurar
    from django.db import connections
    servidor = None
    from contextlib import nullcontext

    try:
        # El bloqueo de instancia cubre el servidor HTTP: mantenimiento y el
        # instalador pueden detectar una instancia activa mediante este cerrojo.
        with (nullcontext() if args.respaldo else bloqueo_instancia(ruta)):
            configurar(
                ruta,
                autorizar_nueva=args.inicializar and not args.respaldo,
                solo_respaldo=args.respaldo,
                modo=modo,
                sid_operador=args.operador_sid
            )
            if args.respaldo:
                from apps.core.respaldos import crear_copia
                from django.conf import settings
                resultado = crear_copia(settings.DB_PATH, settings.BACKUP_DIR, settings.BACKUP_CONSERVAR,
                                       qr=settings.DATA_DIR / 'qr_bancario.png')
                print('Respaldo verificado:', resultado['archivo'], resultado['sha256'])
                return 0

            from apps.core.primer_uso import habilitar
            from apps.core.frontend import recursos_faltantes
            from django.conf import settings

            if not getattr(sys, 'frozen', False):
                # En desarrollo nunca se escribe backend/staticfiles: se recolecta
                # en la carpeta de esta instalación.
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
