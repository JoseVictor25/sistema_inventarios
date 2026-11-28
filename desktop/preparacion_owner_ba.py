"""Preparación NTFS T1-B, bloqueada para producción hasta aprobar T1-B.

El núcleo Win32 usa el método B: crea con DACL protegida, asigna después BA
como owner por handle y verifica el mismo objeto. El arnés N1 vive en scripts/
y no forma parte del paquete congelado.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import sys
import tempfile

SID_SYSTEM = "S-1-5-18"
SID_BA = "S-1-5-32-544"
OPERATOR_MODIFY = 0x001301BF
FILE_ALL_ACCESS = 0x001F01FF
ACE_OBJECT_INHERIT = 0x01
ACE_CONTAINER_INHERIT = 0x02
SE_DACL_PROTECTED = 0x1000

TOKEN_QUERY = 0x0008
TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_GROUPS_CLASS = 2
TOKEN_PRIVILEGES_CLASS = 3
TOKEN_ELEVATION_CLASS = 20
SE_GROUP_ENABLED = 0x00000004
SE_GROUP_OWNER = 0x00000008
SE_GROUP_USE_FOR_DENY_ONLY = 0x00000010
SE_PRIVILEGE_ENABLED = 0x00000002
ERROR_NO_TOKEN = 1008
ERROR_INSUFFICIENT_BUFFER = 122
ERROR_NOT_ALL_ASSIGNED = 1300
ERROR_ALREADY_EXISTS = 183
PROGRAMDATA_PARENT_VALIDATION_ID = None

READ_CONTROL = 0x00020000
WRITE_OWNER = 0x00080000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
FILE_INFO_BY_HANDLE_CLASS_FILE_ATTRIBUTE_TAG_INFO = 9
SE_FILE_OBJECT = 1
OWNER_SECURITY_INFORMATION = 0x00000001
DACL_SECURITY_INFORMATION = 0x00000004
ACL_SIZE_INFORMATION_CLASS = 2
ACCESS_ALLOWED_ACE_TYPE = 0
SECURITY_DESCRIPTOR_REVISION = 1


class PreparacionOwnerError(RuntimeError):
    """La carpeta no pudo prepararse y verificarse de forma completa."""


@dataclass(frozen=True)
class VerificacionDirectorio:
    owner_sid: str
    dacl_exacta_y_protegida: bool


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", ctypes.c_uint32), ("HighPart", ctypes.c_int32)]


class LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", LUID), ("Attributes", ctypes.c_uint32)]


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", ctypes.c_uint32)]


class TOKEN_GROUPS(ctypes.Structure):
    # ANYSIZE_ARRAY. ctypes conserva la alineación nativa del puntero x64.
    _fields_ = [("GroupCount", ctypes.c_uint32), ("Groups", SID_AND_ATTRIBUTES * 1)]


class TOKEN_PRIVILEGES(ctypes.Structure):
    # ANYSIZE_ARRAY; LUID_AND_ATTRIBUTES tiene alineación de 4 y tamaño 12.
    _fields_ = [("PrivilegeCount", ctypes.c_uint32),
                ("Privileges", LUID_AND_ATTRIBUTES * 1)]


class TOKEN_ELEVATION(ctypes.Structure):
    _fields_ = [("TokenIsElevated", ctypes.c_uint32)]


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("nLength", ctypes.c_uint32),
                ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", ctypes.c_int32)]


class ACE_HEADER(ctypes.Structure):
    _fields_ = [("AceType", ctypes.c_ubyte), ("AceFlags", ctypes.c_ubyte),
                ("AceSize", ctypes.c_uint16)]


class ACL_SIZE_INFORMATION(ctypes.Structure):
    _fields_ = [("AceCount", ctypes.c_uint32), ("AclBytesInUse", ctypes.c_uint32),
                ("AclBytesFree", ctypes.c_uint32)]


class FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
    _fields_ = [("FileAttributes", ctypes.c_uint32), ("ReparseTag", ctypes.c_uint32)]


class Win32SecurityApi:
    """WinAPI tipada; instanciar solo en Windows."""

    def __init__(self):
        if os.name != "nt":
            raise OSError("La preparación T1-B solo está disponible en Windows.")
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        self._declare_prototypes()

    def _declare_prototypes(self):
        H = ctypes.c_void_p
        D = ctypes.c_uint32
        B = ctypes.c_int32
        P = ctypes.POINTER
        k, a = self.kernel32, self.advapi32

        k.GetCurrentThread.argtypes, k.GetCurrentThread.restype = [], H
        k.GetCurrentProcess.argtypes, k.GetCurrentProcess.restype = [], H
        k.CloseHandle.argtypes, k.CloseHandle.restype = [H], B
        k.CreateDirectoryW.argtypes = [wintypes.LPCWSTR, P(SECURITY_ATTRIBUTES)]
        k.CreateDirectoryW.restype = B
        k.CreateFileW.argtypes = [wintypes.LPCWSTR, D, D, P(SECURITY_ATTRIBUTES), D, D, H]
        k.CreateFileW.restype = H
        k.GetFileInformationByHandleEx.argtypes = [H, D, H, D]
        k.GetFileInformationByHandleEx.restype = B
        k.GetFinalPathNameByHandleW.argtypes = [H, wintypes.LPWSTR, D, D]
        k.GetFinalPathNameByHandleW.restype = D
        k.LocalFree.argtypes, k.LocalFree.restype = [H], H

        a.OpenThreadToken.argtypes = [H, D, B, P(H)]
        a.OpenThreadToken.restype = B
        a.OpenProcessToken.argtypes = [H, D, P(H)]
        a.OpenProcessToken.restype = B
        a.GetTokenInformation.argtypes = [H, D, H, D, P(D)]
        a.GetTokenInformation.restype = B
        a.LookupPrivilegeValueW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, P(LUID)]
        a.LookupPrivilegeValueW.restype = B
        a.AdjustTokenPrivileges.argtypes = [H, B, P(TOKEN_PRIVILEGES), D,
                                            P(TOKEN_PRIVILEGES), P(D)]
        a.AdjustTokenPrivileges.restype = B
        a.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, P(H)]
        a.ConvertStringSidToSidW.restype = B
        a.ConvertSidToStringSidW.argtypes = [H, P(wintypes.LPWSTR)]
        a.ConvertSidToStringSidW.restype = B
        a.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR, D, P(H), P(D)]
        a.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = B
        a.SetSecurityInfo.argtypes = [H, D, D, H, H, H, H]
        a.SetSecurityInfo.restype = D
        a.GetSecurityInfo.argtypes = [H, D, D, P(H), P(H), P(H), P(H), P(H)]
        a.GetSecurityInfo.restype = D
        a.GetSecurityDescriptorControl.argtypes = [H, P(ctypes.c_uint16), P(D)]
        a.GetSecurityDescriptorControl.restype = B
        a.GetAclInformation.argtypes = [H, H, D, D]
        a.GetAclInformation.restype = B
        a.GetAce.argtypes = [H, D, P(H)]
        a.GetAce.restype = B
        a.IsValidSid.argtypes, a.IsValidSid.restype = [H], B
        a.GetLengthSid.argtypes, a.GetLengthSid.restype = [H], D
        a.EqualSid.argtypes, a.EqualSid.restype = [H, H], B

    @staticmethod
    def _winerror(code=None):
        code = ctypes.get_last_error() if code is None else code
        return OSError(code, ctypes.FormatError(code).strip())

    def _token_handle(self):
        token = ctypes.c_void_p()
        desired = TOKEN_QUERY | TOKEN_ADJUST_PRIVILEGES
        if self.advapi32.OpenThreadToken(
                self.kernel32.GetCurrentThread(), desired, True, ctypes.byref(token)):
            return token, True
        error = ctypes.get_last_error()
        if error != ERROR_NO_TOKEN:
            raise PreparacionOwnerError(
                f"No se pudo abrir el token efectivo del hilo (WinError {error}).")
        if not self.advapi32.OpenProcessToken(
                self.kernel32.GetCurrentProcess(), desired, ctypes.byref(token)):
            raise PreparacionOwnerError(
                f"No se pudo abrir el token efectivo del proceso (WinError {ctypes.get_last_error()}).")
        return token, True

    @contextmanager
    def effective_token(self):
        token, _ = self._token_handle()
        try:
            elevation = TOKEN_ELEVATION()
            returned = ctypes.c_uint32()
            if not self.advapi32.GetTokenInformation(
                    token, TOKEN_ELEVATION_CLASS, ctypes.byref(elevation),
                    ctypes.sizeof(elevation), ctypes.byref(returned)):
                raise PreparacionOwnerError(
                    f"No se pudo comprobar elevación (WinError {ctypes.get_last_error()}).")
            expected_size = ctypes.sizeof(TOKEN_ELEVATION)
            if returned.value != expected_size:
                raise PreparacionOwnerError(
                    f"TOKEN_ELEVATION returned invalid size ({returned.value}; expected {expected_size}).")
            if not elevation.TokenIsElevated:
                raise PreparacionOwnerError("La preparación requiere un token elevado.")
            if not self.ba_enabled(token):
                raise PreparacionOwnerError("BA debe estar habilitado en el token efectivo.")
            yield token
        finally:
            if token and not self.kernel32.CloseHandle(token):
                raise PreparacionOwnerError(
                    f"No se pudo cerrar el token (WinError {ctypes.get_last_error()}).")

    def _token_buffer(self, token, information_class):
        minimum_sizes = {
            TOKEN_GROUPS_CLASS: TOKEN_GROUPS.Groups.offset,
            TOKEN_PRIVILEGES_CLASS: TOKEN_PRIVILEGES.Privileges.offset,
        }
        minimum_size = minimum_sizes.get(information_class)
        if minimum_size is None:
            raise PreparacionOwnerError(
                f"Unsupported variable token information class ({information_class}).")
        needed = ctypes.c_uint32()
        ctypes.set_last_error(0)
        ok = self.advapi32.GetTokenInformation(
            token, information_class, None, 0, ctypes.byref(needed))
        error = ctypes.get_last_error()
        if ok:
            raise PreparacionOwnerError("Token size query unexpectedly succeeded with a null buffer.")
        if error != ERROR_INSUFFICIENT_BUFFER:
            raise PreparacionOwnerError(
                f"Consulta de token sin tamaño válido (WinError {error}).")
        if needed.value < minimum_size:
            raise PreparacionOwnerError(
                f"Invalid token buffer size ({needed.value}; minimum {minimum_size}).")
        buffer = ctypes.create_string_buffer(needed.value)
        returned = ctypes.c_uint32()
        if not self.advapi32.GetTokenInformation(
                token, information_class, buffer, needed.value, ctypes.byref(returned)):
            raise PreparacionOwnerError(
                f"No se pudo leer el token (WinError {ctypes.get_last_error()}).")
        if returned.value < minimum_size or returned.value > needed.value:
            raise PreparacionOwnerError(
                f"Tamaño devuelto inválido ({returned.value}; mínimo {minimum_size}, "
                f"buffer asignado {needed.value}).")
        return buffer, returned.value

    def _ba_group_attributes(self, token):
        buffer, length = self._token_buffer(token, TOKEN_GROUPS_CLASS)
        offset = TOKEN_GROUPS.Groups.offset
        item_size = ctypes.sizeof(SID_AND_ATTRIBUTES)
        if length < offset:
            raise PreparacionOwnerError("TOKEN_GROUPS no contiene su cabecera completa.")
        count = ctypes.c_uint32.from_buffer(buffer).value
        if count > (length - offset) // item_size:
            raise PreparacionOwnerError("TOKEN_GROUPS truncado o malformado.")
        ba = self._sid_pointer(SID_BA)
        try:
            for index in range(count):
                entry = SID_AND_ATTRIBUTES.from_buffer(buffer, offset + index * item_size)
                if entry.Sid and self.advapi32.EqualSid(entry.Sid, ba):
                    return entry.Attributes
            return None
        finally:
            self.kernel32.LocalFree(ba)

    def ba_owner_assignable(self, token):
        flags = self._ba_group_attributes(token)
        return (flags is not None and bool(flags & SE_GROUP_OWNER)
                and not bool(flags & SE_GROUP_USE_FOR_DENY_ONLY))

    def ba_enabled(self, token):
        flags = self._ba_group_attributes(token)
        return (flags is not None and bool(flags & SE_GROUP_ENABLED)
                and not bool(flags & SE_GROUP_USE_FOR_DENY_ONLY))

    def _sid_pointer(self, sid_text):
        sid = ctypes.c_void_p()
        if not self.advapi32.ConvertStringSidToSidW(sid_text, ctypes.byref(sid)):
            raise PreparacionOwnerError(
                f"SID inválido {sid_text!r} (WinError {ctypes.get_last_error()}).")
        if not self.advapi32.IsValidSid(sid):
            self.kernel32.LocalFree(sid)
            raise PreparacionOwnerError(f"Windows rechazó la estructura SID {sid_text!r}.")
        return sid

    def _lookup_restore_luid(self):
        luid = LUID()
        if not self.advapi32.LookupPrivilegeValueW(None, "SeRestorePrivilege", ctypes.byref(luid)):
            raise PreparacionOwnerError(
                f"No se pudo resolver SeRestorePrivilege (WinError {ctypes.get_last_error()}).")
        return luid

    def _privilege_state(self, token, wanted_luid):
        buffer, length = self._token_buffer(token, TOKEN_PRIVILEGES_CLASS)
        offset = TOKEN_PRIVILEGES.Privileges.offset
        item_size = ctypes.sizeof(LUID_AND_ATTRIBUTES)
        if length < offset:
            raise PreparacionOwnerError("TOKEN_PRIVILEGES no contiene su cabecera completa.")
        count = ctypes.c_uint32.from_buffer(buffer).value
        if count > (length - offset) // item_size:
            raise PreparacionOwnerError("TOKEN_PRIVILEGES truncado o malformado.")
        for index in range(count):
            entry = LUID_AND_ATTRIBUTES.from_buffer(buffer, offset + index * item_size)
            if (entry.Luid.LowPart, entry.Luid.HighPart) == (
                    wanted_luid.LowPart, wanted_luid.HighPart):
                return entry.Attributes
        return None

    def owner_assignment_available(self, token):
        """Preflight before creating anything; does not enable privileges."""
        if self.ba_owner_assignable(token):
            return
        luid = self._lookup_restore_luid()
        if self._privilege_state(token, luid) is None:
            raise PreparacionOwnerError(
                "BA no es asignable y el token no contiene SeRestorePrivilege.")

    def _enable_restore_privilege(self, token, luid, old_attributes):
        requested = TOKEN_PRIVILEGES()
        requested.PrivilegeCount = 1
        requested.Privileges[0].Luid = luid
        requested.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
        previous_raw = ctypes.create_string_buffer(ctypes.sizeof(TOKEN_PRIVILEGES))
        previous = ctypes.cast(previous_raw, ctypes.POINTER(TOKEN_PRIVILEGES))
        returned = ctypes.c_uint32()
        ctypes.set_last_error(0)
        ok = self.advapi32.AdjustTokenPrivileges(
            token, False, ctypes.byref(requested), ctypes.sizeof(previous_raw),
            previous, ctypes.byref(returned))
        error = ctypes.get_last_error()
        if not ok:
            raise PreparacionOwnerError(f"No se pudo habilitar SeRestorePrivilege (WinError {error}).")
        if error == ERROR_NOT_ALL_ASSIGNED:
            raise PreparacionOwnerError("El token no tiene SeRestorePrivilege asignable.")
        if error != 0:
            raise PreparacionOwnerError(f"Ajuste de SeRestorePrivilege incompleto (WinError {error}).")
        if returned.value < TOKEN_PRIVILEGES.Privileges.offset + ctypes.sizeof(LUID_AND_ATTRIBUTES):
            # Aun ante PreviousState anómalo, restaurar el estado observado
            # antes de fallar, en lugar de dejar el privilegio habilitado.
            fallback = TOKEN_PRIVILEGES()
            fallback.PrivilegeCount = 1
            fallback.Privileges[0].Luid = luid
            fallback.Privileges[0].Attributes = old_attributes
            self._restore_privilege_state(token, bytes(fallback))
            raise PreparacionOwnerError("PreviousState de SeRestorePrivilege no es válido.")
        if returned.value > ctypes.sizeof(previous_raw):
            fallback = TOKEN_PRIVILEGES()
            fallback.PrivilegeCount = 1
            fallback.Privileges[0].Luid = luid
            fallback.Privileges[0].Attributes = old_attributes
            self._restore_privilege_state(token, bytes(fallback))
            raise PreparacionOwnerError("PreviousState excede el buffer reservado.")
        previous_bytes = bytes(previous_raw.raw[:returned.value])
        previous_info = TOKEN_PRIVILEGES.from_buffer_copy(previous_bytes)
        previous_entry = previous_info.Privileges[0]
        if (previous_info.PrivilegeCount != 1
                or (previous_entry.Luid.LowPart, previous_entry.Luid.HighPart)
                != (luid.LowPart, luid.HighPart)
                or previous_entry.Attributes != old_attributes):
            fallback = TOKEN_PRIVILEGES()
            fallback.PrivilegeCount = 1
            fallback.Privileges[0].Luid = luid
            fallback.Privileges[0].Attributes = old_attributes
            self._restore_privilege_state(token, bytes(fallback))
            raise PreparacionOwnerError("PreviousState no coincide con el estado original consultado.")
        return previous_bytes

    def _restore_privilege_state(self, token, previous_state):
        raw = ctypes.create_string_buffer(previous_state)
        previous = ctypes.cast(raw, ctypes.POINTER(TOKEN_PRIVILEGES))
        ctypes.set_last_error(0)
        ok = self.advapi32.AdjustTokenPrivileges(
            token, False, previous, len(previous_state), None, None)
        error = ctypes.get_last_error()
        if not ok or error != 0:
            raise PreparacionOwnerError(
                f"No se pudo restaurar SeRestorePrivilege (WinError {error}).")

    @contextmanager
    def restore_privilege_temporarily(self, token, *, force=False):
        """Habilita SeRestore solo si hace falta; conserva y restaura PreviousState."""
        with _restore_privilege_scope(self, token, force=force) as enabled:
            yield enabled

    def _descriptor_for_operator(self, sid_operator):
        if (not isinstance(sid_operator, str)
                or not re.fullmatch(r"S-1-(?:[0-9]+-)+[0-9]+", sid_operator)
                or sid_operator in {SID_SYSTEM, SID_BA}):
            raise ValueError("El SID de operador no es válido o colisiona con un SID reservado.")
        # Convertir el SID antes de interpolarlo evita aceptar un valor que
        # SDDL pudiera interpretar como sintaxis adicional.
        operator_sid = self._sid_pointer(sid_operator)
        self.kernel32.LocalFree(operator_sid)
        sddl = (f"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
                f"(A;OICI;0x{OPERATOR_MODIFY:08x};;;{sid_operator})")
        descriptor = ctypes.c_void_p()
        size = ctypes.c_uint32()
        if not self.advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl, SECURITY_DESCRIPTOR_REVISION, ctypes.byref(descriptor), ctypes.byref(size)):
            raise PreparacionOwnerError(
                f"No se pudo construir la DACL protegida (WinError {ctypes.get_last_error()}).")
        return descriptor

    @contextmanager
    def _descriptor(self, sid_operator):
        descriptor = self._descriptor_for_operator(sid_operator)
        try:
            yield descriptor
        finally:
            self.kernel32.LocalFree(descriptor)

    def create_directory_protected(self, path, sid_operator):
        with self._descriptor(sid_operator) as descriptor:
            attributes = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), descriptor, False)
            if self.kernel32.CreateDirectoryW(str(path), ctypes.byref(attributes)):
                return True
            error = ctypes.get_last_error()
            if error == ERROR_ALREADY_EXISTS:
                return False
            raise PreparacionOwnerError(f"CreateDirectoryW falló (WinError {error}).")

    @contextmanager
    def open_directory(self, path):
        handle = self.kernel32.CreateFileW(
            str(path), READ_CONTROL | WRITE_OWNER, FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None)
        invalid = ctypes.c_void_p(-1).value
        if not handle or handle == invalid:
            raise PreparacionOwnerError(
                f"CreateFileW no pudo fijar el directorio (WinError {ctypes.get_last_error()}).")
        try:
            yield handle
        finally:
            if not self.kernel32.CloseHandle(handle):
                raise PreparacionOwnerError(
                    f"No se pudo cerrar el handle del directorio (WinError {ctypes.get_last_error()}).")

    def set_owner_ba(self, handle):
        ba = self._sid_pointer(SID_BA)
        try:
            # SetSecurityInfo devuelve el código Win32 directamente, no usa
            # GetLastError para comunicar el fallo.
            status = self.advapi32.SetSecurityInfo(
                handle, SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION,
                ba, None, None, None)
            if status != 0:
                raise PreparacionOwnerError(f"SetSecurityInfo falló (WinError {status}).")
        finally:
            self.kernel32.LocalFree(ba)

    def verify_handle(self, handle, sid_operator, expected_path=None):
        owner = ctypes.c_void_p()
        dacl = ctypes.c_void_p()
        descriptor = ctypes.c_void_p()
        status = self.advapi32.GetSecurityInfo(
            handle, SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
            ctypes.byref(owner), None, ctypes.byref(dacl), None, ctypes.byref(descriptor))
        if status != 0:
            raise PreparacionOwnerError(f"GetSecurityInfo falló (WinError {status}).")
        expected = [(SID_SYSTEM, FILE_ALL_ACCESS), (SID_BA, FILE_ALL_ACCESS),
                    (sid_operator, OPERATOR_MODIFY)]
        try:
            control = ctypes.c_uint16()
            revision = ctypes.c_uint32()
            if not self.advapi32.GetSecurityDescriptorControl(
                    descriptor, ctypes.byref(control), ctypes.byref(revision)):
                raise PreparacionOwnerError(
                    f"No se pudo consultar control del descriptor (WinError {ctypes.get_last_error()}).")
            if not (control.value & SE_DACL_PROTECTED) or not dacl:
                raise PreparacionOwnerError("La DACL no está protegida o no está presente.")
            acl_info = ACL_SIZE_INFORMATION()
            if not self.advapi32.GetAclInformation(
                    dacl, ctypes.byref(acl_info), ctypes.sizeof(acl_info), ACL_SIZE_INFORMATION_CLASS):
                raise PreparacionOwnerError(
                    f"No se pudo consultar la ACL (WinError {ctypes.get_last_error()}).")
            if acl_info.AceCount != 3:
                raise PreparacionOwnerError("La DACL no contiene exactamente tres ACE.")

            base = ctypes.cast(dacl, ctypes.c_void_p).value
            acl_header_size = 8
            acl_size = ctypes.c_uint16.from_address(base + 2).value
            if acl_size < acl_header_size or acl_info.AclBytesInUse > acl_size:
                raise PreparacionOwnerError("ACL con tamaño incoherente.")
            parsed = []
            for index in range(acl_info.AceCount):
                ace_ptr = ctypes.c_void_p()
                if not self.advapi32.GetAce(dacl, index, ctypes.byref(ace_ptr)) or not ace_ptr.value:
                    raise PreparacionOwnerError(
                        f"GetAce falló para ACE {index} (WinError {ctypes.get_last_error()}).")
                ace_address = ace_ptr.value
                header = ACE_HEADER.from_address(ace_address)
                relative = ace_address - base
                if (relative < acl_header_size or header.AceSize < 16
                        or relative + header.AceSize > acl_info.AclBytesInUse):
                    raise PreparacionOwnerError("ACE fuera de los límites de la ACL.")
                if header.AceType != ACCESS_ALLOWED_ACE_TYPE or header.AceFlags != (
                        ACE_OBJECT_INHERIT | ACE_CONTAINER_INHERIT):
                    raise PreparacionOwnerError("Tipo o flags de ACE inesperados.")
                mask = ctypes.c_uint32.from_address(ace_address + 4).value
                sid_ptr = ctypes.c_void_p(ace_address + 8)
                subauthority_count = ctypes.c_ubyte.from_address(ace_address + 9).value
                sid_length_expected = 8 + 4 * subauthority_count
                if 8 + sid_length_expected != header.AceSize:
                    raise PreparacionOwnerError("La longitud SID no cabe dentro del ACE.")
                if not self.advapi32.IsValidSid(sid_ptr):
                    raise PreparacionOwnerError("SID de ACE inválido.")
                sid_length = self.advapi32.GetLengthSid(sid_ptr)
                if sid_length <= 0 or 8 + sid_length != header.AceSize:
                    raise PreparacionOwnerError("El SID no cabe exactamente dentro de AceSize.")
                sid_text_pointer = wintypes.LPWSTR()
                if not self.advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(sid_text_pointer)):
                    raise PreparacionOwnerError(
                        f"No se pudo convertir el SID de ACE (WinError {ctypes.get_last_error()}).")
                try:
                    parsed.append((sid_text_pointer.value, header.AceType,
                                   header.AceFlags, mask))
                finally:
                    self.kernel32.LocalFree(ctypes.cast(sid_text_pointer, ctypes.c_void_p))
            expected_rows = [(sid, ACCESS_ALLOWED_ACE_TYPE,
                              ACE_OBJECT_INHERIT | ACE_CONTAINER_INHERIT, mask)
                             for sid, mask in expected]
            if sorted(parsed) != sorted(expected_rows):
                # El orden exacto se fija en la política compartida.
                raise PreparacionOwnerError("La DACL no coincide exactamente con la política T1.")

            ba = self._sid_pointer(SID_BA)
            try:
                if not self.advapi32.EqualSid(owner, ba):
                    raise PreparacionOwnerError("El owner observado no es BUILTIN\\Administradores.")
            finally:
                self.kernel32.LocalFree(ba)
            tag_info = FILE_ATTRIBUTE_TAG_INFO()
            if not self.kernel32.GetFileInformationByHandleEx(
                    handle, FILE_INFO_BY_HANDLE_CLASS_FILE_ATTRIBUTE_TAG_INFO,
                    ctypes.byref(tag_info), ctypes.sizeof(tag_info)):
                raise PreparacionOwnerError(
                    f"No se pudieron consultar atributos del handle (WinError {ctypes.get_last_error()}).")
            if tag_info.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT:
                raise PreparacionOwnerError("El objeto abierto es un reparse point.")
            if expected_path is not None:
                self._verify_final_path(handle, expected_path)
            return VerificacionDirectorio(SID_BA, True)
        finally:
            if descriptor:
                self.kernel32.LocalFree(descriptor)

    def _verify_final_path(self, handle, expected_path):
        buffer = ctypes.create_unicode_buffer(32768)
        length = self.kernel32.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            raise PreparacionOwnerError(
                f"No se pudo consultar la ruta final del handle (WinError {ctypes.get_last_error()}).")
        final_path = buffer.value
        if final_path.startswith("\\\\?\\"):
            final_path = final_path[4:]
        expected = os.path.abspath(os.path.normpath(str(expected_path)))
        actual = os.path.abspath(os.path.normpath(final_path))
        if os.path.normcase(actual) != os.path.normcase(expected):
            raise PreparacionOwnerError("La ruta final del handle no coincide con el destino solicitado.")


def _path_is_under(path, parent):
    try:
        Path(path).resolve(strict=False).relative_to(Path(parent).resolve(strict=False))
        return True
    except (ValueError, OSError, RuntimeError):
        return False


@contextmanager
def _restore_privilege_scope(api, token, *, force=False):
    """Estado de SeRestore aislado para pruebas con un API simulado."""
    if not force and api.ba_owner_assignable(token):
        yield False
        return
    luid = api._lookup_restore_luid()
    old_attributes = api._privilege_state(token, luid)
    if old_attributes is None:
        raise PreparacionOwnerError("El token no contiene SeRestorePrivilege.")
    if old_attributes & SE_PRIVILEGE_ENABLED:
        yield True
        return
    previous = api._enable_restore_privilege(token, luid, old_attributes)
    try:
        yield True
    finally:
        api._restore_privilege_state(token, previous)
        if api._privilege_state(token, luid) != old_attributes:
            raise PreparacionOwnerError(
                "SeRestorePrivilege no volvió al estado original tras restaurarlo.")


def _validate_scope(path, *, n1_temp_root=None):
    from .rutas import PROGRAM_DATA_DIR
    target = Path(path)
    if not target.is_absolute() or str(target).startswith("\\\\"):
        raise PreparacionOwnerError("La ruta debe ser local y absoluta.")
    if getattr(sys, "frozen", False):
        expected = Path(PROGRAM_DATA_DIR)
        if os.path.normcase(os.path.abspath(os.path.normpath(str(target)))) != os.path.normcase(
                os.path.abspath(os.path.normpath(str(expected)))):
            raise PreparacionOwnerError("El ejecutable congelado solo admite ProgramData\\SistemaInventarios.")
    elif (n1_temp_root is None
          or Path(n1_temp_root).resolve(strict=False) != Path(tempfile.gettempdir()).resolve(strict=False)
          or Path(target).resolve(strict=False) == Path(tempfile.gettempdir()).resolve(strict=False)
          or not _path_is_under(target, tempfile.gettempdir())):
        raise PreparacionOwnerError("En desarrollo, el núcleo solo admite la raíz TEMP autorizada por el arnés N1.")
    if target == target.parent:
        raise PreparacionOwnerError("No se admite la raíz de una unidad.")
    from .release_gate import _reject_reparse_components
    try:
        _reject_reparse_components(target)
    except Exception as exc:
        raise PreparacionOwnerError(f"No se pudo validar la cadena de ruta: {exc}") from exc
    return target


def _prepare_directory_b(path, sid_operator, *, api=None, n1_temp_root=None):
    """Núcleo común privado. En source solo admite TEMP; frozen, solo ruta fija.

    No borra ni repara objetos existentes. Un objeto preexistente debe superar
    owner y DACL exactos para ser reutilizado.
    """
    target = _validate_scope(path, n1_temp_root=n1_temp_root)
    if getattr(sys, "frozen", False):
        from . import release_gate
        if (release_gate.OWNER_BA_VALIDATION_ID is None
                or PROGRAMDATA_PARENT_VALIDATION_ID is None):
            raise PreparacionOwnerError(
                "Preparación productiva bloqueada: falta validación T1-B o del padre ProgramData.")
        release_gate.require_frozen_production(Path(sys.executable).resolve().parent)
    api = api or Win32SecurityApi()
    with api.effective_token() as token:
        api.owner_assignment_available(token)
        created = api.create_directory_protected(target, sid_operator)
        with api.open_directory(target) as handle:
            if created:
                with api.restore_privilege_temporarily(token):
                    api.set_owner_ba(handle)
            result = api.verify_handle(handle, sid_operator, target)
    return {"path": str(target), "created": created,
            "owner_sid": result.owner_sid,
            "dacl_exact_and_protected": result.dacl_exacta_y_protegida,
            "parent_access_assessed": False,
            "production_prepared": False}


def prepare_installed_data_directory(sid_operator):
    """Punto productivo fijo, bloqueado hasta que release gate cierre T1-B."""
    from . import release_gate
    if (not getattr(sys, "frozen", False)
            or release_gate.OWNER_BA_VALIDATION_ID is None
            or PROGRAMDATA_PARENT_VALIDATION_ID is None):
        raise PreparacionOwnerError("Preparación productiva bloqueada hasta aprobar T1-B.")
    from .rutas import PROGRAM_DATA_DIR
    return _prepare_directory_b(PROGRAM_DATA_DIR, sid_operator)
