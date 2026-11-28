"""Fail-closed release authorization and production readiness checks.

The T1-A tree intentionally has no release public key and no T1-B owner
validation identity. A frozen build therefore cannot enter production.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

PRODUCT_ID = "{E3488284-3044-4D29-AB90-33D28FD02467}"
PRODUCT_VERSION = "0.10.0"
POLICY_ID = "ntfs-data-acl-v1"
POLICY_SHA256 = hashlib.sha256(
    b"SYSTEM:FA:OI,CI;BA:FA:OI,CI;OPERATOR:0x1301bf:OI,CI;D:P;exactly-3"
).hexdigest()
VERIFIER_VERSION = 1
SCHEMA_VERSION = 1

# Provisioned only by the separately reviewed release process. None is a
# deliberate lock, not a development key or an example credential.
TRUSTED_RELEASE_PUBLIC_KEY_B64 = None
TRUSTED_RELEASE_KEY_ID = None
# Set only after T1-B/N1 approval and carried in the exact signed artifact.
OWNER_BA_VALIDATION_ID = None

MANIFEST_NAME = "release-manifest.json"
AUTHORIZATION_NAME = "release-authorization.json"
BUILD_IDENTITY_NAME = "release-build.json"
SIGNING_CONTEXT = b"SistemaInventarios-ReleaseAuthorization-v1\0"


class ReleaseGateError(RuntimeError):
    """The candidate is not authorized for production use."""


@dataclass(frozen=True)
class SecurityAssessment:
    route_validated: bool = False
    folder_exists: bool = False
    folder_accessible: bool = False
    dacl_exact_and_protected: bool = False
    owner_sid_observed: str | None = None
    owner_sid_allowed_by_policy: bool = False
    owner_sid_matches_ba: bool = False
    owner_assignment_procedure_validated: bool = False
    operator_sid_accepted: bool = False
    release_authorization_valid: bool = False
    production_prepared: bool = False
    failure_reason: str | None = None


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Clave JSON duplicada: {key}")
        result[key] = value
    return result


def _load_json(path):
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("JSON no puede llevar BOM")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys), raw


def _is_sha256_hex(value):
    return (isinstance(value, str) and len(value) == 64
            and all(character in "0123456789abcdef" for character in value))


def _parse_utc_timestamp(value, field):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"Fecha UTC con sufijo Z requerida: {field}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"Fecha UTC inválida: {field}") from exc
    canonical = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    if parsed.microsecond or canonical != value:
        raise ValueError(f"Formato UTC no canónico: {field}")
    return parsed


def _decode_ed25519_signature(value):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    if not isinstance(value, str) or len(value) != 86 or any(char not in alphabet for char in value):
        raise ValueError("Firma Ed25519 base64url inválida")
    try:
        signature = base64.urlsafe_b64decode(value + "==")
    except Exception as exc:
        raise ValueError("Firma Ed25519 base64url inválida") from exc
    canonical = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    if len(signature) != 64 or canonical != value:
        raise ValueError("Firma Ed25519 base64url no canónica")
    return signature


def canonical_json(value):
    """RFC 8785 serialization for this release schema's restricted JSON profile.

    Object property names are ASCII and numbers are safe integers only. That
    restriction makes Python's ordinal key ordering equivalent to JCS UTF-16
    ordering and decimal integer output equivalent to ECMAScript number output.
    This is not a general-purpose JCS implementation.
    """
    def validate(item):
        if isinstance(item, bool) or item is None:
            return
        if isinstance(item, str):
            item.encode("utf-8", errors="strict")
            return
        if isinstance(item, int) and not isinstance(item, bool):
            if not -(2**53 - 1) <= item <= 2**53 - 1:
                raise ValueError("JCS del release solo admite enteros seguros IEEE-754")
            return
        if isinstance(item, list):
            for child in item:
                validate(child)
            return
        if isinstance(item, dict):
            if not all(isinstance(key, str) and key.isascii() for key in item):
                raise ValueError("JCS del release solo admite nombres de propiedad ASCII")
            for key, child in item.items():
                key.encode("utf-8", errors="strict")
                validate(child)
            return
        raise ValueError("Tipo JSON no permitido en autorización")

    validate(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _is_reparse_stat(info):
    return (stat.S_ISLNK(info.st_mode)
            or bool(getattr(info, "st_file_attributes", 0) & 0x400))


def _reject_reparse_components(path):
    """Reject reparse points in existing path components without creating them."""
    absolute = Path(os.path.abspath(os.path.normpath(str(path))))
    prefix = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        prefix = prefix / component
        try:
            info = os.lstat(prefix)
        except FileNotFoundError:
            break
        except OSError as exc:
            raise ReleaseGateError(f"No se pudo clasificar el componente de ruta: {prefix}") from exc
        if _is_reparse_stat(info):
            raise ReleaseGateError(f"Ruta instalada contiene symlink, junction u otro reparse point: {prefix}")


def _path_key(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(str(path))))


def _same_existing_object(left, right):
    try:
        return os.path.samefile(left, right)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ReleaseGateError("No se pudo determinar la identidad física de la ruta.") from exc


def _same_parent_entry(left, right):
    """Compare parent directory identity when the final directory is absent."""
    if os.path.normcase(Path(left).name) != os.path.normcase(Path(right).name):
        return False
    return _same_existing_object(Path(left).parent, Path(right).parent)


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_manifest_row(path, relative):
    """Hash one open file and reject hardlinks or observed path replacement.

    The open handle pins the bytes read, but not the directory entry used later
    by the signer or Inno Setup. A replacement race after the final lstat still
    requires handle-based packaging or immutable storage to eliminate.
    """
    before = os.lstat(path)
    if _is_reparse_stat(before) or not stat.S_ISREG(before.st_mode):
        raise ValueError(f"El manifiesto solo admite archivos regulares: {relative}")
    if getattr(before, "st_nlink", 0) != 1:
        raise ValueError(f"No se admiten hardlinks en el paquete: {relative}")

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or getattr(opened, "st_nlink", 0) != 1
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
            raise ValueError(f"El archivo cambió al abrirse: {relative}")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = os.lstat(path)
    identity_before = (before.st_dev, before.st_ino, before.st_size,
                       before.st_mtime_ns, before.st_nlink)
    identity_after = (after.st_dev, after.st_ino, after.st_size,
                      after.st_mtime_ns, after.st_nlink)
    if identity_before != identity_after or _is_reparse_stat(after):
        raise ValueError(f"El archivo cambió durante la lectura: {relative}")
    return {"path": relative, "size": opened.st_size, "sha256": digest.hexdigest()}


def _validated_package_root(root):
    root = Path(os.path.abspath(os.path.normpath(str(root))))
    _reject_reparse_components(root)
    try:
        root_info = os.lstat(root)
    except OSError as exc:
        raise ValueError(f"No se pudo consultar el directorio del paquete: {root}") from exc
    if _is_reparse_stat(root_info) or not stat.S_ISDIR(root_info.st_mode):
        raise ValueError("La raíz del paquete debe ser un directorio real, no un reparse point")
    return root


def _manifest_payload(root):
    """Hash a path-based package walk and reject observed links/replacements.

    The walk uses lstat and each file is hashed through one open handle with
    identity checks before and after reading. It cannot prevent an attacker or
    concurrent process from swapping a directory between scandir calls, or
    replacing a file after the final lstat and before a later consumer opens
    it. Eliminating those races requires handle-relative traversal and passing
    pinned handles to consumers, or compiling from storage made immutable for
    the whole signing/build operation.
    """
    root = _validated_package_root(root)

    rows = []
    folded_paths = set()

    def visit(directory):
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name.casefold())
        except OSError as exc:
            raise ValueError(f"No se pudo recorrer el paquete: {directory}") from exc
        for entry in entries:
            path = Path(entry.path)
            # DirEntry.stat may omit st_nlink on Windows; os.lstat exposes it.
            info = os.lstat(path)
            if _is_reparse_stat(info):
                raise ValueError(f"No se admiten symlinks, junctions ni reparse points: {path.name}")
            if stat.S_ISDIR(info.st_mode):
                visit(path)
                continue
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f"El paquete contiene un objeto no regular: {path.name}")
            if getattr(info, "st_nlink", 0) != 1:
                raise ValueError(f"No se admiten hardlinks en el paquete: {path.name}")
            relative = path.relative_to(root).as_posix()
            folded = relative.casefold()
            if folded in folded_paths:
                raise ValueError(f"Colisión de rutas sin distinguir mayúsculas: {relative}")
            folded_paths.add(folded)
            if relative in {MANIFEST_NAME, AUTHORIZATION_NAME}:
                continue
            if folded in {MANIFEST_NAME.casefold(), AUTHORIZATION_NAME.casefold()}:
                raise ValueError("Colisión de nombres del manifiesto de release")
            rows.append(_file_manifest_row(path, relative))

    visit(root)
    rows.sort(key=lambda row: row["path"].casefold())
    if not any(row["path"].casefold() == "sistemainventarios.exe" for row in rows):
        raise ValueError("Falta SistemaInventarios.exe")
    return {"schema_version": SCHEMA_VERSION, "files": rows}


def write_candidate_manifest(candidate):
    """Write an unsigned manifest; this only labels a candidate, never authorizes it."""
    root = _validated_package_root(candidate)
    if (root / AUTHORIZATION_NAME).exists():
        raise ReleaseGateError("No se regenera el manifiesto de un payload ya autorizado.")
    manifest = _manifest_payload(root)
    target = root / MANIFEST_NAME
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_bytes(canonical_json(manifest))
    temporary.replace(target)
    return hashlib.sha256(target.read_bytes()).hexdigest()


def verify_release_authorization(package_root, *, now=None):
    """Verify signed metadata and every payload file; fail closed by default."""
    if not TRUSTED_RELEASE_PUBLIC_KEY_B64 or not OWNER_BA_VALIDATION_ID:
        raise ReleaseGateError("Producción bloqueada: falta clave de release o validación T1-B del owner BA.")

    root = _validated_package_root(package_root)
    manifest, manifest_raw = _load_json(root / MANIFEST_NAME)
    authorization, _ = _load_json(root / AUTHORIZATION_NAME)
    if canonical_json(manifest) != manifest_raw:
        raise ValueError("El manifiesto no usa la serialización canónica requerida")
    if (set(manifest) != {"schema_version", "files"}
            or type(manifest["schema_version"]) is not int
            or manifest["schema_version"] != SCHEMA_VERSION):
        raise ValueError("Esquema de manifiesto incompatible")
    if not isinstance(manifest["files"], list):
        raise ValueError("Lista de archivos inválida")

    payload = authorization.get("payload")
    signature_text = authorization.get("signature")
    if set(authorization) != {"payload", "signature"} or not isinstance(payload, dict):
        raise ValueError("Sobre de autorización inválido")
    signature = _decode_ed25519_signature(signature_text)
    expected = {
        "schema_version", "product_id", "product_version", "release_id", "release_sequence",
        "channel", "target", "policy_id", "policy_sha256", "verifier_version",
        "t1_b_approved", "t1_b_validation_id", "t1_b_evidence_sha256",
        "artifact_manifest_sha256", "executable_sha256", "issued_at", "not_before",
        "expires_at", "key_id", "algorithm",
    }
    if set(payload) != expected:
        raise ValueError("Campos de autorización ausentes o inesperados")
    for field in ("schema_version", "verifier_version", "release_sequence"):
        if type(payload[field]) is not int:
            raise ValueError(f"Campo entero inválido en autorización: {field}")
    if payload["release_sequence"] < 1:
        raise ValueError("Secuencia de release inválida")
    for field in ("product_id", "product_version", "release_id", "channel", "target",
                  "policy_id", "policy_sha256", "t1_b_validation_id",
                  "t1_b_evidence_sha256", "artifact_manifest_sha256",
                  "executable_sha256", "issued_at", "not_before", "expires_at",
                  "key_id", "algorithm"):
        if not isinstance(payload[field], str):
            raise ValueError(f"Campo de texto inválido en autorización: {field}")
    if not payload["release_id"].strip():
        raise ValueError("Identificador de release vacío")
    for field in ("policy_sha256", "t1_b_evidence_sha256",
                  "artifact_manifest_sha256", "executable_sha256"):
        if not _is_sha256_hex(payload[field]):
            raise ValueError(f"Hash SHA-256 inválido en autorización: {field}")
    if (payload["schema_version"] != SCHEMA_VERSION
            or payload["product_id"] != PRODUCT_ID
            or payload["product_version"] != PRODUCT_VERSION
            or payload["channel"] != "production"
            or payload["target"] != "windows-x64-win11"
            or payload["policy_id"] != POLICY_ID
            or payload["policy_sha256"] != POLICY_SHA256
            or payload["verifier_version"] != VERIFIER_VERSION
            or payload["t1_b_approved"] is not True
            or payload["t1_b_validation_id"] != OWNER_BA_VALIDATION_ID
            or payload["key_id"] != TRUSTED_RELEASE_KEY_ID
            or payload["algorithm"] != "Ed25519"):
        raise ValueError("Autorización incompatible con producto, política o T1-B")

    manifest_digest = hashlib.sha256(manifest_raw).hexdigest()
    if payload["artifact_manifest_sha256"] != manifest_digest:
        raise ValueError("La autorización no corresponde a este manifiesto")
    exe = root / "SistemaInventarios.exe"
    if payload["executable_sha256"] != _sha256(exe):
        raise ValueError("La autorización no corresponde a este ejecutable")

    _verify_file_rows(root, manifest["files"])
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("El reloj de verificación debe incluir zona horaria")
    issued = _parse_utc_timestamp(payload["issued_at"], "issued_at")
    begins = _parse_utc_timestamp(payload["not_before"], "not_before")
    expires = _parse_utc_timestamp(payload["expires_at"], "expires_at")
    if not (issued <= begins < expires) or not (issued <= current < expires) or current < begins:
        raise ValueError("Autorización no vigente o expirada")

    key = base64.b64decode(TRUSTED_RELEASE_PUBLIC_KEY_B64, validate=True)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    Ed25519PublicKey.from_public_bytes(key).verify(
        signature, SIGNING_CONTEXT + canonical_json(payload))
    return payload


def _verify_file_rows(root, rows):
    seen = set()
    for row in rows:
        if set(row) != {"path", "size", "sha256"}:
            raise ValueError("Entrada de manifiesto inválida")
        if type(row["size"]) is not int or row["size"] < 0:
            raise ValueError("Tamaño inválido en manifiesto")
        if not _is_sha256_hex(row["sha256"]):
            raise ValueError("Hash inválido en manifiesto")
        rel = row["path"]
        if not isinstance(rel, str) or rel.startswith("/") or "\\" in rel or ".." in Path(rel).parts:
            raise ValueError("Ruta de manifiesto inválida")
        folded = rel.casefold()
        if folded in seen:
            raise ValueError("Ruta duplicada en manifiesto")
        seen.add(folded)
    actual_rows = _manifest_payload(root)["files"]
    if actual_rows != rows:
        raise ValueError("El conjunto o contenido de archivos no coincide con el manifiesto")


def require_frozen_production(package_root):
    if not getattr(sys, "frozen", False):
        raise ReleaseGateError("El modo instalado solo está disponible en artefactos congelados autorizados.")
    payload = verify_release_authorization(package_root)
    if payload["t1_b_validation_id"] != OWNER_BA_VALIDATION_ID:
        raise ReleaseGateError("Producción bloqueada: owner BA no está validado por T1-B.")
    return payload


def require_installed_path_if_production(path):
    """Protect installed-path use against textual aliases and filesystem redirects.

    For an absent target, normalized and resolved paths are compared without
    creating it. For existing targets, samefile also compares filesystem object
    identity. Reparse points in the installed path are always rejected. These
    checks do not pin the directory against later replacement (TOCTOU).
    """
    from .rutas import PROGRAM_DATA_DIR
    candidate = Path(os.path.abspath(os.path.normpath(str(path))))
    expected = Path(os.path.abspath(os.path.normpath(str(PROGRAM_DATA_DIR))))
    try:
        candidate_resolved = candidate.resolve(strict=False)
        expected_resolved = expected.resolve(strict=False)
        same_lexical_path = _path_key(candidate) == _path_key(expected)
        same_resolved_path = _path_key(candidate_resolved) == _path_key(expected_resolved)
        same_object = (_same_existing_object(candidate, expected)
                       or _same_parent_entry(candidate, expected))
    except (OSError, RuntimeError) as exc:
        raise ReleaseGateError("No se pudo clasificar de forma segura la ruta de datos.") from exc

    is_installed = same_lexical_path or same_resolved_path or same_object
    if is_installed:
        if not same_lexical_path:
            raise ReleaseGateError("Se rechaza una ruta alternativa equivalente a la ruta instalada.")
        _reject_reparse_components(candidate)
    if is_installed or getattr(sys, "frozen", False):
        require_frozen_production(Path(sys.executable).resolve().parent)


def production_readiness(*, route_validated=False, folder_exists=False,
                         folder_accessible=False, dacl_exact_and_protected=False,
                         owner_sid_observed=None, owner_sid_allowed_by_policy=False,
                         owner_sid_matches_ba=False, operator_sid_accepted=False,
                         release_authorization_valid=False):
    """Compose observations without promoting partial checks to readiness."""
    # T1-A deliberately has no final folder verifier. Boolean observations are
    # not proof objects and must never be enough to authorize installed use.
    ready = False
    reason = "Preparación de producción bloqueada hasta validar T1-B."
    return SecurityAssessment(
        route_validated=route_validated,
        folder_exists=folder_exists,
        folder_accessible=folder_accessible,
        dacl_exact_and_protected=dacl_exact_and_protected,
        owner_sid_observed=owner_sid_observed,
        owner_sid_allowed_by_policy=owner_sid_allowed_by_policy,
        owner_sid_matches_ba=owner_sid_matches_ba,
        # T1-A has only an observation; the assignment procedure is unvalidated.
        owner_assignment_procedure_validated=False,
        operator_sid_accepted=operator_sid_accepted,
        release_authorization_valid=release_authorization_valid,
        production_prepared=ready,
        failure_reason=reason,
    )


def assessment_from_owner_observation(owner_sid, **checks):
    """Report SID observations and comparisons, never assignment validation."""
    owner_sid_allowed_by_policy = owner_sid in {"S-1-5-18", "S-1-5-32-544"}
    owner_sid_matches_ba = owner_sid == "S-1-5-32-544"
    return production_readiness(
        owner_sid_observed=owner_sid,
        owner_sid_allowed_by_policy=owner_sid_allowed_by_policy,
        owner_sid_matches_ba=owner_sid_matches_ba,
        **checks,
    )
