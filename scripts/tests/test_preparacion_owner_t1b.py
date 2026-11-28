"""Pruebas T1-B sin llamadas WinAPI que cambien ACL, owner o privilegios."""
from contextlib import contextmanager
import ctypes
from pathlib import Path
import sys
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


class FakeApi:
    def __init__(self, *, created=True, fail_set=False, fail_verify=False, fail_preflight=False):
        self.created = created
        self.fail_set = fail_set
        self.fail_verify = fail_verify
        self.fail_preflight = fail_preflight
        self.calls = []

    @contextmanager
    def effective_token(self):
        self.calls.append("token-open")
        try:
            yield "token"
        finally:
            self.calls.append("token-close")

    def create_directory_protected(self, path, sid):
        self.calls.append(("create", str(path), sid))
        return self.created

    def owner_assignment_available(self, token):
        self.calls.append("owner-preflight")
        if self.fail_preflight:
            raise PreparacionOwnerError("sin BA asignable ni SeRestorePrivilege")

    @contextmanager
    def open_directory(self, path):
        self.calls.append(("open", str(path)))
        try:
            yield "handle"
        finally:
            self.calls.append("handle-close")

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

    def verify_handle(self, handle, sid, path):
        self.calls.append(("verify", handle, sid, str(path)))
        if self.fail_verify:
            raise PreparacionOwnerError("fallo inyectado en verificación")
        return VerificacionDirectorio("S-1-5-32-544", True)


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
        self.assertLess(api.calls.index("owner-preflight"),
                        next(i for i, call in enumerate(api.calls)
                             if isinstance(call, tuple) and call[0] == "create"))
        self.assertLess(api.calls.index(("set-owner", "handle")),
                        next(i for i, call in enumerate(api.calls) if isinstance(call, tuple) and call[0] == "verify"))

    def test_set_owner_failure_closes_handle_and_token_without_verifying(self):
        api = FakeApi(fail_set=True)
        with self.assertRaisesRegex(PreparacionOwnerError, "SetSecurityInfo"):
            _prepare_directory_b(self.root / "datos", self.sid, api=api,
                                 n1_temp_root=Path(tempfile.gettempdir()))
        self.assertIn("handle-close", api.calls)
        self.assertIn("token-close", api.calls)
        self.assertIn("privilege-restore", api.calls)
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "verify" for call in api.calls))

    def test_owner_preflight_failure_happens_before_directory_creation(self):
        api = FakeApi(fail_preflight=True)
        with self.assertRaisesRegex(PreparacionOwnerError, "sin BA asignable"):
            _prepare_directory_b(self.root / "datos", self.sid, api=api,
                                 n1_temp_root=Path(tempfile.gettempdir()))
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "create" for call in api.calls))

    def test_existing_directory_is_verified_but_never_adopted(self):
        api = FakeApi(created=False, fail_verify=True)
        with self.assertRaisesRegex(PreparacionOwnerError, "verificación"):
            _prepare_directory_b(self.root / "datos", self.sid, api=api,
                                 n1_temp_root=Path(tempfile.gettempdir()))
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "set-owner" for call in api.calls))
        self.assertFalse(any(call == "privilege-enter" for call in api.calls))

    def test_source_core_rejects_non_temp_and_arbitrary_temp_root(self):
        outside = RAIZ / "datos-temporales-ajenos"
        with self.assertRaises(PreparacionOwnerError):
            _prepare_directory_b(outside, self.sid, api=FakeApi(),
                                 n1_temp_root=Path(tempfile.gettempdir()))
        with self.assertRaises(PreparacionOwnerError):
            _prepare_directory_b(self.root / "datos", self.sid, api=FakeApi(),
                                 n1_temp_root=self.root)

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
