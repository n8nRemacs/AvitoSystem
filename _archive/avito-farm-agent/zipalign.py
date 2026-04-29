"""Pure Python zipalign — align uncompressed entries to 4-byte boundaries.

Equivalent to: zipalign -f 4 input.apk output.apk
"""

import struct
import sys
import os


def zipalign(input_path, output_path, alignment=4):
    """Align uncompressed entries in a ZIP/APK to the specified boundary."""
    with open(input_path, "rb") as f:
        data = f.read()

    # Find End of Central Directory
    eocd_pos = data.rfind(b"PK\x05\x06")
    if eocd_pos == -1:
        raise ValueError("Not a valid ZIP file")

    cd_offset = struct.unpack_from("<I", data, eocd_pos + 16)[0]
    cd_size = struct.unpack_from("<I", data, eocd_pos + 12)[0]
    num_entries = struct.unpack_from("<H", data, eocd_pos + 10)[0]

    # Parse central directory entries
    entries = []
    pos = cd_offset
    for _ in range(num_entries):
        if data[pos:pos+4] != b"PK\x01\x02":
            raise ValueError(f"Bad central dir entry at {pos}")

        compress = struct.unpack_from("<H", data, pos + 10)[0]
        fname_len = struct.unpack_from("<H", data, pos + 28)[0]
        extra_len = struct.unpack_from("<H", data, pos + 30)[0]
        comment_len = struct.unpack_from("<H", data, pos + 32)[0]
        local_offset = struct.unpack_from("<I", data, pos + 42)[0]
        fname = data[pos+46:pos+46+fname_len]

        entries.append({
            "cd_offset": pos,
            "cd_size": 46 + fname_len + extra_len + comment_len,
            "local_offset": local_offset,
            "compress": compress,
            "fname": fname,
            "fname_len": fname_len,
        })
        pos += 46 + fname_len + extra_len + comment_len

    # Process local file headers and build aligned output
    out_parts = []
    new_local_offsets = {}
    current_offset = 0

    for entry in entries:
        lo = entry["local_offset"]
        if data[lo:lo+4] != b"PK\x03\x04":
            raise ValueError(f"Bad local header at {lo}")

        lfname_len = struct.unpack_from("<H", data, lo + 26)[0]
        lextra_len = struct.unpack_from("<H", data, lo + 28)[0]
        compress = struct.unpack_from("<H", data, lo + 8)[0]
        comp_size = struct.unpack_from("<I", data, lo + 18)[0]

        header_size = 30 + lfname_len  # without extra
        data_start = lo + 30 + lfname_len + lextra_len
        file_data = data[data_start:data_start + comp_size]

        # For uncompressed entries, align data to 4-byte boundary
        if compress == 0:  # STORED
            # Calculate needed padding
            needed_extra = 0
            data_offset = current_offset + header_size
            remainder = data_offset % alignment
            if remainder != 0:
                needed_extra = alignment - remainder
        else:
            needed_extra = lextra_len  # keep original extra for compressed

        new_local_offsets[entry["cd_offset"]] = current_offset

        if compress == 0:
            # Write header with adjusted extra field (padding bytes)
            header = data[lo:lo+28]  # up to extra_len field
            header = header[:26] + struct.pack("<H", lfname_len) + struct.pack("<H", needed_extra)
            out_parts.append(data[lo:lo+4])  # signature
            out_parts.append(data[lo+4:lo+26])  # fields
            out_parts.append(struct.pack("<H", lfname_len))
            out_parts.append(struct.pack("<H", needed_extra))
            out_parts.append(data[lo+30:lo+30+lfname_len])  # filename
            out_parts.append(b"\x00" * needed_extra)  # padding
            out_parts.append(file_data)
            current_offset += 30 + lfname_len + needed_extra + comp_size
        else:
            # Keep as-is for compressed entries
            local_entry = data[lo:data_start + comp_size]
            out_parts.append(local_entry)
            current_offset += len(local_entry)

        # Check for data descriptor
        dd_pos = data_start + comp_size
        if dd_pos < len(data) and data[dd_pos:dd_pos+4] == b"PK\x07\x08":
            dd = data[dd_pos:dd_pos+16]
            out_parts.append(dd)
            current_offset += 16

    # Write central directory with updated offsets
    new_cd_offset = current_offset
    for entry in entries:
        cd_data = bytearray(data[entry["cd_offset"]:entry["cd_offset"]+entry["cd_size"]])
        new_offset = new_local_offsets[entry["cd_offset"]]
        struct.pack_into("<I", cd_data, 42, new_offset)
        out_parts.append(bytes(cd_data))
        current_offset += len(cd_data)

    # Write EOCD with updated CD offset
    eocd = bytearray(data[eocd_pos:eocd_pos+22])
    struct.pack_into("<I", eocd, 16, new_cd_offset)
    # Update CD size
    new_cd_size = current_offset - new_cd_offset
    struct.pack_into("<I", eocd, 12, new_cd_size)
    out_parts.append(bytes(eocd))

    # Write output
    with open(output_path, "wb") as f:
        for part in out_parts:
            f.write(part)

    print(f"[*] Aligned: {output_path} ({os.path.getsize(output_path)} bytes)")


def main():
    if len(sys.argv) < 2:
        apk = os.path.join(os.path.dirname(__file__), "apk_work", "avito-patched.apk")
    else:
        apk = sys.argv[1]

    aligned = apk.replace(".apk", "-aligned.apk")
    zipalign(apk, aligned)

    # Replace original with aligned
    os.replace(aligned, apk)
    print(f"[*] Replaced {apk}")


if __name__ == "__main__":
    main()
