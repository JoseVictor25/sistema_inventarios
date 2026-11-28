"""Arnés N1 explícito para T1-B. Nunca evalúa ni modifica ProgramData."""
import argparse
import json
import os
from pathlib import Path
import tempfile

from desktop.preparacion_owner_ba import (
    PreparacionOwnerError,
    Win32SecurityApi,
    _prepare_directory_b,
)


def _dentro(ruta, raiz):
    try:
        Path(ruta).resolve(strict=True).relative_to(Path(raiz).resolve(strict=True))
        return True
    except (OSError, ValueError, RuntimeError):
        return False


def run_n1(sid_operator):
    if os.name != "nt":
        raise RuntimeError("N1 solo puede ejecutarse en Windows.")
    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    report = {
        "scope": "N1_TEMP_ONLY",
        "temporary_root": str(temp_root),
        "programdata_touched": False,
        "programdata_parent_access_assessed": False,
        "results": {},
    }
    with tempfile.TemporaryDirectory(prefix="sistema_inventarios_n1_owner_") as raw_root:
        root = Path(raw_root).resolve(strict=True)
        if not _dentro(root, temp_root) or root == temp_root:
            raise RuntimeError("El TEMP generado no es descendiente controlado de TEMP.")
        report["run_root"] = str(root)

        api = Win32SecurityApi()
        try:
            result = _prepare_directory_b(
                root / "success", sid_operator, api=api, n1_temp_root=temp_root)
            report["results"]["create_set_owner_verify"] = {
                "status": "PASS" if result["created"]
                and result["owner_sid"] == "S-1-5-32-544"
                and result["dacl_exact_and_protected"] else "FAIL",
                "created": result["created"],
                "owner_sid": result["owner_sid"],
                "dacl_exact_and_protected": result["dacl_exact_and_protected"],
            }
        except Exception as exc:
            report["results"]["create_set_owner_verify"] = {
                "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}

        occupied = root / "preexisting_unrecognized"
        occupied.mkdir()
        try:
            _prepare_directory_b(occupied, sid_operator, api=api, n1_temp_root=temp_root)
            report["results"]["preexisting_unrecognized"] = {"status": "FAIL", "error": "se aceptó"}
        except PreparacionOwnerError as exc:
            report["results"]["preexisting_unrecognized"] = {
                "status": "PASS_REJECTED", "error": str(exc)}

        try:
            _prepare_directory_b(root / "missing_parent" / "target", sid_operator,
                                 api=api, n1_temp_root=temp_root)
            report["results"]["missing_parent"] = {"status": "FAIL", "error": "se creó"}
        except PreparacionOwnerError as exc:
            report["results"]["missing_parent"] = {"status": "PASS_REJECTED", "error": str(exc)}

        try:
            with api.effective_token() as token:
                luid = api._lookup_restore_luid()
                before = api._privilege_state(token, luid)
                if before is None:
                    report["results"]["restore_privilege"] = {
                        "status": "NOT_RUN", "reason": "SeRestorePrivilege ausente del token"}
                else:
                    with api.restore_privilege_temporarily(token, force=True):
                        during = api._privilege_state(token, luid)
                        if not (during & 0x2):
                            raise PreparacionOwnerError("SeRestorePrivilege no quedó habilitado.")
                    after = api._privilege_state(token, luid)
                    report["results"]["restore_privilege"] = {
                        "status": "PASS" if after == before else "FAIL",
                        "attributes_before": before,
                        "attributes_during": during,
                        "attributes_after": after,
                    }
        except Exception as exc:
            report["results"]["restore_privilege"] = {
                "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}

    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-n1", action="store_true",
                        help="Confirmación explícita: crea y asegura subdirectorios del TEMP actual.")
    parser.add_argument("--sid-operador", required=True,
                        help="SID local de usuario reservado para el ensayo N1.")
    args = parser.parse_args()
    if not args.run_n1:
        parser.error("Se requiere --run-n1; este arnés cambia ACL/owner solo bajo TEMP.")
    report = run_n1(args.sid_operador)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    statuses = [item["status"] for item in report["results"].values()]
    return 0 if all(status.startswith("PASS") for status in statuses) else 2


if __name__ == "__main__":
    raise SystemExit(main())
