"""Structural release-gate tests; no Windows ACLs or production keys are used."""
from pathlib import Path
import os
import stat
import subprocess
import sys
import tempfile
import base64
from types import SimpleNamespace
import unittest
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from desktop import release_gate as gate
from desktop import rutas
from scripts import autorizar_release as release_signer


class ReleaseGateT1ATests(unittest.TestCase):
    def test_signature_base64url_must_be_canonical(self):
        signature = bytes(64)
        encoded = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        self.assertEqual(gate._decode_ed25519_signature(encoded), signature)
        # The final character's two low pad bits are ignored by permissive
        # decoders. Changing them must not create a second accepted spelling.
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        alternate = encoded[:-1] + alphabet[alphabet.index(encoded[-1]) + 1]
        with self.assertRaisesRegex(ValueError, "no canónica"):
            gate._decode_ed25519_signature(alternate)

    def test_authorization_timestamps_require_canonical_utc_seconds(self):
        parsed = gate._parse_utc_timestamp("2030-01-02T03:04:05Z", "issued_at")
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)
        for value in (
            "2030-01-02T03:04:05+00:00",
            "2030-01-02T03:04:05.000Z",
            "2030-01-02T03:04:05",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    gate._parse_utc_timestamp(value, "issued_at")

    def test_rfc8785_reference_string_and_literal_vector(self):
        # RFC 8785 section 3.2.2's string/literal values, with the unsupported
        # floating-point "numbers" member omitted for this integer-only profile.
        value = {
            "string": "€$\u000f\nA'B\"\\\\\"/",
            "literals": [None, True, False],
        }
        expected = r'''{"literals":[null,true,false],"string":"€$\u000f\nA'B\"\\\\\"/"}'''.encode("utf-8")
        self.assertEqual(gate.canonical_json(value), expected)

    def test_rfc8785_profile_sorts_ascii_properties_recursively(self):
        value = {"z": {"b": 1, "a": 2}, "a": [{"d": 4, "c": 3}]}
        self.assertEqual(
            gate.canonical_json(value),
            b'{"a":[{"c":3,"d":4}],"z":{"a":2,"b":1}}',
        )

    def test_rfc8785_profile_preserves_unicode_and_escapes_controls(self):
        self.assertEqual(
            gate.canonical_json({"text": "mañana 😀"}),
            '{"text":"mañana 😀"}'.encode("utf-8"),
        )
        self.assertEqual(
            gate.canonical_json({"controls": "\u0000\b\t\n\u000b\f\r\u000e"}),
            b'{"controls":"\\u0000\\b\\t\\n\\u000b\\f\\r\\u000e"}',
        )

    def test_rfc8785_profile_safe_integer_boundaries(self):
        maximum_safe_integer = 2**53 - 1
        self.assertEqual(
            gate.canonical_json({"n": maximum_safe_integer}),
            b'{"n":9007199254740991}',
        )
        self.assertEqual(
            gate.canonical_json({"n": -maximum_safe_integer}),
            b'{"n":-9007199254740991}',
        )
        for unsupported in (
            {"float": 1.5},
            {"above_safe_integer": 2**53},
            {"below_safe_integer": -(2**53)},
            {"ñ": "non-ASCII property name"},
            {"surrogate": "\ud800"},
        ):
            with self.subTest(unsupported=repr(unsupported)):
                with self.assertRaises((ValueError, UnicodeEncodeError)):
                    gate.canonical_json(unsupported)

    def test_reparse_attribute_covers_junction_tags(self):
        simulated_junction = SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=0x400,
        )
        self.assertTrue(gate._is_reparse_stat(simulated_junction))

    def test_manifest_rejects_hardlinked_file_in_temp_package(self):
        with tempfile.TemporaryDirectory(prefix="inventarios_hardlink_") as temp:
            root = Path(temp)
            package = root / "package"
            package.mkdir()
            exe = package / "SistemaInventarios.exe"
            exe.write_bytes(b"fixture-not-executable")
            alias = root / "alias.exe"
            try:
                os.link(exe, alias)
            except OSError as exc:
                self.skipTest(f"El filesystem temporal no permite hardlinks: {exc}")
            with self.assertRaisesRegex(ValueError, "hardlinks"):
                gate._manifest_payload(package)

    def test_manifest_rejects_symlink_or_directory_reparse_point(self):
        with tempfile.TemporaryDirectory(prefix="inventarios_reparse_") as temp:
            root = Path(temp)
            package = root / "package"
            package.mkdir()
            target = root / "outside"
            target.mkdir()
            link = package / "linked-directory"
            try:
                os.symlink(target, link, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"El entorno no permite crear symlinks de prueba: {exc}")
            with self.assertRaisesRegex(ValueError, "reparse points"):
                gate._manifest_payload(package)

    def test_manifest_rejects_package_root_reparse_alias(self):
        with tempfile.TemporaryDirectory(prefix="inventarios_root_alias_") as temp:
            root = Path(temp)
            package = root / "package"
            package.mkdir()
            (package / "SistemaInventarios.exe").write_bytes(b"fixture-not-executable")
            alias = root / "package-alias"
            try:
                os.symlink(package, alias, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"El entorno no permite crear symlinks de prueba: {exc}")
            with self.assertRaisesRegex(gate.ReleaseGateError, "reparse point"):
                gate._manifest_payload(alias)

    @unittest.skipUnless(os.name == "nt", "junction real solo está disponible en Windows")
    def test_manifest_rejects_real_windows_junction_in_temp(self):
        with tempfile.TemporaryDirectory(prefix="inventarios_junction_real_") as temp:
            root = Path(temp)
            package = root / "package"
            package.mkdir()
            (package / "SistemaInventarios.exe").write_bytes(b"fixture-not-executable")
            target = root / "junction-target"
            target.mkdir()
            junction = package / "real-junction"
            command = ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target)]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()
                self.skipTest(
                    "NO EJECUTADA: Windows no permitió crear la junction temporal "
                    f"(código {result.returncode}): {detail}"
                )
            try:
                self.assertTrue(gate._is_reparse_stat(os.lstat(junction)))
                with self.assertRaisesRegex(ValueError, "reparse points"):
                    gate._manifest_payload(package)
            finally:
                if os.path.lexists(junction):
                    os.rmdir(junction)

    def test_installed_path_normalization_does_not_create_missing_folder(self):
        with tempfile.TemporaryDirectory(prefix="inventarios_route_identity_") as temp:
            parent = Path(temp) / "ProgramData"
            parent.mkdir()
            expected = parent / "SistemaInventarios"
            equivalent_spelling = str(parent / "." / "SistemaInventarios")
            with patch.object(rutas, "PROGRAM_DATA_DIR", expected):
                with patch.object(gate, "require_frozen_production") as require_release:
                    gate.require_installed_path_if_production(equivalent_spelling)
            require_release.assert_called_once()
            self.assertFalse(expected.exists())

    def test_installed_path_rejects_symlink_alias_to_expected_folder(self):
        with tempfile.TemporaryDirectory(prefix="inventarios_route_alias_") as temp:
            root = Path(temp)
            real_parent = root / "real"
            real_parent.mkdir()
            expected = real_parent / "SistemaInventarios"
            expected.mkdir()
            alias_parent = root / "alias"
            try:
                os.symlink(real_parent, alias_parent, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"El entorno no permite crear symlinks de prueba: {exc}")
            alternate = alias_parent / "SistemaInventarios"
            with patch.object(rutas, "PROGRAM_DATA_DIR", expected):
                with self.assertRaisesRegex(gate.ReleaseGateError, "alternativa equivalente"):
                    gate.require_installed_path_if_production(alternate)

    def test_installed_path_rejects_reparse_component_even_at_expected_spelling(self):
        with tempfile.TemporaryDirectory(prefix="inventarios_route_reparse_") as temp:
            root = Path(temp)
            real_parent = root / "real"
            real_parent.mkdir()
            expected = root / "redirected" / "SistemaInventarios"
            try:
                os.symlink(real_parent, expected.parent, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"El entorno no permite crear symlinks de prueba: {exc}")
            with patch.object(rutas, "PROGRAM_DATA_DIR", expected):
                with self.assertRaisesRegex(gate.ReleaseGateError, "reparse point"):
                    gate.require_installed_path_if_production(expected)

    def test_candidate_manifest_does_not_authorize_or_modify_payload(self):
        with tempfile.TemporaryDirectory(prefix="inventarios_candidate_") as temp:
            root = Path(temp)
            exe = root / "SistemaInventarios.exe"
            exe.write_bytes(b"fixture-not-executable")
            payload_before = exe.read_bytes()
            digest = gate.write_candidate_manifest(root)
            self.assertEqual(len(digest), 64)
            self.assertEqual(exe.read_bytes(), payload_before)
            self.assertTrue((root / gate.MANIFEST_NAME).is_file())
            self.assertFalse((root / gate.AUTHORIZATION_NAME).exists())
            with self.assertRaises(gate.ReleaseGateError):
                gate.verify_release_authorization(root)

    def test_existing_ba_owner_is_observed_but_not_production_ready(self):
        assessment = gate.assessment_from_owner_observation(
            "S-1-5-32-544", route_validated=True, folder_exists=True,
            folder_accessible=True, dacl_exact_and_protected=True,
            operator_sid_accepted=True, release_authorization_valid=True)
        self.assertEqual(assessment.owner_sid_observed, "S-1-5-32-544")
        self.assertTrue(assessment.owner_sid_allowed_by_policy)
        self.assertTrue(assessment.owner_sid_matches_ba)
        self.assertFalse(assessment.owner_assignment_procedure_validated)
        self.assertFalse(assessment.production_prepared)

    def test_owner_system_is_policy_allowed_but_not_ba_verified(self):
        assessment = gate.assessment_from_owner_observation("S-1-5-18")
        self.assertTrue(assessment.owner_sid_allowed_by_policy)
        self.assertFalse(assessment.owner_sid_matches_ba)
        self.assertFalse(assessment.production_prepared)

    def test_frozen_build_fails_closed_without_key_and_t1b(self):
        with tempfile.TemporaryDirectory(prefix="inventarios_frozen_gate_") as temp:
            with patch.object(sys, "frozen", True, create=True):
                with self.assertRaises(gate.ReleaseGateError):
                    gate.require_frozen_production(temp)

    def test_authorizer_fails_before_resolving_candidate_or_private_key_without_release_keys(self):
        with self.assertRaises(gate.ReleaseGateError):
            release_signer.autorizar(
                RAIZ / "no-se-debe-leer",
                RAIZ / "tampoco-se-debe-leer.pem",
                release_id="release-test",
                release_sequence=1,
                t1b_evidence_sha256="0" * 64,
                expires_at="2099-01-01T00:00:00Z",
            )

    def test_installed_route_rejects_arbitrary_argument_and_environment_override(self):
        with tempfile.TemporaryDirectory(prefix="inventarios_route_") as temp:
            arbitrary = Path(temp) / "datos"
            with self.assertRaises(ValueError):
                rutas.validar_datos_instalados(arbitrary)
            with patch.dict("os.environ", {"INVENTARIOS_DATOS_INSTALADOS": str(arbitrary)}):
                self.assertEqual(rutas.validar_datos_instalados(), rutas.PROGRAM_DATA_DIR.resolve())

    def test_settings_launcher_and_installer_have_static_gate_sites(self):
        launcher = (RAIZ / "desktop/launcher.py").read_text(encoding="utf-8")
        init = (RAIZ / "desktop/inicializacion.py").read_text(encoding="utf-8")
        settings = (RAIZ / "backend/config/settings/base.py").read_text(encoding="utf-8")
        setup = (RAIZ / "desktop/installer/setup.iss").read_text(encoding="utf-8")
        compiler = (RAIZ / "scripts/compilar_instalador.py").read_text(encoding="utf-8")
        self.assertIn("require_frozen_production", launcher)
        self.assertIn("require_installed_path_if_production", init)
        self.assertIn("require_frozen_production", settings)
        self.assertIn("Result := False;\n  Exit;", setup.split("function InitializeSetup(): Boolean;")[1])
        self.assertIn("verify_release_authorization(paquete)", compiler)
        self.assertIn("--solo-pruebas-vm está bloqueado", compiler)


if __name__ == "__main__":
    unittest.main()
