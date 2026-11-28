"""Sign an immutable candidate after T1-B approval; never builds the payload."""
import argparse
from datetime import datetime, timezone
import base64
import hashlib
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from desktop import release_gate as gate


def _esta_dentro(ruta, raiz):
    try:
        Path(ruta).resolve().relative_to(Path(raiz).resolve())
        return True
    except ValueError:
        return False


def autorizar(candidate, private_key_path, *, release_id, release_sequence,
              t1b_evidence_sha256, expires_at):
    if gate.TRUSTED_RELEASE_PUBLIC_KEY_B64 is None or gate.TRUSTED_RELEASE_KEY_ID is None:
        raise gate.ReleaseGateError("No hay clave pública de release fijada; firma bloqueada.")
    if gate.OWNER_BA_VALIDATION_ID is None:
        raise gate.ReleaseGateError("T1-B no está validado; no se puede autorizar producción.")

    root = gate._validated_package_root(candidate)
    private_path = Path(private_key_path).resolve(strict=True)
    if _esta_dentro(root, RAIZ):
        raise ValueError("El candidato debe estar fuera del repositorio.")
    if _esta_dentro(private_path, RAIZ) or _esta_dentro(private_path, root):
        raise ValueError("La clave privada debe permanecer fuera del repositorio y del candidato.")
    if (not isinstance(release_id, str) or not release_id.strip()
            or type(release_sequence) is not int or release_sequence < 1):
        raise ValueError("Identificador y secuencia de release inválidos.")
    if not gate._is_sha256_hex(t1b_evidence_sha256):
        raise ValueError("La evidencia T1-B debe identificarse con SHA-256 hexadecimal.")
    manifest_path = root / gate.MANIFEST_NAME
    current_manifest = gate._manifest_payload(root)
    manifest, raw_manifest = gate._load_json(manifest_path)
    if gate.canonical_json(manifest) != raw_manifest or manifest != current_manifest:
        raise ValueError("El candidato cambió o su manifiesto no coincide con los bytes actuales")

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key_bytes = private_path.read_bytes()
    private_key = serialization.load_pem_private_key(key_bytes, password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("La clave externa debe ser una clave privada Ed25519 PEM")
    public_der = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    pinned = base64.b64decode(gate.TRUSTED_RELEASE_PUBLIC_KEY_B64, validate=True)
    if public_der != pinned:
        raise ValueError("La clave privada no corresponde a la clave pública fijada")

    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires = gate._parse_utc_timestamp(expires_at, "expires_at")
    if expires <= now:
        raise ValueError("La autorización debe expirar en una fecha UTC futura.")
    payload = {
        "schema_version": gate.SCHEMA_VERSION,
        "product_id": gate.PRODUCT_ID,
        "product_version": gate.PRODUCT_VERSION,
        "release_id": release_id,
        "release_sequence": release_sequence,
        "channel": "production",
        "target": "windows-x64-win11",
        "policy_id": gate.POLICY_ID,
        "policy_sha256": gate.POLICY_SHA256,
        "verifier_version": gate.VERIFIER_VERSION,
        "t1_b_approved": True,
        "t1_b_validation_id": gate.OWNER_BA_VALIDATION_ID,
        "t1_b_evidence_sha256": t1b_evidence_sha256,
        "artifact_manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "executable_sha256": gate._sha256(root / "SistemaInventarios.exe"),
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "not_before": now.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "key_id": gate.TRUSTED_RELEASE_KEY_ID,
        "algorithm": "Ed25519",
    }
    signature = private_key.sign(gate.SIGNING_CONTEXT + gate.canonical_json(payload))
    envelope = {"payload": payload, "signature": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")}
    target = root / gate.AUTHORIZATION_NAME
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_bytes(gate.canonical_json(envelope))
    temporary.replace(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--private-key", required=True, type=Path,
                        help="Clave privada PEM ubicada fuera del repositorio y del paquete.")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--release-sequence", required=True, type=int)
    parser.add_argument("--t1b-evidence-sha256", required=True)
    parser.add_argument("--expires-at", required=True, help="Fecha UTC ISO-8601 con Z.")
    args = parser.parse_args()
    try:
        result = autorizar(args.candidate, args.private_key, release_id=args.release_id,
                           release_sequence=args.release_sequence,
                           t1b_evidence_sha256=args.t1b_evidence_sha256,
                           expires_at=args.expires_at)
    except Exception as exc:
        parser.exit(2, f"Autorización rechazada: {exc}\n")
    print("Autorización creada para el payload exacto:", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
