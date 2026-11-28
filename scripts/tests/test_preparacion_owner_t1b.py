"""Pruebas T1-B sin llamadas WinAPI que cambien ACL, owner o privilegios."""
from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from desktop.preparacion_owner_ba import (
    ACE_HEADER,
    LUID,
    LUID_AND_ATTRIBUTES,
    PreparacionOwnerError,
    SID_AND_ATTRIBUTES,
    TOKEN_GROUPS,
    TOKEN_PRIVILEGES,
    TOKEN_GROUPS_CLASS,
    TOKEN_ELEVATION,
    TOKEN_PRIVILEGES_CLASS,
    VerificacionDirectorio,
    Win32SecurityApi,
    _prepare_directory_b,
    _restore_privilege_scope,
)
from desktop.release_gate import ReleaseGateError, _reject_reparse_components
from scripts.n1_preparacion_owner_ba import run_n1


class FakeApi:
    def __init__(self, *, created=True, fail_set=False, fail_verify=False,
                 fail_preflight=False, fail_target=False, fail_create=False,
                 fail_delete=False, fail_close=False, kind="directory"):
        self.created = created
        self.fail_set = fail_set
        self.fail_verify = fail_verify
        self.fail_preflight = fail_preflight
        self.fail_target = fail_target
        self.fail_create = fail_create
        self.fail_delete = fail_delete
        self.fail_close = fail_close
        self.kind = kind
        self.calls = []
        self.deleted = []

    @contextmanager
    def effective_token(self):
        self.calls.append("token-open")
        try:
            yield "token"
        finally:
            self.calls.append("token-close")

    def owner_assignment_available(self, token):
        self.calls.append("owner-preflight")
        if self.fail_preflight:
            raise PreparacionOwnerError("sin BA asignable ni SeRestorePrivilege")

    @contextmanager
    def open_parent_chain(self, path):
        self.calls.append(("open-parent", str(path)))
        try:
            yield ("parent-handle", Path(path).name)
        finally:
            self.calls.append("parent-close")

    def create_or_open_child_directory(self, parent_handle, name, sid):
        self.calls.append(("create-or-open", parent_handle, name, sid))
        if self.fail_create:
            raise PreparacionOwnerError("fallo inyectado al crear/abrir el hijo")
        return ("handle", self.kind), self.created

    def verify_handle_target(self, handle, expected_path):
        self.calls.append(("verify-target", handle, str(expected_path)))
        if self.fail_target:
            raise PreparacionOwnerError("fallo inyectado en verificación de identidad")
        if handle[1] != "directory":
            raise PreparacionOwnerError("El objeto abierto no es un directorio.")

    def verify_handle_is_directory(self, handle):
        self.calls.append(("verify-dir", handle))
        if handle[1] != "directory":
            raise PreparacionOwnerError("El objeto abierto no es un directorio.")

    @contextmanager
    def restore_privilege_temporarily(self, token):
        self.calls.append("privilege-enter")
        try:
            yield False
        finally:
            self.calls.append("privilege-restore")

    def set_owner_ba(self, handle):
        self.calls.append(("set-owner", handle))
        if self.fail_set:
            raise PreparacionOwnerError("fallo inyectado en SetSecurityInfo")

    def verify_handle_not_reparse(self, handle):
        self.calls.append(("verify-not-reparse", handle))

    def verify_handle(self, handle, sid, path):
        self.calls.append(("verify", handle, sid, str(path)))
        if self.fail_verify:
            raise PreparacionOwnerError("fallo inyectado en verificación")
        return VerificacionDirectorio("S-1-5-32-544", True)

    def delete_directory_handle(self, handle):
        self.calls.append(("delete", handle))
        if self.fail_delete:
            raise PreparacionOwnerError("fallo inyectado al eliminar por handle")
        self.deleted.append(handle)

    def close_handle(self, handle):
        self.calls.append(("close", handle))
        if self.fail_close:
            raise PreparacionOwnerError("fallo inyectado al cerrar handle")


class FakeN1Handle:
    def __init__(self, path, *, kind="directory", parent=None):
        self.path, self.kind, self.parent = Path(path), kind, parent
        self.closed = False
        self.share_delete = False


class FaithfulN1Api:
    """FS local de prueba: handles fijan directorios; toda creación es relativa."""
    def __init__(self, *, inject_destination_junction=False, replacement_hook=None,
                 fail_delete=False):
        self.root = None
        self.events = []
        self.owner_targets = []
        self.inject_destination_junction = inject_destination_junction
        self.replacement_hook = replacement_hook
        self.fail_delete = fail_delete
        self.external = None
        self.handles = []

    @contextmanager
    def open_directory_chain(self, path):
        path = Path(path)
        _reject_reparse_components(path)
        if not path.is_dir():
            raise PreparacionOwnerError("TEMP no es directorio")
        self.root = path.resolve()
        handle = FakeN1Handle(self.root)
        self.handles.append(handle)
        try:
            yield handle
        finally:
            handle.closed = True

    def _check_parent(self, parent):
        if parent.closed or not parent.path.is_dir():
            raise PreparacionOwnerError("handle padre cerrado o inválido")
        _reject_reparse_components(parent.path)

    def attempt_parent_substitution(self, handle):
        # NT share mode held by this handle denies delete/rename while open.
        if handle.closed or handle.share_delete:
            raise PreparacionOwnerError("modelo: handle no fija antecesor")
        raise PermissionError("modelo: sharing violation por ausencia de FILE_SHARE_DELETE")

    def create_child_directory(self, parent_handle, name, sid_operator=None):
        self._check_parent(parent_handle)
        if self.replacement_hook:
            self.replacement_hook(parent_handle, name)
        target = parent_handle.path / name
        _reject_reparse_components(target)
        try:
            target.mkdir()
        except FileExistsError as exc:
            raise PreparacionOwnerError("FILE_CREATE: nombre ya ocupado") from exc
        self.events.append(("mkdir", target.resolve()))
        handle = FakeN1Handle(target.resolve(), parent=parent_handle)
        self.handles.append(handle)
        return handle, True

    def open_child_directory(self, parent_handle, name):
        self._check_parent(parent_handle)
        target = parent_handle.path / name
        _reject_reparse_components(target)
        if not target.is_dir():
            raise PreparacionOwnerError("STATUS_OBJECT_NAME_NOT_FOUND")
        return FakeN1Handle(target.resolve(), parent=parent_handle)

    def verify_handle_not_reparse(self, handle):
        if handle.closed or not handle.path.is_dir() or handle.path.is_symlink():
            raise PreparacionOwnerError("handle no es directorio real")
        _reject_reparse_components(handle.path)

    def verify_handle_is_directory(self, handle):
        if handle.closed or not handle.path.is_dir():
            raise PreparacionOwnerError("handle no es un directorio")

    def verify_handle_target(self, handle, expected_path=None):
        self.verify_handle_not_reparse(handle)
        self.verify_handle_is_directory(handle)

    @contextmanager
    def effective_token(self):
        yield "simulated-token"

    def owner_assignment_available(self, token):
        return None

    @contextmanager
    def restore_privilege_temporarily(self, token, *, force=False):
        yield False

    def set_owner_ba(self, handle):
        self.verify_handle_not_reparse(handle)
        if not handle.path.resolve().is_relative_to(self.root):
            raise PreparacionOwnerError("owner fuera de TEMP")
        self.owner_targets.append(handle.path.resolve())
        self.events.append(("set-owner", handle.path.resolve()))

    def verify_handle(self, handle, sid_operator, expected_path=None):
        self.verify_handle_target(handle, expected_path)
        if handle.path.name == "preexisting_unrecognized":
            raise PreparacionOwnerError("DACL no conforme")
        return VerificacionDirectorio("S-1-5-32-544", True)

    def delete_directory_handle(self, handle):
        if handle.closed:
            raise PreparacionOwnerError("handle ya cerrado")
        if self.fail_delete:
            raise PreparacionOwnerError("fallo simulado al borrar por handle")
        handle.path.rmdir()
        self.events.append(("delete", handle.path))

    def close_handle(self, handle):
        handle.closed = True

    def _lookup_restore_luid(self):
        return "restore"

    def _privilege_state(self, token, luid):
        return None


class FakePrivilegeApi:
    def __init__(self, *, owner_assignable=False, attributes=0, present=True,
                 fail_enable=False, fail_restore=False):
        self.owner_assignable = owner_assignable
        self.attributes = attributes if present else None
        self.fail_enable = fail_enable
        self.fail_restore = fail_restore
        self.calls = []

    def ba_owner_assignable(self, token):
        self.calls.append("check-ba-owner")
        return self.owner_assignable

    def _lookup_restore_luid(self):
        self.calls.append("lookup-restore")
        return "luid-restore"

    def _privilege_state(self, token, luid):
        self.calls.append(("query-restore", luid))
        return self.attributes

    def _enable_restore_privilege(self, token, luid, old_attributes):
        self.calls.append(("enable-restore", luid, old_attributes))
        if self.fail_enable:
            raise PreparacionOwnerError("ERROR_NOT_ALL_ASSIGNED")
        return (luid, old_attributes)

    def _restore_privilege_state(self, token, previous):
        self.calls.append(("restore", previous))
        if self.fail_restore:
            raise PreparacionOwnerError("restauración fallida")


class PreparacionOwnerT1BTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="inventarios_t1b_unit_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sid = "S-1-5-21-111-222-333-1001"

    def test_x64_structure_layouts(self):
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            self.assertEqual(ctypes.sizeof(SID_AND_ATTRIBUTES), 16)
            self.assertEqual(TOKEN_GROUPS.Groups.offset, 8)
            self.assertEqual(ctypes.sizeof(LUID_AND_ATTRIBUTES), 12)
            self.assertEqual(TOKEN_PRIVILEGES.Privileges.offset, 4)
        self.assertEqual(ctypes.sizeof(ACE_HEADER), 4)

    def _token_buffer_api(self, required_size, returned_size):
        class FakeAdvapi:
            calls = 0

            def GetTokenInformation(inner, token, info_class, buffer, size, returned):
                inner.calls += 1
                out = ctypes.cast(returned, ctypes.POINTER(ctypes.c_uint32))
                if inner.calls == 1:
                    out[0] = required_size
                    return 0
                out[0] = returned_size
                return 1

        api = object.__new__(Win32SecurityApi)
        api.advapi32 = FakeAdvapi()
        return api

    def test_token_buffer_rejects_zero_or_short_required_size(self):
        minimum = TOKEN_GROUPS.Groups.offset
        for size in (0, minimum - 1):
            with self.subTest(size=size):
                api = self._token_buffer_api(size, size)
                with patch.object(ctypes, "set_last_error"):
                    with patch.object(ctypes, "get_last_error", return_value=122):
                        with self.assertRaisesRegex(PreparacionOwnerError, "Invalid token buffer size"):
                            api._token_buffer("token", TOKEN_GROUPS_CLASS)

    def test_token_buffer_rejects_returned_size_above_allocation(self):
        minimum = TOKEN_GROUPS.Groups.offset
        api = self._token_buffer_api(minimum, minimum + 1)
        with patch.object(ctypes, "set_last_error"):
            with patch.object(ctypes, "get_last_error", return_value=122):
                with self.assertRaisesRegex(PreparacionOwnerError, "inválido"):
                    api._token_buffer("token", TOKEN_GROUPS_CLASS)

    def test_token_buffer_rejects_returned_size_below_minimum(self):
        minimum = TOKEN_GROUPS.Groups.offset
        api = self._token_buffer_api(minimum, minimum - 1)
        with patch.object(ctypes, "set_last_error"):
            with patch.object(ctypes, "get_last_error", return_value=122):
                with self.assertRaisesRegex(PreparacionOwnerError, "inválido"):
                    api._token_buffer("token", TOKEN_GROUPS_CLASS)

    def test_token_buffer_accepts_valid_size(self):
        minimum = TOKEN_GROUPS.Groups.offset
        api = self._token_buffer_api(minimum, minimum)
        with patch.object(ctypes, "set_last_error"):
            with patch.object(ctypes, "get_last_error", return_value=122):
                buffer, length = api._token_buffer("token", TOKEN_GROUPS_CLASS)
        self.assertEqual(length, minimum)
        self.assertEqual(len(buffer), minimum)

    def test_effective_token_requires_exact_elevation_size(self):
        class FakeKernel:
            def CloseHandle(self, token):
                return 1

        class FakeAdvapi:
            def __init__(self, size):
                self.size = size

            def GetTokenInformation(self, token, info_class, elevation, capacity, returned):
                ctypes.cast(elevation, ctypes.POINTER(TOKEN_ELEVATION))[0].TokenIsElevated = 1
                ctypes.cast(returned, ctypes.POINTER(ctypes.c_uint32))[0] = self.size
                return 1

        for size in (0, ctypes.sizeof(TOKEN_ELEVATION) - 1,
                     ctypes.sizeof(TOKEN_ELEVATION) + 1):
            api = object.__new__(Win32SecurityApi)
            api._token_handle = lambda: (ctypes.c_void_p(1), True)
            api.kernel32 = FakeKernel()
            api.advapi32 = FakeAdvapi(size)
            api.ba_enabled = lambda token: self.fail("BA check must not run for invalid size")
            with self.subTest(size=size):
                with self.assertRaisesRegex(PreparacionOwnerError, "TOKEN_ELEVATION returned invalid size"):
                    with api.effective_token():
                        self.fail("invalid elevation size accepted")

        api.advapi32 = FakeAdvapi(ctypes.sizeof(TOKEN_ELEVATION))
        api.ba_enabled = lambda token: True
        with api.effective_token() as token:
            self.assertEqual(token.value, 1)

    def _group_parser_api(self, count, *, include_entry):
        offset = TOKEN_GROUPS.Groups.offset
        item_size = ctypes.sizeof(SID_AND_ATTRIBUTES)
        length = offset + item_size if include_entry else offset
        buffer = ctypes.create_string_buffer(length)
        ctypes.c_uint32.from_buffer(buffer).value = count
        if include_entry:
            entry = SID_AND_ATTRIBUTES.from_buffer(buffer, offset)
            entry.Sid = 0x1234
            entry.Attributes = 0xA5

        class FakeAdvapi:
            def EqualSid(self, sid, expected):
                return sid == expected.value

        api = object.__new__(Win32SecurityApi)
        api._token_buffer = lambda token, info_class: (buffer, length)
        api._sid_pointer = lambda sid: ctypes.c_void_p(0x1234)
        api.advapi32 = FakeAdvapi()
        api.kernel32 = type("FakeKernel", (), {"LocalFree": lambda self, sid: None})()
        return api

    def test_ba_group_parser_rejects_count_exceeding_buffer(self):
        api = self._group_parser_api(1, include_entry=False)
        with self.assertRaisesRegex(PreparacionOwnerError, "TOKEN_GROUPS truncado"):
            api._ba_group_attributes("token")

    def test_ba_group_parser_processes_complete_entry(self):
        api = self._group_parser_api(1, include_entry=True)
        self.assertEqual(api._ba_group_attributes("token"), 0xA5)

    def test_ba_group_parser_zero_count_returns_none(self):
        api = self._group_parser_api(0, include_entry=False)
        self.assertIsNone(api._ba_group_attributes("token"))

    def _privilege_parser_api(self, count, *, include_entry):
        offset = TOKEN_PRIVILEGES.Privileges.offset
        item_size = ctypes.sizeof(LUID_AND_ATTRIBUTES)
        length = offset + item_size if include_entry else offset
        buffer = ctypes.create_string_buffer(length)
        ctypes.c_uint32.from_buffer(buffer).value = count
        wanted = LUID()
        wanted.LowPart = 0x12345678
        wanted.HighPart = -7
        if include_entry:
            entry = LUID_AND_ATTRIBUTES.from_buffer(buffer, offset)
            entry.Luid = wanted
            entry.Attributes = 0x2
        api = object.__new__(Win32SecurityApi)
        api._token_buffer = lambda token, info_class: (buffer, length)
        return api, wanted

    def test_privilege_parser_rejects_count_exceeding_buffer(self):
        api, wanted = self._privilege_parser_api(1, include_entry=False)
        with self.assertRaisesRegex(PreparacionOwnerError, "TOKEN_PRIVILEGES truncado"):
            api._privilege_state("token", wanted)

    def test_privilege_parser_processes_complete_entry(self):
        api, wanted = self._privilege_parser_api(1, include_entry=True)
        self.assertEqual(api._privilege_state("token", wanted), 0x2)

    def test_privilege_parser_zero_count_returns_none(self):
        api, wanted = self._privilege_parser_api(0, include_entry=False)
        self.assertIsNone(api._privilege_state("token", wanted))

    def test_common_flow_sets_owner_then_verifies_and_never_marks_production(self):
        api = FakeApi()
        result = _prepare_directory_b(
            self.root / "datos", self.sid, api=api,
            n1_temp_root=Path(tempfile.gettempdir()))
        self.assertEqual(result["owner_sid"], "S-1-5-32-544")
        self.assertTrue(result["dacl_exact_and_protected"])
        self.assertFalse(result["production_prepared"])
        self.assertFalse(result["parent_access_assessed"])
        self.assertTrue(result["created"])
        self.assertLess(api.calls.index("owner-preflight"),
                        next(i for i, call in enumerate(api.calls)
                             if isinstance(call, tuple) and call[0] == "create-or-open"))
        self.assertLess(
            next(i for i, call in enumerate(api.calls)
                 if isinstance(call, tuple) and call[0] == "verify-target"),
            api.calls.index(("set-owner", ("handle", "directory"))))
        self.assertLess(api.calls.index(("set-owner", ("handle", "directory"))),
                        next(i for i, call in enumerate(api.calls)
                             if isinstance(call, tuple) and call[0] == "verify"))
        self.assertFalse(any(isinstance(call, tuple) and call[0] in {"create", "open"}
                             for call in api.calls))
        self.assertTrue(any(isinstance(call, tuple) and call[0] == "close"
                            for call in api.calls))
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "delete"
                             for call in api.calls))

    def test_core_uses_parent_handle_and_relative_create(self):
        api = FakeApi()
        _prepare_directory_b(self.root / "datos", self.sid, api=api,
                             n1_temp_root=Path(tempfile.gettempdir()))
        self.assertIn(("open-parent", str(self.root / "datos")), api.calls)
        create_call = next(call for call in api.calls
                           if isinstance(call, tuple) and call[0] == "create-or-open")
        self.assertEqual(create_call[1], "parent-handle")
        self.assertEqual(create_call[2], "datos")
        self.assertEqual(create_call[3], self.sid)
        self.assertFalse(any(isinstance(call, tuple) and call[0] in {"create", "open"}
                             for call in api.calls))

    def test_set_owner_failure_closes_handle_and_token_without_verifying(self):
        api = FakeApi(fail_set=True)
        with self.assertRaisesRegex(PreparacionOwnerError, "SetSecurityInfo"):
            _prepare_directory_b(self.root / "datos", self.sid, api=api,
                                 n1_temp_root=Path(tempfile.gettempdir()))
        self.assertTrue(any(isinstance(call, tuple) and call[0] == "close"
                            for call in api.calls))
        self.assertIn("token-close", api.calls)
        self.assertIn("privilege-restore", api.calls)
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "verify" for call in api.calls))
        self.assertTrue(any(isinstance(call, tuple) and call[0] == "delete"
                            for call in api.calls))

    def test_owner_preflight_failure_happens_before_directory_creation(self):
        api = FakeApi(fail_preflight=True)
        with self.assertRaisesRegex(PreparacionOwnerError, "sin BA asignable"):
            _prepare_directory_b(self.root / "datos", self.sid, api=api,
                                 n1_temp_root=Path(tempfile.gettempdir()))
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "create-or-open"
                             for call in api.calls))

    def test_existing_directory_is_verified_but_never_adopted(self):
        api = FakeApi(created=False, fail_verify=True)
        with self.assertRaisesRegex(PreparacionOwnerError, "verificación"):
            _prepare_directory_b(self.root / "datos", self.sid, api=api,
                                 n1_temp_root=Path(tempfile.gettempdir()))
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "set-owner" for call in api.calls))
        self.assertFalse(any(call == "privilege-enter" for call in api.calls))
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "delete"
                             for call in api.calls))

    def test_target_verification_failure_happens_before_owner_and_cleans_created(self):
        api = FakeApi(fail_target=True)
        with self.assertRaisesRegex(PreparacionOwnerError, "identidad"):
            _prepare_directory_b(self.root / "datos", self.sid, api=api,
                                 n1_temp_root=Path(tempfile.gettempdir()))
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "set-owner"
                             for call in api.calls))
        self.assertTrue(any(isinstance(call, tuple) and call[0] == "delete"
                            for call in api.calls))
        self.assertTrue(any(isinstance(call, tuple) and call[0] == "close"
                            for call in api.calls))

    def test_file_like_object_is_rejected_before_owner(self):
        api = FakeApi(kind="file")
        with self.assertRaisesRegex(PreparacionOwnerError, "no es un directorio"):
            _prepare_directory_b(self.root / "datos", self.sid, api=api,
                                 n1_temp_root=Path(tempfile.gettempdir()))
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "set-owner"
                             for call in api.calls))
        self.assertTrue(any(isinstance(call, tuple) and call[0] == "delete"
                            for call in api.calls))

    def test_create_failure_does_not_delete_or_verify(self):
        api = FakeApi(fail_create=True)
        with self.assertRaisesRegex(PreparacionOwnerError, "crear/abrir"):
            _prepare_directory_b(self.root / "datos", self.sid, api=api,
                                 n1_temp_root=Path(tempfile.gettempdir()))
        self.assertFalse(any(isinstance(call, tuple) and call[0] in {"delete", "verify", "set-owner"}
                             for call in api.calls))

    def test_cleanup_residue_is_reported_when_handle_delete_fails(self):
        api = FakeApi(fail_set=True, fail_delete=True)
        with self.assertRaisesRegex(PreparacionOwnerError, "posible residuo"):
            _prepare_directory_b(self.root / "datos", self.sid, api=api,
                                 n1_temp_root=Path(tempfile.gettempdir()))
        self.assertTrue(any(isinstance(call, tuple) and call[0] == "close"
                            for call in api.calls))
        self.assertIn("token-close", api.calls)

    def test_source_core_rejects_non_temp_and_arbitrary_temp_root(self):
        outside = RAIZ / "datos-temporales-ajenos"
        with self.assertRaises(PreparacionOwnerError):
            _prepare_directory_b(outside, self.sid, api=FakeApi(),
                                 n1_temp_root=Path(tempfile.gettempdir()))
        with self.assertRaises(PreparacionOwnerError):
            _prepare_directory_b(self.root / "datos", self.sid, api=FakeApi(),
                                 n1_temp_root=self.root)

    def test_reparse_component_is_rejected_on_reachable_path(self):
        link = self.root / "reparse"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ReleaseGateError):
            _reject_reparse_components(link / "missing" / "child")

    def test_dotdot_is_rejected_as_ambiguous_before_filesystem_walk(self):
        candidate = self.root / "missing" / ".." / "ordinary"
        with self.assertRaisesRegex(ReleaseGateError, "'..'"):
            _reject_reparse_components(candidate)

    def test_run_n1_missing_temp_component_fails_without_writes(self):
        api = FaithfulN1Api()
        report = run_n1(self.sid, api_factory=lambda: api,
                        temp_root_override=self.root / "missing" / "child")
        self.assertIn("fatal_error", report)
        self.assertEqual(api.events, [])
        self.assertEqual(api.owner_targets, [])

    def test_run_n1_coordinated_ancestor_substitution_is_denied_by_handle_model(self):
        api = FaithfulN1Api()

        def substitute(parent, name):
            api.attempt_parent_substitution(parent)
        api.replacement_hook = substitute
        report = run_n1(self.sid, api_factory=lambda: api, temp_root_override=self.root)
        self.assertIn("fatal_error", report)
        self.assertEqual(api.events, [])
        self.assertEqual(api.owner_targets, [])

    def test_run_n1_reports_cleanup_residue_and_closes_every_handle(self):
        api = FaithfulN1Api(fail_delete=True)
        report = run_n1(self.sid, api_factory=lambda: api, temp_root_override=self.root)
        self.assertTrue(report.get("cleanup_residue"))
        self.assertTrue(api.handles)
        self.assertTrue(all(handle.closed for handle in api.handles))

    def test_run_n1_with_handle_model_confines_all_writes_and_owner_calls(self):
        api = FaithfulN1Api()
        report = run_n1(self.sid, api_factory=lambda: api, temp_root_override=self.root)
        self.assertNotIn("fatal_error", report)
        self.assertNotIn("cleanup_residue", report)
        self.assertTrue(api.events)
        self.assertTrue(all(path.resolve().is_relative_to(self.root.resolve())
                            for _, path in api.events))
        self.assertTrue(all(path.resolve().is_relative_to(self.root.resolve())
                            for path in api.owner_targets))
        self.assertEqual(len(api.owner_targets), 1)

    @unittest.skipUnless(os.name == "nt", "junctions reales requieren Windows")
    def test_run_n1_rejects_temp_and_intermediate_junctions_before_api(self):
        external = self.root / "outside"
        external.mkdir()
        for name, supplied in (("temp_link", self.root / "temp_link"),
                               ("middle_link", self.root / "middle_link" / "descendant")):
            link = supplied if name == "temp_link" else self.root / "middle_link"
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(external)],
                                    capture_output=True, text=True)
            if result.returncode:
                self.skipTest(f"mklink /J no disponible: {result.stderr or result.stdout}")
            self.addCleanup(lambda p=link: subprocess.run(["cmd", "/c", "rmdir", str(p)],
                                                          capture_output=True))
            with self.subTest(path=supplied), self.assertRaises(ReleaseGateError):
                run_n1(self.sid, api_factory=lambda: self.fail("API no debe abrirse"),
                       temp_root_override=supplied)
            self.assertEqual(list(external.iterdir()), [])

    @unittest.skipUnless(os.name == "nt", "junctions reales requieren Windows")
    def test_run_n1_destination_junction_has_no_external_write_or_owner_change(self):
        external = self.root / "outside_destination"
        external.mkdir()
        junctions = []
        api = FaithfulN1Api()

        def inject(parent, name):
            if name == "success":
                junction = parent.path / name
                result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(external)],
                                        capture_output=True, text=True)
                if result.returncode:
                    raise AssertionError(result.stderr or result.stdout)
                junctions.append(junction)
        api.replacement_hook = inject
        self.addCleanup(lambda: [subprocess.run(["cmd", "/c", "rmdir", str(p)],
                                                capture_output=True) for p in junctions])
        report = run_n1(self.sid, api_factory=lambda: api, temp_root_override=self.root)
        self.assertIn("fatal_error", report)
        self.assertEqual(list(external.iterdir()), [])
        self.assertEqual(api.owner_targets, [])
        self.assertTrue(all(path.resolve().is_relative_to(self.root.resolve())
                            for event, path in api.events))

    @unittest.skipUnless(os.name == "nt", "ABI NT y sharing modes requieren Windows x64")
    def test_native_abi_layout_and_handle_relative_create_block_rename(self):
        from desktop.preparacion_owner_ba import (
            FILE_DISPOSITION_INFO, IO_STATUS_BLOCK, OBJECT_ATTRIBUTES, UNICODE_STRING,
            Win32SecurityApi,
        )
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            self.skipTest("Windows x64 requerido")
        self.assertEqual((ctypes.sizeof(UNICODE_STRING), UNICODE_STRING.Length.offset,
                          UNICODE_STRING.MaximumLength.offset, UNICODE_STRING.Buffer.offset),
                         (16, 0, 2, 8))
        self.assertEqual((ctypes.sizeof(OBJECT_ATTRIBUTES), OBJECT_ATTRIBUTES.Length.offset,
                          OBJECT_ATTRIBUTES.RootDirectory.offset, OBJECT_ATTRIBUTES.ObjectName.offset,
                          OBJECT_ATTRIBUTES.Attributes.offset, OBJECT_ATTRIBUTES.SecurityDescriptor.offset,
                          OBJECT_ATTRIBUTES.SecurityQualityOfService.offset),
                         (48, 0, 8, 16, 24, 32, 40))
        self.assertEqual((ctypes.sizeof(IO_STATUS_BLOCK), IO_STATUS_BLOCK.Status.offset,
                          IO_STATUS_BLOCK.Information.offset), (16, 0, 8))
        self.assertEqual(ctypes.sizeof(FILE_DISPOSITION_INFO), 1)
        api = Win32SecurityApi()
        self.assertEqual(len(api.ntdll.NtCreateFile.argtypes), 11)
        self.assertEqual(api.ntdll.NtCreateFile.restype, ctypes.c_long)
        # Test fixture is a fresh TEMP directory created by TemporaryDirectory.
        # Open that known test root directly; this avoids requiring the sandbox
        # identity to enumerate C:\Users\Jose while testing relative NtCreateFile.
        _reject_reparse_components(self.root)
        open_probe = self.root / "native_open_probe"
        open_probe.mkdir()
        reparse_target = self.root / "native_reparse_target"
        reparse_target.mkdir()
        reparse_link = self.root / "native_reparse_link"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(reparse_link),
                                 str(reparse_target)], capture_output=True, text=True)
        if result.returncode:
            self.skipTest(f"mklink /J no disponible: {result.stderr or result.stdout}")
        self.addCleanup(lambda: os.rmdir(reparse_link) if reparse_link.exists() else None)
        native_symlink = self.root / "native_symlink"
        native_symlink.symlink_to(reparse_target, target_is_directory=True)
        self.addCleanup(lambda: native_symlink.unlink(missing_ok=True))
        root_handle = api.kernel32.CreateFileW(
            str(self.root), 0xA5, 0x3, None, 3,
            0x02000000 | 0x00200000, None)
        self.assertNotIn(root_handle, (None, 0, ctypes.c_void_p(-1).value))
        child = reopened = leaf = None
        try:
            api.verify_handle_not_reparse(root_handle)
            reopened = api.open_child_directory(root_handle, "native_open_probe")
            self.assertIsNotNone(reopened)
            leaf, leaf_created = api.create_child_directory(reopened, "native_relative_leaf")
            self.assertTrue(leaf_created)
            with self.assertRaises(OSError):
                os.rename(open_probe, self.root / "native_open_probe_renamed")
            with self.assertRaises(OSError):
                os.rmdir(open_probe)
            api.delete_directory_handle(leaf)
            api.close_handle(leaf)
            leaf = None
            api.delete_directory_handle(reopened)
            api.close_handle(reopened)
            reopened = None
            with self.assertRaisesRegex(PreparacionOwnerError, "reparse point"):
                api.open_child_directory(root_handle, "native_reparse_link")
            with self.assertRaisesRegex(PreparacionOwnerError, "reparse point"):
                api.open_child_directory(root_handle, "native_symlink")
            with patch.object(api, "verify_handle_not_reparse",
                              side_effect=PreparacionOwnerError("fallo de verificación inyectado")):
                with self.assertRaisesRegex(PreparacionOwnerError, "fallo de verificación"):
                    api.create_child_directory(root_handle, "native_partial_cleanup")
            self.assertFalse((self.root / "native_partial_cleanup").exists())
            child, created = api.create_child_directory(root_handle, "native_handle_probe")
            self.assertTrue(created)
            with self.assertRaises(PreparacionOwnerError):
                api.create_child_directory(root_handle, "native_handle_probe")
            api.delete_directory_handle(child)
            api.close_handle(child)
            child = None
        finally:
            if leaf:
                try:
                    api.delete_directory_handle(leaf)
                finally:
                    api.close_handle(leaf)
            if reopened:
                api.close_handle(reopened)
            if child:
                try:
                    api.delete_directory_handle(child)
                finally:
                    api.close_handle(child)
            api.close_handle(root_handle)
        self.assertFalse((self.root / "native_handle_probe").exists())

    @unittest.skipUnless(os.name == "nt", "creación relativa nativa requiere Windows")
    def test_native_open_parent_chain_creates_and_reopens_relative_child(self):
        api = Win32SecurityApi()
        parent = self.root / "native_core_parent"
        parent.mkdir()
        target = parent / "native_core_child"
        handle = None
        reopened = None
        try:
            with api.open_parent_chain(target) as (parent_handle, name):
                handle, created = api.create_or_open_child_directory(parent_handle, name)
                self.assertTrue(created)
                api.verify_handle_target(handle, target)
                api.close_handle(handle)
                handle = None
                reopened, created_again = api.create_or_open_child_directory(parent_handle, name)
                self.assertFalse(created_again)
                api.verify_handle_target(reopened, target)
        finally:
            for current in (handle, reopened):
                if current is not None:
                    try:
                        api.delete_directory_handle(current)
                    finally:
                        api.close_handle(current)
        self.assertFalse(target.exists())

    @unittest.skipUnless(os.name == "nt", "junctions reales requieren Windows")
    def test_native_open_parent_chain_rejects_junction_in_parent(self):
        api = Win32SecurityApi()
        external = self.root / "native_parent_external"
        external.mkdir()
        junction = self.root / "native_parent_junction"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(external)],
                                capture_output=True, text=True)
        if result.returncode:
            self.skipTest(f"mklink /J no disponible: {result.stderr or result.stdout}")
        self.addCleanup(lambda: subprocess.run(["cmd", "/c", "rmdir", str(junction)],
                                               capture_output=True))
        with self.assertRaisesRegex(PreparacionOwnerError, "reparse point"):
            with api.open_parent_chain(junction / "child"):
                self.fail("no debía abrir un padre con junction")

    @unittest.skipUnless(os.name == "nt", "atributos nativos requieren Windows")
    def test_native_file_is_rejected_as_directory_by_handle(self):
        api = Win32SecurityApi()
        file_path = self.root / "native_not_a_directory"
        file_path.write_text("no es un directorio", encoding="utf-8")
        handle = api.kernel32.CreateFileW(
            str(file_path), 0x80, 0x3, None, 3, 0, None)
        self.assertNotIn(handle, (None, 0, ctypes.c_void_p(-1).value))
        try:
            with self.assertRaisesRegex(PreparacionOwnerError, "no es un directorio"):
                api.verify_handle_is_directory(handle)
        finally:
            api.close_handle(handle)
        with api.open_parent_chain(file_path) as (parent_handle, name):
            with self.assertRaises(PreparacionOwnerError):
                api.create_or_open_child_directory(parent_handle, name)

    @unittest.skipUnless(os.name == "nt", "DACL nativa requiere Windows")
    def test_native_verify_handle_rejects_non_t1_dacl(self):
        api = Win32SecurityApi()
        target = self.root / "native_wrong_dacl"
        target.mkdir()
        with api.open_parent_chain(target) as (parent_handle, name):
            handle = api.open_child_directory(parent_handle, name)
            try:
                with self.assertRaisesRegex(PreparacionOwnerError, "DACL"):
                    api.verify_handle(handle, self.sid)
            finally:
                api.close_handle(handle)

    @unittest.skipUnless(os.name == "nt", "owner nativo requiere Windows")
    def test_native_verify_handle_rejects_non_ba_owner(self):
        from desktop.seguridad import obtener_sid_actual
        api = Win32SecurityApi()
        sid_operator = obtener_sid_actual()
        if sid_operator in {"S-1-5-18", "S-1-5-32-544"}:
            self.skipTest("El SID actual es SYSTEM o BA; no se usa como operador de prueba.")
        target = self.root / "native_wrong_owner"
        with api.open_parent_chain(target) as (parent_handle, name):
            handle, created = api.create_or_open_child_directory(
                parent_handle, name, sid_operator)
            self.assertTrue(created)
            try:
                with self.assertRaisesRegex(PreparacionOwnerError, "owner"):
                    api.verify_handle(handle, sid_operator)
            finally:
                api.delete_directory_handle(handle)
                api.close_handle(handle)

    @unittest.skipUnless(os.name == "nt", "núcleo nativo requiere Windows")
    def test_native_prepare_directory_b_uses_relative_core_or_skips_without_elevation(self):
        from desktop.seguridad import obtener_sid_actual
        api = Win32SecurityApi()
        try:
            with api.effective_token() as token:
                api.owner_assignment_available(token)
        except PreparacionOwnerError as exc:
            self.skipTest(f"token de prueba no elevado/apto para preparar owner: {exc}")
        sid_operator = obtener_sid_actual()
        if sid_operator in {"S-1-5-18", "S-1-5-32-544"}:
            self.skipTest("El SID actual es SYSTEM o BA; no se usa como operador de prueba.")
        target = self.root / "native_prepare_core"
        self.addCleanup(lambda: os.rmdir(target) if target.exists() else None)

        def cleanup_relative():
            try:
                with api.open_parent_chain(target) as (parent_handle, name):
                    handle = api.open_child_directory(parent_handle, name)
                    try:
                        api.delete_directory_handle(handle)
                    finally:
                        api.close_handle(handle)
            except Exception:
                pass
        self.addCleanup(cleanup_relative)
        result = _prepare_directory_b(
            target, sid_operator, api=api, n1_temp_root=Path(tempfile.gettempdir()))
        self.assertTrue(result["created"])
        self.assertEqual(result["owner_sid"], "S-1-5-32-544")
        self.assertTrue(result["dacl_exact_and_protected"])
        again = _prepare_directory_b(
            target, sid_operator, api=api, n1_temp_root=Path(tempfile.gettempdir()))
        self.assertFalse(again["created"])
        self.assertEqual(again["owner_sid"], "S-1-5-32-544")
        self.assertTrue(again["dacl_exact_and_protected"])

    @unittest.skipUnless(os.name == "nt", "cadena nativa requiere Windows")
    def test_native_full_temp_chain_is_exercised_or_explicitly_blocked_by_token(self):
        api = Win32SecurityApi()
        try:
            with api.open_directory_chain(Path(tempfile.gettempdir())) as temp_handle:
                api.verify_handle_not_reparse(temp_handle)
        except PreparacionOwnerError as exc:
            # No se cambia el access mask ni se toma esto como aprobación.
            if "NTSTATUS 0xc0000022" in str(exc):
                self.skipTest(f"cadena TEMP denegada por el token en este entorno: {exc}")
            raise

    @unittest.skipUnless(os.name == "nt", "owner WinAPI requiere Windows")
    def test_native_owner_set_and_readback_only_on_temporary_probe(self):
        api = Win32SecurityApi()
        try:
            with api.effective_token() as token:
                api.owner_assignment_available(token)
        except PreparacionOwnerError as exc:
            self.skipTest(f"token de prueba no elevado/apto para asignar owner: {exc}")
        root_handle = api.kernel32.CreateFileW(
            str(self.root), 0xA5, 0x3, None, 3, 0x02000000 | 0x00200000, None)
        self.assertNotIn(root_handle, (None, 0, ctypes.c_void_p(-1).value))
        handle = None
        try:
            api.verify_handle_not_reparse(root_handle)
            handle, created = api.create_child_directory(root_handle, "native_owner_probe")
            self.assertTrue(created)
            with api.effective_token() as token:
                with api.restore_privilege_temporarily(token):
                    api.set_owner_ba(handle)
            owner, dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
            status = api.advapi32.GetSecurityInfo(
                handle, 1, 0x1, ctypes.byref(owner), None, None, None,
                ctypes.byref(descriptor))
            self.assertEqual(status, 0)
            ba = api._sid_pointer("S-1-5-32-544")
            try:
                self.assertTrue(api.advapi32.EqualSid(owner, ba))
            finally:
                api.kernel32.LocalFree(ba)
                if descriptor:
                    api.kernel32.LocalFree(descriptor)
            api.delete_directory_handle(handle)
            api.close_handle(handle)
            handle = None
        finally:
            if handle:
                try:
                    api.delete_directory_handle(handle)
                finally:
                    api.close_handle(handle)
            api.close_handle(root_handle)

    @unittest.skipUnless(os.name == "nt", "junctions reales requieren Windows")
    def test_real_junction_is_rejected_in_temp_intermediate_and_destination(self):
        target = self.root / "junction_target"
        target.mkdir()
        junction = self.root / "junction"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)],
                                capture_output=True, text=True)
        if result.returncode:
            self.skipTest(f"No se pudo crear junction local: {result.stderr or result.stdout}")
        self.addCleanup(lambda: subprocess.run(["cmd", "/c", "rmdir", str(junction)],
                                               capture_output=True))
        for candidate in (junction, junction / "middle" / "missing",
                          self.root / "destination_link"):
            if candidate.name == "destination_link":
                candidate.symlink_to(target, target_is_directory=True)
            with self.subTest(candidate=candidate), self.assertRaises(ReleaseGateError):
                _reject_reparse_components(candidate)

    def test_restore_privilege_is_scoped_and_restored_after_exception(self):
        api = FakePrivilegeApi()
        with self.assertRaisesRegex(RuntimeError, "failure inside"):
            with _restore_privilege_scope(api, "token") as enabled:
                self.assertTrue(enabled)
                raise RuntimeError("failure inside")
        self.assertIn(("restore", ("luid-restore", 0)), api.calls)
        self.assertEqual(api.calls[-1], ("query-restore", "luid-restore"))

    def test_restore_privilege_absent_or_not_assigned_aborts(self):
        absent = FakePrivilegeApi(present=False)
        with self.assertRaisesRegex(PreparacionOwnerError, "no contiene"):
            with _restore_privilege_scope(absent, "token"):
                self.fail("no debía continuar")
        not_assigned = FakePrivilegeApi(fail_enable=True)
        with self.assertRaisesRegex(PreparacionOwnerError, "ERROR_NOT_ALL_ASSIGNED"):
            with _restore_privilege_scope(not_assigned, "token"):
                self.fail("no debía continuar")

    def test_owner_assignable_skips_restore_and_preenabled_state_is_preserved(self):
        owner_ok = FakePrivilegeApi(owner_assignable=True)
        with _restore_privilege_scope(owner_ok, "token") as enabled:
            self.assertFalse(enabled)
        self.assertNotIn("lookup-restore", owner_ok.calls)

        already_enabled = FakePrivilegeApi(attributes=0x2)
        with _restore_privilege_scope(already_enabled, "token") as enabled:
            self.assertTrue(enabled)
        self.assertFalse(any(call[0] == "enable-restore" for call in already_enabled.calls
                             if isinstance(call, tuple)))
        self.assertFalse(any(call[0] == "restore" for call in already_enabled.calls
                             if isinstance(call, tuple)))

    def test_restore_failure_propagates_and_prevents_success(self):
        api = FakePrivilegeApi(fail_restore=True)
        with self.assertRaisesRegex(PreparacionOwnerError, "restauración fallida"):
            with _restore_privilege_scope(api, "token"):
                pass

    def test_n1_harness_is_outside_pyinstaller_collection(self):
        spec = (RAIZ / "desktop/sistema.spec").read_text(encoding="utf-8")
        launcher = (RAIZ / "desktop/launcher.py").read_text(encoding="utf-8")
        self.assertIn("collect_submodules('desktop')", spec)
        self.assertNotIn("collect_submodules('scripts')", spec)
        self.assertNotIn("n1_preparacion_owner_ba", launcher)


if __name__ == "__main__":
    unittest.main()
