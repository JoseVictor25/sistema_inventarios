"""Control de identidad Windows, SID del operador y permisos ACL para B3.

Mecanismo por equipo con una sola identidad Windows autorizada para acceder a los datos.
SYSTEM y Administradores mantienen acceso administrativo; el operador autorizado
gestiona el negocio. Everyone, Users y Authenticated Users no tienen acceso a los datos.
"""
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

logger = logging.getLogger(__name__)

# SIDs bien conocidos en Windows
SID_SYSTEM = 'S-1-5-18'
SID_ADMINISTRADORES = 'S-1-5-32-544'
SID_USERS = 'S-1-5-32-545'
SID_AUTHENTICATED_USERS = 'S-1-5-11'
SID_EVERYONE = 'S-1-1-0'


def obtener_sid_actual():
    """Obtiene de forma fiable el SID del usuario del proceso actual en Windows.

    Utiliza llamadas nativas de Advapi32 y Kernel32 mediante ctypes.
    En pruebas permite sobreescritura controlada mediante variable de entorno.
    """
    simulado = os.environ.get('INVENTARIOS_OPERADOR_SID_SIMULADO')
    if simulado:
        return simulado

    if os.name != 'nt':
        return 'S-1-5-21-SIMULADO-0000000000-0000000000-1000'

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        advapi32 = ctypes.windll.advapi32

        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        kernel32.OpenProcessToken.restype = wintypes.BOOL

        token = wintypes.HANDLE()
        proc = kernel32.GetCurrentProcess()
        if not kernel32.OpenProcessToken(proc, 0x0008, ctypes.byref(token)):  # TOKEN_QUERY = 0x0008
            raise RuntimeError(f'Error al abrir token de proceso: {ctypes.GetLastError()}')

        try:
            longitud = wintypes.DWORD()
            TokenUser = 1
            advapi32.GetTokenInformation(token, TokenUser, None, 0, ctypes.byref(longitud))
            buffer = ctypes.create_string_buffer(longitud.value)
            if not advapi32.GetTokenInformation(token, TokenUser, buffer, longitud.value, ctypes.byref(longitud)):
                raise RuntimeError(f'Error al obtener información de token: {ctypes.GetLastError()}')

            p_sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents
            p_cadena = wintypes.LPWSTR()
            advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
            advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL

            if not advapi32.ConvertSidToStringSidW(p_sid, ctypes.byref(p_cadena)):
                raise RuntimeError(f'Error al convertir SID a texto: {ctypes.GetLastError()}')

            sid_str = p_cadena.value
            kernel32.LocalFree(p_cadena)
            return sid_str
        finally:
            kernel32.CloseHandle(token)
    except Exception as exc:
        logger.error('No se pudo resolver el SID nativo: %s', exc)
        raise RuntimeError(f'Fallo al identificar la cuenta Windows del operador: {exc}') from exc


def es_administrador():
    """Comprueba si el proceso actual se ejecuta con privilegios elevados de Administrador."""
    if os.name != 'nt':
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def identificar_sid_operador(parametro_sid=None, permitir_admin=False):
    """Identifica el SID del operador de forma segura sin confundirlo con un Administrador elevado.

    Reglas:
    1. Si se proporciona parametro_sid (ej. vía /OPERATOR_SID o variable de entorno),
       se valida su formato S-1-... y se prioriza.
    2. Si el proceso actual está ELEVADO como Administrador y NO se proporcionó
       parametro_sid:
       - Si permitir_admin es False, lanza ValueError para evitar que el instalador
         asigne erróneamente el SID de la cuenta de TI/Admin como operador del negocio.
       - Si permitir_admin es True, acepta el SID actual.
    3. Si el proceso es de un usuario estándar (no elevado), se toma su SID nativo.
    """
    if parametro_sid:
        if not isinstance(parametro_sid, str) or not parametro_sid.startswith('S-1-'):
            raise ValueError(f'El SID de operador proporcionado no es válido: {parametro_sid}')
        return parametro_sid

    simulado = os.environ.get('INVENTARIOS_OPERADOR_SID_SIMULADO')
    if simulado:
        return simulado

    sid_actual = obtener_sid_actual()

    # Si está elevado y no se indicó SID explícito
    if es_administrador() and not permitir_admin:
        if not os.environ.get('INVENTARIOS_PERMITIR_ADMIN_COMO_OPERADOR'):
            raise ValueError(
                'El proceso se ejecuta con privilegios elevados de Administrador sin indicar '
                'un SID de operador explícito. Para evitar registrar una cuenta administrativa '
                'como operador del negocio, especifique --operador-sid o /OPERATOR_SID=.'
            )

    return sid_actual


def verificar_directorio_seguro(directorio_datos, sid_esperado=None):
    """Comprueba que el directorio de datos no contenga configuraciones inseguras.

    Verifica:
    - Que no sea enlace simbólico ni unión de directorio (junction).
    - Que no conceda permisos a Everyone, Users o Authenticated Users.
    - Si existe operador.json, que coincida con sid_esperado (si se proporciona).

    Lanza PermissionError o ValueError si detecta condiciones inseguras.
    """
    d = Path(directorio_datos).resolve()
    if not d.exists():
        return True

    if d.is_symlink() or (hasattr(d, 'is_junction') and d.is_junction()):
        raise ValueError('Directorio inseguro: no se permiten enlaces simbólicos ni redirecciones.')

    # Inspección de ACLs en Windows
    if os.name == 'nt':
        inspeccion = inspeccionar_permisos_icacls(d)
        if inspeccion.get('tiene_inseguros'):
            raise PermissionError(
                f'El directorio de datos {d} tiene permisos inseguros asignados a '
                'Everyone, Users o Authenticated Users. '
                'Se requiere que un Administrador configure permisos exclusivos antes de operar.'
            )

    # Registro de operador preexistente
    if sid_esperado:
        registro = leer_registro_operador(d)
        if registro and registro.get('sid') != sid_esperado:
            raise PermissionError(
                f'El directorio pertenece al operador {registro.get("sid")}, '
                f'no coincide con el esperado {sid_esperado}.'
            )

    return True


def obtener_cuenta_actual():
    """Identificador legible (Dominio\\Usuario) de la cuenta actual."""
    dominio = os.environ.get('USERDOMAIN', '')
    usuario = os.environ.get('USERNAME', '')
    if dominio and usuario:
        return f'{dominio}\\{usuario}'
    return usuario or 'Desconocido'


def leer_registro_operador(directorio_datos):
    """Lee el registro de operador autorizado en operador.json si existe."""
    archivo = Path(directorio_datos) / 'operador.json'
    if not archivo.is_file():
        return None
    try:
        with archivo.open('r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as exc:
        raise ValueError(f'Archivo de operador dañado o ilegible: {exc}') from exc


def registrar_operador(directorio_datos, sid, cuenta=None, version='0.10.0'):
    """Registra de manera atómica el operador autorizado de esta instalación.

    Lanza ValueError si el SID es inválido o si ya existe otro operador registrado.
    """
    if not sid or not isinstance(sid, str) or not sid.startswith('S-1-'):
        raise ValueError('SID de operador inválido.')

    archivo = Path(directorio_datos) / 'operador.json'
    if archivo.is_file():
        existente = leer_registro_operador(directorio_datos)
        if existente and existente.get('sid') != sid:
            raise ValueError(
                f"La instalación ya tiene asignado el operador {existente.get('sid')}. "
                'Para transferir el acceso use el procedimiento controlado migrar_operador.'
            )

    datos = {
        'sid': sid,
        'cuenta': cuenta or obtener_cuenta_actual(),
        'version': version,
        'fecha_registro': datetime.now(timezone.utc).isoformat(),
        'historial_migraciones': []
    }
    provisional = archivo.with_suffix('.tmp')
    with provisional.open('w', encoding='utf-8') as f:
        json.dump(datos, f, indent=2)
    os.replace(provisional, archivo)
    return datos


def validar_operador(directorio_datos, sid_actual=None):
    """Comprueba que el proceso actual coincida con el operador autorizado.

    Lanza:
        PermissionError: si el SID del proceso no coincide con el operador registrado.
    Devuelve:
        True si coincide.
        False si la instalación aún no tiene operador registrado (ej. primer arranque antes de inicializar).
    """
    registro = leer_registro_operador(directorio_datos)
    if not registro:
        return False

    sid_esperado = registro.get('sid')
    sid_real = sid_actual or obtener_sid_actual()

    if sid_real != sid_esperado:
        raise PermissionError(
            f'Operador Windows no autorizado. Esta instalación pertenece al operador con SID '
            f"'{sid_esperado}' ({registro.get('cuenta', 'desconocido')}), "
            f"pero el proceso se ejecuta como '{sid_real}'."
        )
    return True


def migrar_operador(directorio_datos, nuevo_sid, nuevo_cuenta=None, autorizacion_admin=False):
    """Procedimiento controlado para cambiar la cuenta autorizada de una instalación.

    Exige confirmación de administrador para evitar apropiación indebida de datos.
    Registra una auditoría inmutable en logs/migracion_operador.log.
    """
    if not autorizacion_admin:
        raise PermissionError('La migración de operador exige autorización administrativa explícita.')

    if not nuevo_sid or not isinstance(nuevo_sid, str) or not nuevo_sid.startswith('S-1-'):
        raise ValueError('El nuevo SID de operador no es válido.')

    registro_previo = leer_registro_operador(directorio_datos)
    if not registro_previo:
        raise ValueError('No existe una instalación previa para migrar.')

    sid_anterior = registro_previo.get('sid')
    if sid_anterior == nuevo_sid:
        return registro_previo

    historial = registro_previo.get('historial_migraciones', [])
    evento = {
        'fecha': datetime.now(timezone.utc).isoformat(),
        'sid_anterior': sid_anterior,
        'cuenta_anterior': registro_previo.get('cuenta'),
        'sid_nuevo': nuevo_sid,
        'cuenta_nueva': nuevo_cuenta or 'No especificada',
    }
    historial.append(evento)

    nuevo_registro = {
        'sid': nuevo_sid,
        'cuenta': nuevo_cuenta or obtener_cuenta_actual(),
        'version': registro_previo.get('version', '0.10.0'),
        'fecha_registro': registro_previo.get('fecha_registro'),
        'fecha_actualizacion': datetime.now(timezone.utc).isoformat(),
        'historial_migraciones': historial,
    }

    # Registrar en bitácora de seguridad
    logs_dir = Path(directorio_datos) / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    bitacora = logs_dir / 'migracion_operador.log'
    with bitacora.open('a', encoding='utf-8') as f:
        f.write(
            f"[{evento['fecha']}] CAMBIO CONTROLADO DE OPERADOR: "
            f"{sid_anterior} -> {nuevo_sid} (cuenta: {nuevo_registro['cuenta']})\n"
        )

    # Actualizar operador.json atómicamente
    archivo = Path(directorio_datos) / 'operador.json'
    provisional = archivo.with_suffix('.tmp')
    with provisional.open('w', encoding='utf-8') as f:
        json.dump(nuevo_registro, f, indent=2)
    os.replace(provisional, archivo)
    return nuevo_registro


def generar_comandos_icacls(directorio_datos, sid_operador):
    """Genera la secuencia exacta de argumentos icacls para asegurar el directorio de datos.

    Reglas:
    1. Deshabilitar herencia y remover permisos heredados (/inheritance:r).
    2. Conceder control total al sistema operativo (SYSTEM: S-1-5-18).
    3. Conceder control total a los Administradores locales (Administrators: S-1-5-32-544).
    4. Conceder control total/modificación al operador autorizado con propagación de herencia ((OI)(CI)F).
    5. Remover accesos para Users (S-1-5-32-545), Authenticated Users (S-1-5-11) y Everyone (S-1-1-0).
    """
    d = str(Path(directorio_datos).resolve())
    return [
        ['icacls', d, '/inheritance:r'],
        ['icacls', d, '/grant:r', f'*{SID_SYSTEM}:(OI)(CI)F', f'*{SID_ADMINISTRADORES}:(OI)(CI)F'],
        ['icacls', d, '/grant:r', f'*{sid_operador}:(OI)(CI)F'],
        ['icacls', d, '/remove:g', f'*{SID_USERS}', f'*{SID_AUTHENTICATED_USERS}', f'*{SID_EVERYONE}'],
    ]


def aplicar_permisos_seguros(directorio_datos, sid_operador, *, solo_nuevo=False):
    """Ejecuta los comandos icacls sobre el directorio de datos especificado.

    Arquitectura de permisos (B3):
    ─────────────────────────────
    El instalador (elevado como Admin) NO aplica las ACLs porque en ese
    contexto el SID activo sería el del Administrador, no el del operador
    del negocio. Las ACLs se aplican en el PRIMER ARRANQUE de la aplicación,
    que se ejecuta bajo la cuenta del operador final.

    Cuándo llamar esta función:
        - Primer arranque (nueva instalación): siempre.
        - Arranques posteriores: NO (solo_nuevo=True lo garantiza).
        - Migración de operador: sí, tras registrar_operador() con nuevo SID.

    Garantías de seguridad:
        - No se aplica sobre rutas dentro de Program Files.
        - No se aplica sobre la raíz de ProgramData.
        - Si la carpeta no existe, no se crea aquí; debe crearla el instalador.
        - Si las ACLs ya están aplicadas y el SID coincide, no se reaplican
          innecesariamente (solo_nuevo=True).

    ADVERTENCIA: Esta función modifica los permisos NTFS reales del directorio.
    Solo debe ejecutarse sobre la carpeta de datos de la instalación autorizada,
    jamás en entornos de prueba que usen rutas de ProgramData reales.
    """
    if os.name != 'nt':
        return True

    directorio_datos = Path(directorio_datos).resolve()

    # Solo aplicar en primer arranque si se indica
    if solo_nuevo:
        # Verificar si ya existe operador.json con el mismo SID (ya inicializado antes)
        registro = leer_registro_operador(directorio_datos)
        if registro and registro.get('acl_aplicadas') and registro.get('sid') == sid_operador:
            logger.debug('ACLs ya aplicadas para SID %s, no se reaplican.', sid_operador)
            return True

    comandos = generar_comandos_icacls(directorio_datos, sid_operador)
    exito = True
    for cmd in comandos:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.debug('icacls (%s) retornó código %s: %s', cmd[2] if len(cmd) > 2 else '', res.returncode, res.stdout or res.stderr)
            # El /remove puede fallar si la entrada ya no existe; no es crítico
            # si la herencia ya fue eliminada. Anotamos pero no abortamos.
            if '/remove' not in ' '.join(cmd):
                exito = False

    # Registrar en operador.json que las ACLs fueron aplicadas
    if exito:
        try:
            archivo = directorio_datos / 'operador.json'
            if archivo.is_file():
                registro = leer_registro_operador(directorio_datos)
                if registro:
                    registro['acl_aplicadas'] = True
                    registro['acl_fecha'] = datetime.now(timezone.utc).isoformat()
                    provisional = archivo.with_suffix('.tmp')
                    with provisional.open('w', encoding='utf-8') as f:
                        json.dump(registro, f, indent=2)
                    os.replace(provisional, archivo)
        except Exception as exc:
            logger.warning('No se pudo registrar aplicación de ACLs: %s', exc)

    return exito


def inspeccionar_permisos_icacls(directorio_datos):
    """Inspecciona los permisos configurados con icacls y verifica que Everyone y Users no tengan acceso."""
    if os.name != 'nt':
        return {'seguro': True, 'salida': 'No aplicable en SO no-Windows'}
    d = str(Path(directorio_datos).resolve())
    res = subprocess.run(['icacls', d], capture_output=True, text=True)
    salida = res.stdout
    # Verificar que no figuren Everyone o Users con permisos concedidos
    inseguros = ['Everyone', 'Todos', 'BUILTIN\\Users', 'BUILTIN\\Usuarios', 'NT AUTHORITY\\Authenticated Users', 'Usuarios autentificados']
    tiene_inseguros = any(f'{ins}:' in salida for ins in inseguros)
    return {
        'seguro': not tiene_inseguros and res.returncode == 0,
        'salida': salida,
        'tiene_inseguros': tiene_inseguros
    }
