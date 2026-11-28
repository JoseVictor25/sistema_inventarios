"""Launcher del sistema: soporta modo temporal (Bloque A) y modo instalado persistente (Bloque B3)."""
import argparse
from pathlib import Path
import sys
import threading
import logging

MENSAJE_CUENTA_NO_AUTORIZADA = ('Esta cuenta de Windows no está autorizada para usar el sistema. '
                               'Inicia sesión con la cuenta con la que se instaló.')


def _mensaje_inicio(error):
    if isinstance(error, PermissionError):
        return MENSAJE_CUENTA_NO_AUTORIZADA
    return f'No se pudo iniciar el sistema: {error}'


def _registrar_permiso_bloqueo(error, ruta):
    """Registra el fallo previo a configurar Django sin emitirlo a consola."""
    from logging.handlers import RotatingFileHandler

    logs_dir = Path(ruta) / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('desktop.launcher.bloqueo')
    logger.propagate = False
    logger.setLevel(logging.ERROR)
    handler = RotatingFileHandler(logs_dir / 'sistema.log', maxBytes=1_000_000,
                                  backupCount=4, encoding='utf-8')
    handler.setFormatter(logging.Formatter(
        '{asctime} [{levelname}] {name}: {message}', style='{'))
    logger.addHandler(handler)
    try:
        logger.exception('No se pudo abrir el archivo de bloqueo de instancia',
                         exc_info=(type(error), error, error.__traceback__))
    finally:
        logger.removeHandler(handler)
        handler.close()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _crear_respaldo_automatico(settings):
    from apps.core.respaldos import crear_copia
    resultado = crear_copia(settings.DB_PATH, settings.BACKUP_DIR, settings.BACKUP_CONSERVAR,
        qr=settings.DATA_DIR / 'qr_bancario.png',
        directorio_externo=getattr(settings, 'BACKUP_DIR_EXTERNO', None))
    try:
        from apps.core.services import _guardar_advertencia_externa
        _guardar_advertencia_externa(resultado['advertencia'])
    except Exception:
        logging.getLogger(__name__).exception('No se pudo registrar el estado del destino externo')
    return resultado


def _respaldo_vencido(settings, horas=24, *, ahora=None):
    from apps.core.respaldos import listar_copias
    from datetime import datetime, timezone
    import logging
    try:
        ultimo = next((fila['fecha'] for fila in listar_copias(settings.BACKUP_DIR) if fila['verificado']), None)
        if not ultimo:
            return True
        ahora = ahora or datetime.now(timezone.utc)
        return (ahora - datetime.fromisoformat(ultimo)).total_seconds() > horas * 60 * 60
    except Exception:
        logging.getLogger(__name__).exception('No se pudo comprobar la antigüedad del último respaldo')
        return True


def _respaldo_cierre_vencido(settings, *, ahora=None):
    return _respaldo_vencido(settings, settings.BACKUP_HORAS_MIN_CIERRE, ahora=ahora)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datos-temporales', help='Ruta absoluta dentro de TEMP para modo experimental/pruebas.')
    parser.add_argument('--datos-instalados', help='Ruta absoluta en ProgramData para modo instalado persistente.')
    parser.add_argument('--instalado', action='store_true', help='Ejecuta en modo instalado permanente (usa ProgramData).')
    parser.add_argument('--inicializar', action='store_true', help='Autoriza crear una instalación nueva.')
    parser.add_argument('--respaldo', action='store_true', help='Crea copia de seguridad y finaliza sin abrir interfaz.')
    parser.add_argument('--restaurar', metavar='RUTA_DEL_RESPALDO', help='Restaura una copia verificada (solo instalación cerrada).')
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

    if args.restaurar and (modo != 'instalado' or args.respaldo or args.inicializar):
        parser.error('--restaurar requiere --instalado y no se combina con --respaldo ni --inicializar.')

    if modo == 'instalado':
        from desktop.release_gate import require_frozen_production
        require_frozen_production(Path(sys.executable).resolve().parent)

    ruta.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(recursos() / 'backend'))

    from desktop.inicializacion import configurar
    from django.db import connections
    servidor = None
    respaldo_inicio = None
    inicio_normal = False
    from contextlib import nullcontext

    try:
        if args.restaurar:
            from desktop.restauracion import restaurar_con_bloqueo
            resultado = restaurar_con_bloqueo(args.restaurar, ruta, preparar=lambda: configurar(
                ruta, solo_respaldo=True, modo=modo, sid_operador=args.operador_sid))
            print('Restauración completada. Base reemplazada; respaldo de seguridad:', resultado['respaldo_seguridad'])
            return 0

        # El bloqueo de instancia cubre el servidor HTTP: mantenimiento y el
        # instalador pueden detectar una instancia activa mediante este cerrojo.
        with (nullcontext() if args.respaldo else bloqueo_instancia(ruta)):
            if not args.respaldo and not args.restaurar:
                print('No cierres esta ventana mientras uses el sistema. Para salir, cierra la ventana del programa.', flush=True)
            configurar(
                ruta,
                # El acceso directo instalado no lleva argumentos. Autorizar la
                # creacion inicial solo en el paquete congelado evita exigir
                # --inicializar al operador; la configuracion() rechaza una
                # instalacion incompleta o con archivos existentes parciales.
                autorizar_nueva=(args.inicializar or (getattr(sys, 'frozen', False) and modo == 'instalado'))
                    and not args.respaldo,
                solo_respaldo=args.respaldo or bool(args.restaurar),
                modo=modo,
                sid_operador=args.operador_sid
            )
            if args.respaldo:
                from django.conf import settings
                resultado = _crear_respaldo_automatico(settings)
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
            inicio_normal = True
            if _respaldo_vencido(settings):
                def respaldo_en_segundo_plano():
                    try:
                        resultado = _crear_respaldo_automatico(settings)
                        logging.getLogger(__name__).info('Respaldo automático de inicio completado: %s', resultado['archivo'])
                        if resultado['advertencia']:
                            logging.getLogger(__name__).warning('%s', resultado['advertencia'])
                    except Exception:
                        logging.getLogger(__name__).exception('Falló el respaldo automático de inicio')
                respaldo_inicio = threading.Thread(target=respaldo_en_segundo_plano,
                    name='respaldo-inicio', daemon=True)
                respaldo_inicio.start()

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
                    print('WebView2 no está disponible o no pudo abrirse. Se abrirá el navegador predeterminado.')

            import webbrowser
            webbrowser.open(url)
            input('Servidor local activo. Pulsa ENTER aquí para cerrarlo: ')
            servidor.cerrar()
            servidor = None
            return 0
    except Exception as error:
        from desktop.bloqueo_instancia import ErrorPermisoBloqueo
        if isinstance(error, ErrorPermisoBloqueo):
            try:
                _registrar_permiso_bloqueo(error, ruta)
            except Exception:
                # No exponer detalles técnicos; conservar el aviso amigable.
                pass
            print(MENSAJE_CUENTA_NO_AUTORIZADA, file=sys.stderr)
            return 1
        logging.getLogger(__name__).exception('Fallo técnico durante el arranque')
        if args.restaurar:
            print(str(error), file=sys.stderr)
        elif isinstance(error, PermissionError):
            print(MENSAJE_CUENTA_NO_AUTORIZADA, file=sys.stderr)
        else:
            print(_mensaje_inicio(error), file=sys.stderr)
        return 1
    finally:
        if servidor:
            servidor.cerrar()
        from django.conf import settings
        if settings.configured:
            connections.close_all()
            if inicio_normal:
                try:
                    if respaldo_inicio and respaldo_inicio.is_alive():
                        respaldo_inicio.join()
                    if _respaldo_cierre_vencido(settings):
                        resultado = _crear_respaldo_automatico(settings)
                        logging.getLogger(__name__).info('Respaldo automático de cierre completado: %s', resultado['archivo'])
                        if resultado['advertencia']:
                            logging.getLogger(__name__).warning('%s', resultado['advertencia'])
                except Exception:
                    logging.getLogger(__name__).exception('Falló el respaldo automático de cierre')


if __name__ == '__main__':
    sys.exit(main())
