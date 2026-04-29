"""Sign APK with v1 (JAR) signature using Python cryptography.

Creates a self-signed debug certificate and signs the APK.
No Java required.
"""

import hashlib
import base64
import os
import sys
import zipfile
import tempfile
import shutil
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7


def generate_debug_key():
    """Generate RSA key and self-signed certificate."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Android Debug"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Debug"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=10000))
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _is_signature_file(name):
    """Check if a META-INF file is a signature file (skip for v1 signing)."""
    upper = name.upper()
    if upper == "META-INF/MANIFEST.MF":
        return True
    if upper.startswith("META-INF/") and upper.endswith((".SF", ".RSA", ".DSA", ".EC")):
        return True
    return False


def compute_digests(apk_path):
    """Compute SHA-256 digests for all entries in the APK."""
    digests = {}
    with zipfile.ZipFile(apk_path, "r") as zf:
        for name in zf.namelist():
            if _is_signature_file(name):
                continue
            data = zf.read(name)
            digest = base64.b64encode(hashlib.sha256(data).digest()).decode()
            digests[name] = digest
    return digests


def create_manifest(digests):
    """Create MANIFEST.MF content."""
    lines = ["Manifest-Version: 1.0", "Created-By: 1.0 (Android SignApk)", ""]
    for name, digest in sorted(digests.items()):
        lines.append(f"Name: {name}")
        lines.append(f"SHA-256-Digest: {digest}")
        lines.append("")
    return "\r\n".join(lines)


def create_signature_file(manifest_content):
    """Create CERT.SF signature file."""
    manifest_bytes = manifest_content.encode("utf-8")
    main_digest = base64.b64encode(hashlib.sha256(manifest_bytes).digest()).decode()

    lines = [
        "Signature-Version: 1.0",
        f"SHA-256-Digest-Manifest: {main_digest}",
        "Created-By: 1.0 (Android SignApk)",
        "",
    ]

    # Per-entry digests
    sections = manifest_content.split("\r\n\r\n")
    for section in sections[1:]:  # Skip the main section
        if not section.strip():
            continue
        section_with_newline = section + "\r\n\r\n"
        section_digest = base64.b64encode(
            hashlib.sha256(section_with_newline.encode("utf-8")).digest()
        ).decode()
        # Extract name
        for line in section.split("\r\n"):
            if line.startswith("Name: "):
                name = line[6:]
                lines.append(f"Name: {name}")
                lines.append(f"SHA-256-Digest: {section_digest}")
                lines.append("")
                break

    return "\r\n".join(lines)


def create_pkcs7_signature(sf_content, key, cert):
    """Create PKCS#7 signature of the .SF file."""
    sf_bytes = sf_content.encode("utf-8")
    sig = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(sf_bytes)
        .add_signer(cert, key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.Binary, pkcs7.PKCS7Options.NoAttributes])
    )
    return sig


def sign_apk(apk_path, output_path=None):
    """Sign an APK with v1 JAR signature."""
    if output_path is None:
        output_path = apk_path

    print("[*] Generating debug key...")
    key, cert = generate_debug_key()

    print("[*] Computing digests...")
    digests = compute_digests(apk_path)
    print(f"[*] {len(digests)} entries to sign")

    print("[*] Creating MANIFEST.MF...")
    manifest = create_manifest(digests)

    print("[*] Creating CERT.SF...")
    sf = create_signature_file(manifest)

    print("[*] Creating PKCS#7 signature...")
    pkcs7_sig = create_pkcs7_signature(sf, key, cert)

    print("[*] Rewriting APK with signatures...")
    tmp_path = apk_path + ".tmp"
    with zipfile.ZipFile(apk_path, "r") as zf_in:
        with zipfile.ZipFile(tmp_path, "w") as zf_out:
            # Copy all original entries, skip only old signature files
            _sig_files = {"META-INF/MANIFEST.MF", "META-INF/CERT.SF", "META-INF/CERT.RSA"}
            for item in zf_in.infolist():
                fn = item.filename.upper()
                if fn in {s.upper() for s in _sig_files} or \
                   (fn.startswith("META-INF/") and fn.endswith((".SF", ".RSA", ".DSA", ".EC"))):
                    continue
                data = zf_in.read(item.filename)
                zf_out.writestr(item, data)

            # Add signature files (stored compressed)
            zf_out.writestr("META-INF/MANIFEST.MF", manifest, compress_type=zipfile.ZIP_DEFLATED)
            zf_out.writestr("META-INF/CERT.SF", sf, compress_type=zipfile.ZIP_DEFLATED)
            zf_out.writestr("META-INF/CERT.RSA", pkcs7_sig, compress_type=zipfile.ZIP_STORED)

    if output_path == apk_path:
        os.replace(tmp_path, output_path)
    else:
        shutil.move(tmp_path, output_path)

    print(f"[*] Signed APK: {output_path} ({os.path.getsize(output_path)} bytes)")


def main():
    apk_path = os.path.join(os.path.dirname(__file__), "apk_work", "avito-patched.apk")
    if not os.path.exists(apk_path):
        print(f"[-] Not found: {apk_path}")
        sys.exit(1)

    sign_apk(apk_path)
    print("[*] Done! APK is signed and ready to install.")


if __name__ == "__main__":
    main()
