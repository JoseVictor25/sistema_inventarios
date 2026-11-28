"""Arnés N1 explícito para T1-B. Nunca evalúa ni modifica ProgramData."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import uuid

from desktop.preparacion_owner_ba import (
    PreparacionOwnerError,
    Win32SecurityApi,
    _prepare_open_directory_b,
)
from desktop.release_gate import _reject_reparse_components


def _dentro(ruta, raiz):
    try:
        Path(os.path.abspath(os.path.normpath(str(ruta)))).relative_to(
            Path(os.path.abspath(os.path.normpath(str(raiz)))))
        return True
    except (OSError, ValueError, RuntimeError):
        return False


def run_n1(sid_operator, *, api_factory=None, temp_root_override=None):
    if os.name != "nt":
        raise RuntimeError("N1 solo puede ejecutarse en Windows.")
    # El TEMP se abre desde la raíz del volumen, componente por componente.
    temp_raw = str(temp_root_override) if temp_root_override is not None else tempfile.gettempdir()
    temp_root = Path(os.path.abspath(os.path.normpath(temp_raw)))
    _reject_reparse_components(temp_root)
    report = {
        "scope": "N1_TEMP_ONLY",
        "temporary_root": str(temp_root),
        "programdata_touched": False,
        "programdata_parent_access_assessed": False,
        "results": {},
    }
    api = (api_factory or Win32SecurityApi)()
    report["run_root"] = "<handle-relative TEMP child>"
    handles = []
    cleanup_errors = []
    try:
        with api.open_directory_chain(temp_root) as temp_handle:
            # Unique name; creation is relative to the pinned TEMP handle.
            root_name = "sistema_inventarios_n1_owner_" + uuid.uuid4().hex
            root_handle, created = api.create_child_directory(temp_handle, root_name)
            if not created:
                api.close_handle(root_handle)
                raise PreparacionOwnerError("Colisión al crear raíz temporal N1.")
            handles.append(("raíz N1", root_handle))
            report["run_root"] = root_name

            success, made = api.create_child_directory(root_handle, "success", sid_operator)
            handles.append(("success", success))
            try:
                result = _prepare_open_directory_b(success, made, sid_operator, api=api)
                report["results"]["create_set_owner_verify"] = {
                    "status": "PASS" if made and result["owner_sid"] == "S-1-5-32-544"
                    and result["dacl_exact_and_protected"] else "FAIL", **result}
            except Exception as exc:
                report["results"]["create_set_owner_verify"] = {
                    "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}

            occupied, made = api.create_child_directory(root_handle, "preexisting_unrecognized")
            handles.append(("preexisting_unrecognized", occupied))
            try:
                result = _prepare_open_directory_b(occupied, False, sid_operator, api=api)
                report["results"]["preexisting_unrecognized"] = {"status": "FAIL", **result}
            except PreparacionOwnerError as exc:
                report["results"]["preexisting_unrecognized"] = {
                    "status": "PASS_REJECTED", "error": str(exc)}

            try:
                unexpected = api.open_child_directory(root_handle, "missing_parent")
                api.close_handle(unexpected)
                report["results"]["missing_parent"] = {"status": "FAIL", "error": "se abrió"}
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
                            "attributes_before": before, "attributes_during": during,
                            "attributes_after": after}
            except Exception as exc:
                report["results"]["restore_privilege"] = {
                    "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        # Elimina únicamente por handles, hijos antes que la raíz. Si falla,
        # conserva el diagnóstico y aun así cierra todos los handles.
        for label, handle in reversed(handles):
            try:
                api.delete_directory_handle(handle)
            except Exception as exc:
                cleanup_errors.append(f"{label}: {type(exc).__name__}: {exc}")
            finally:
                try:
                    api.close_handle(handle)
                except Exception as exc:
                    cleanup_errors.append(f"cierre {label}: {type(exc).__name__}: {exc}")
    if cleanup_errors:
        report["cleanup_residue"] = cleanup_errors

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
    return 0 if (not report.get("fatal_error") and not report.get("cleanup_residue")
                 and all(status.startswith("PASS") for status in statuses)) else 2


if __name__ == "__main__":
    raise SystemExit(main())
