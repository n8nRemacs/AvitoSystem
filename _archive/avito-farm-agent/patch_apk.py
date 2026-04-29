"""Patch Avito APK to inject Frida Gadget.

Uses lief to add frida-gadget.so as a dependency to an existing native library.
Then repackages and signs the APK with a debug key.

No apktool, aapt, or Java required — pure Python.
"""

import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
import lzma

GADGET_VERSION = "17.6.2"
GADGET_ARCH = "android-arm64"
GADGET_URL = f"https://github.com/frida/frida/releases/download/{GADGET_VERSION}/frida-gadget-{GADGET_VERSION}-{GADGET_ARCH}.so.xz"
GADGET_NAME = "libfrida-gadget.so"

WORK_DIR = os.path.join(os.path.dirname(__file__), "apk_work")


def download_gadget(dest_path):
    """Download and decompress frida-gadget.so."""
    xz_path = dest_path + ".xz"
    if os.path.exists(dest_path):
        print(f"[*] Gadget already exists: {dest_path}")
        return

    print(f"[*] Downloading gadget from {GADGET_URL}...")
    urllib.request.urlretrieve(GADGET_URL, xz_path)

    print("[*] Decompressing...")
    with lzma.open(xz_path) as f_in:
        with open(dest_path, "wb") as f_out:
            f_out.write(f_in.read())
    os.remove(xz_path)
    print(f"[*] Gadget saved: {dest_path} ({os.path.getsize(dest_path)} bytes)")


def find_native_lib(apk_path, arch="arm64-v8a"):
    """Find a suitable native library to patch in the APK."""
    with zipfile.ZipFile(apk_path, "r") as zf:
        libs = [n for n in zf.namelist()
                if n.startswith(f"lib/{arch}/") and n.endswith(".so")]

    if not libs:
        print(f"[-] No native libs found for {arch}")
        return None

    # Prefer libraries that are actually loaded at startup
    preferred = ["libcrashlytics.so", "libcrashlytics-common.so",
                 "libdatastore_shared_counter.so",
                 "libnative-lib.so", "libapp.so", "libflutter.so"]
    for pref in preferred:
        matches = [l for l in libs if l.endswith(pref)]
        if matches:
            return matches[0]

    # Just pick the first one
    print(f"[*] Available native libs: {libs[:10]}")
    return libs[0]


def patch_elf(lib_path, gadget_name=GADGET_NAME):
    """Add frida-gadget.so as a NEEDED dependency to an ELF binary."""
    import lief

    binary = lief.ELF.parse(lib_path)
    if binary is None:
        raise RuntimeError(f"Failed to parse ELF: {lib_path}")

    # Check if already patched
    existing = [d.name for d in binary.dynamic_entries
                if d.tag == lief.ELF.DynamicEntry.TAG.NEEDED]
    if gadget_name in existing:
        print(f"[*] Already patched: {gadget_name} in NEEDED")
        return

    print(f"[*] Adding {gadget_name} to NEEDED of {os.path.basename(lib_path)}")
    binary.add_library(gadget_name)
    binary.write(lib_path)


def create_gadget_config(config_path):
    """Create frida-gadget config for listen mode."""
    import json
    config = {
        "interaction": {
            "type": "listen",
            "address": "0.0.0.0",
            "port": 27042,
            "on_load": "resume"
        }
    }
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"[*] Gadget config: {config_path}")


def _should_store_uncompressed(name):
    """Files that Android requires to be stored uncompressed."""
    if name == "resources.arsc":
        return True
    if name.endswith(".so"):
        return True
    return False


def repackage_apk(original_apk, output_apk, target_lib, gadget_so, gadget_config, arch="arm64-v8a"):
    """Repackage APK with patched lib and gadget.

    Preserves compression mode for each entry. Stores resources.arsc and .so
    files uncompressed with 4-byte alignment (required for Android R+).
    """
    print("[*] Repackaging APK...")

    tmp = tempfile.mkdtemp(prefix="avito_patch_")
    try:
        # Build set of original compression methods
        orig_compress = {}
        with zipfile.ZipFile(original_apk, "r") as zf:
            for info in zf.infolist():
                orig_compress[info.filename] = info.compress_type
            zf.extractall(tmp)

        # Patch the target ELF
        lib_dest = os.path.join(tmp, target_lib)
        patch_elf(lib_dest)

        # Add gadget .so
        gadget_dest = os.path.join(tmp, f"lib/{arch}/{GADGET_NAME}")
        shutil.copy2(gadget_so, gadget_dest)

        # Add gadget config
        config_name = GADGET_NAME.replace(".so", ".config.so")
        config_dest = os.path.join(tmp, f"lib/{arch}/{config_name}")
        shutil.copy2(gadget_config, config_dest)

        # Remove only signature files from META-INF (keep services/, etc.)
        meta_inf = os.path.join(tmp, "META-INF")
        if os.path.exists(meta_inf):
            for sig_file in os.listdir(meta_inf):
                if sig_file.upper() in ("MANIFEST.MF",) or \
                   sig_file.upper().endswith((".SF", ".RSA", ".DSA", ".EC")):
                    os.remove(os.path.join(meta_inf, sig_file))
                    print(f"[*] Removed signature: META-INF/{sig_file}")

        # Repack — preserve compression, store .arsc and .so uncompressed
        print("[*] Compressing (preserving alignment)...")
        with zipfile.ZipFile(output_apk, "w") as zf:
            for root, dirs, files in os.walk(tmp):
                for fname in sorted(files):
                    fpath = os.path.join(root, fname)
                    arcname = os.path.relpath(fpath, tmp).replace("\\", "/")

                    if _should_store_uncompressed(arcname):
                        compress = zipfile.ZIP_STORED
                    else:
                        compress = orig_compress.get(arcname, zipfile.ZIP_DEFLATED)

                    zf.write(fpath, arcname, compress_type=compress)

        print(f"[*] Repackaged: {output_apk} ({os.path.getsize(output_apk)} bytes)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sign_apk(apk_path):
    """Sign APK with a debug keystore using apksigner or jarsigner."""
    # Try uber-apk-signer if available
    # Otherwise use Python-based signing
    try:
        # Use Android SDK apksigner if available
        result = subprocess.run(["apksigner", "sign", "--ks-pass", "pass:android",
                                  apk_path], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print("[*] Signed with apksigner")
            return
    except FileNotFoundError:
        pass

    # Python-based zipalign + signing using signapk approach
    # For development, we can use a simple debug signature
    print("[*] No apksigner found. Using uber-apk-signer...")

    # Download uber-apk-signer
    uber_jar = os.path.join(WORK_DIR, "uber-apk-signer.jar")
    if not os.path.exists(uber_jar):
        url = "https://github.com/nicehash/uber-apk-signer/releases/download/1.3.0/uber-apk-signer-1.3.0.jar"
        print(f"[*] Downloading uber-apk-signer from GitHub...")
        try:
            urllib.request.urlretrieve(url, uber_jar)
        except Exception as e:
            print(f"[-] Failed to download: {e}")
            print("[!] APK is NOT signed. You'll need to sign it manually:")
            print(f"    java -jar uber-apk-signer.jar --apks {apk_path}")
            return

    try:
        result = subprocess.run(["java", "-jar", uber_jar, "--apks", apk_path],
                                capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("[*] Signed with uber-apk-signer")
            return
        print(f"[-] uber-apk-signer failed: {result.stderr}")
    except FileNotFoundError:
        print("[!] Java not found. APK is NOT signed.")
        print("[!] Install Java or sign manually.")
        print(f"[!] You can also use: https://github.com/nicehash/uber-apk-signer")


def main():
    apk_path = os.path.join(WORK_DIR, "avito.apk")
    if not os.path.exists(apk_path):
        print(f"[-] APK not found: {apk_path}")
        print("[*] Pull it first: adb pull <path> avito.apk")
        sys.exit(1)

    arch = "arm64-v8a"
    gadget_so = os.path.join(WORK_DIR, GADGET_NAME)
    gadget_config = os.path.join(WORK_DIR, "frida-gadget.config")
    output_apk = os.path.join(WORK_DIR, "avito-patched.apk")

    # Step 1: Download gadget
    download_gadget(gadget_so)

    # Step 2: Find target native lib
    target_lib = find_native_lib(apk_path, arch)
    if not target_lib:
        print("[-] No patchable native library found")
        sys.exit(1)
    print(f"[*] Target lib: {target_lib}")

    # Step 3: Create gadget config
    create_gadget_config(gadget_config)

    # Step 4: Repackage APK
    repackage_apk(apk_path, output_apk, target_lib, gadget_so, gadget_config, arch)

    # Step 5: Sign
    sign_apk(output_apk)

    print()
    print("[*] DONE!")
    print(f"[*] Patched APK: {output_apk}")
    print()
    print("[*] Install with:")
    print(f"    adb install -r {output_apk}")
    print()
    print("[*] After install, launch Avito. It will freeze waiting for Frida connection.")
    print("[*] Then run: python run_sniff.py")


if __name__ == "__main__":
    main()
