"""APK Signature Scheme v2 — pure Python implementation.

Signs an APK with v2 scheme (required for Android 7+ / targetSdk 30+).
No Java or Android SDK required.

The v2 signature is stored in an APK Signing Block inserted between
the ZIP local entries and the Central Directory.
"""

import hashlib
import os
import struct
import sys
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding

# Constants
APK_SIG_BLOCK_MAGIC = b"APK Sig Block 42"
APK_SIG_V2_BLOCK_ID = 0x7109871a
CHUNK_SIZE = 1048576  # 1 MB
SIG_ALGO_RSASSA_PKCS1_V15_SHA256 = 0x0103


def generate_debug_key():
    """Generate RSA key pair and self-signed certificate."""
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


def _len_prefix(data: bytes) -> bytes:
    """Prefix bytes with uint32 LE length."""
    return struct.pack("<I", len(data)) + data


def _find_eocd(data: bytes) -> int:
    """Find End of Central Directory record."""
    pos = data.rfind(b"PK\x05\x06")
    if pos == -1:
        raise ValueError("Not a valid ZIP file (no EOCD)")
    return pos


def _find_cd(data: bytes, eocd_pos: int) -> int:
    """Get Central Directory offset from EOCD."""
    return struct.unpack_from("<I", data, eocd_pos + 16)[0]


def compute_v2_digest(section1: bytes, section3: bytes, section4: bytes) -> bytes:
    """Compute APK v2 digest over three APK sections.

    section1: ZIP local entries (before signing block)
    section3: ZIP Central Directory
    section4: ZIP EOCD (with cd_offset = original, i.e., start of section1 end)
    """
    chunk_digests = []

    for section in (section1, section3, section4):
        offset = 0
        while offset < len(section):
            chunk = section[offset:offset + CHUNK_SIZE]
            # Per-chunk digest: SHA256(0xa5 || uint32_le(chunk_len) || chunk)
            h = hashlib.sha256()
            h.update(b"\xa5")
            h.update(struct.pack("<I", len(chunk)))
            h.update(chunk)
            chunk_digests.append(h.digest())
            offset += CHUNK_SIZE

    # Top-level digest: SHA256(0x5a || uint32_le(num_chunks) || all_chunk_digests)
    h = hashlib.sha256()
    h.update(b"\x5a")
    h.update(struct.pack("<I", len(chunk_digests)))
    for cd in chunk_digests:
        h.update(cd)
    return h.digest()


def build_signed_data(digest: bytes, cert_der: bytes) -> bytes:
    """Build the signed_data structure for v2 signer.

    Format:
        uint32(digests_seq_size) + digests_entries
        uint32(certs_seq_size) + cert_entries
        uint32(attrs_seq_size) + attrs_entries  (empty)
    """
    # Build digest entry: uint32(algo_id) + uint32(digest_len) + digest_bytes
    digest_entry = (
        struct.pack("<I", SIG_ALGO_RSASSA_PKCS1_V15_SHA256)
        + _len_prefix(digest)
    )
    digests_seq = _len_prefix(digest_entry)

    # Build certificate entry
    certs_seq = _len_prefix(cert_der)

    # Empty additional attributes
    attrs_seq = b""

    return _len_prefix(digests_seq) + _len_prefix(certs_seq) + _len_prefix(attrs_seq)


def build_v2_signer(key, cert) -> bytes:
    """Build a complete v2 signer block (not yet including section digests)."""
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    pub_key_der = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return cert_der, pub_key_der


def build_signing_block(v2_block_value: bytes) -> bytes:
    """Build the complete APK Signing Block.

    Format:
        uint64(sb_size)
        [pairs]
        uint64(sb_size)
        "APK Sig Block 42"
    """
    # Build pair: uint64(pair_len) + uint32(pair_id) + pair_value
    pair_data = struct.pack("<I", APK_SIG_V2_BLOCK_ID) + v2_block_value
    pair = struct.pack("<Q", len(pair_data)) + pair_data

    # sb_size = pairs_size + 8 (for sb_size2) + 16 (for magic)
    pairs_data = pair
    sb_size = len(pairs_data) + 8 + 16

    block = struct.pack("<Q", sb_size)
    block += pairs_data
    block += struct.pack("<Q", sb_size)
    block += APK_SIG_BLOCK_MAGIC

    return block


def sign_apk_v2(apk_path: str, output_path: str = None):
    """Sign APK with v2 signature scheme."""
    if output_path is None:
        output_path = apk_path

    print("[*] Generating debug key...")
    key, cert = generate_debug_key()
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    pub_key_der = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    print("[*] Reading APK...")
    with open(apk_path, "rb") as f:
        apk_data = f.read()

    # Find ZIP structures
    eocd_pos = _find_eocd(apk_data)
    cd_offset = _find_cd(apk_data, eocd_pos)

    # Split into sections
    section1 = apk_data[:cd_offset]           # ZIP local entries
    section3 = apk_data[cd_offset:eocd_pos]   # Central Directory
    section4 = apk_data[eocd_pos:]            # EOCD

    print(f"[*] Section 1 (entries): {len(section1)} bytes")
    print(f"[*] Section 3 (CD):      {len(section3)} bytes")
    print(f"[*] Section 4 (EOCD):    {len(section4)} bytes")

    # Compute v2 digest
    # For signing, EOCD bytes 16-20 should contain cd_offset (= sb_offset)
    # In the unsigned APK, this is already the case, so use section4 as-is
    print("[*] Computing v2 digest (1 MB chunks)...")
    digest = compute_v2_digest(section1, section3, section4)
    print(f"[*] Digest: {digest.hex()[:32]}...")

    # Build signed_data
    signed_data_raw = build_signed_data(digest, cert_der)

    # Sign the signed_data
    print("[*] Signing with RSA-PKCS1-v1.5-SHA256...")
    signature_bytes = key.sign(
        signed_data_raw,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    print(f"[*] Signature: {len(signature_bytes)} bytes")

    # Build signature entry: uint32(algo_id) + len_prefix(sig_bytes)
    sig_entry = (
        struct.pack("<I", SIG_ALGO_RSASSA_PKCS1_V15_SHA256)
        + _len_prefix(signature_bytes)
    )

    # Build signer:
    #   len_prefix(signed_data_raw)
    #   len_prefix(signatures_seq)
    #   len_prefix(public_key)
    signer = (
        _len_prefix(signed_data_raw)
        + _len_prefix(_len_prefix(sig_entry))  # signatures sequence
        + _len_prefix(pub_key_der)
    )

    # Build v2 block value: uint32(signers_seq_size) + signers
    v2_block_value = _len_prefix(_len_prefix(signer))

    # Build APK Signing Block
    signing_block = build_signing_block(v2_block_value)
    print(f"[*] Signing block: {len(signing_block)} bytes")

    # Update EOCD with new CD offset
    new_cd_offset = cd_offset + len(signing_block)
    new_section4 = bytearray(section4)
    struct.pack_into("<I", new_section4, 16, new_cd_offset)

    # Write output
    print(f"[*] Writing signed APK...")
    with open(output_path, "wb") as f:
        f.write(section1)
        f.write(signing_block)
        f.write(section3)
        f.write(bytes(new_section4))

    size = os.path.getsize(output_path)
    print(f"[*] Signed APK: {output_path} ({size} bytes)")

    # Verify our own signature
    print("[*] Verifying...")
    _verify_own_signature(output_path)


def _verify_own_signature(apk_path: str):
    """Quick self-check that the signing block is present and well-formed."""
    with open(apk_path, "rb") as f:
        data = f.read()

    eocd_pos = _find_eocd(data)
    cd_offset = struct.unpack_from("<I", data, eocd_pos + 16)[0]

    # Search for magic before CD
    magic_pos = data.rfind(APK_SIG_BLOCK_MAGIC, 0, cd_offset)
    if magic_pos == -1:
        print("[-] FAIL: No APK Signing Block found!")
        return False

    # Read sb_size2
    sb_size2 = struct.unpack_from("<Q", data, magic_pos - 8)[0]
    sb_start = magic_pos + 16 - sb_size2 - 8
    sb_size1 = struct.unpack_from("<Q", data, sb_start)[0]

    if sb_size1 != sb_size2:
        print(f"[-] FAIL: size mismatch: {sb_size1} != {sb_size2}")
        return False

    # Read pair
    pair_offset = sb_start + 8
    pair_len = struct.unpack_from("<Q", data, pair_offset)[0]
    pair_id = struct.unpack_from("<I", data, pair_offset + 8)[0]

    if pair_id != APK_SIG_V2_BLOCK_ID:
        print(f"[-] FAIL: unexpected pair ID: {hex(pair_id)}")
        return False

    print(f"[*] OK: v2 signing block at offset {sb_start}, pair ID={hex(pair_id)}, sb_size={sb_size1}")
    return True


def main():
    apk_path = os.path.join(os.path.dirname(__file__), "apk_work", "avito-patched.apk")
    if not os.path.exists(apk_path):
        print(f"[-] Not found: {apk_path}")
        sys.exit(1)

    sign_apk_v2(apk_path)
    print("[*] Done! APK has v2 signature.")


if __name__ == "__main__":
    main()
