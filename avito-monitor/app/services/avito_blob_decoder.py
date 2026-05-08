"""Decode Avito web URL `f=AS...` blob into structured (param_id, value) pairs.

Avito hides structured-search filters in the URL slug as a URL-safe base64
binary blob. Example URL:

    /astrahan/telefony/mobilnye_telefony/apple/iphone_13-ASgBAgICA0SywA3svcgBtMANzqs5sMENiPw3

Everything after the last "-" in the final slug is the blob. Decoding it gives
the same (param_id, value) pairs that the mobile API expects in
``params[<param_id>][0]=<value>``.

Format spec — DOCS/REFERENCE/10-blob-decoder.md.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass


# All known blobs start with this 6-byte constant. Verified empirically on 3
# URLs (all_phones / apple / iphone_13). If a future URL breaks this assumption
# we'll widen the check or skip the header sanity check entirely.
_HEADER_PREFIX = bytes.fromhex("012801020202")
_PAIR_MARKER = 0x44


# A blob token is URL-safe base64 (A-Z, a-z, 0-9, _, -). Real Avito tokens have
# at least one uppercase char (the ``A`` of the version byte ``0x01``) and at
# least 12 chars; pure-lowercase model slugs (e.g. ``iphone_12_pro_max``) must
# not match. Same heuristic as ``url_parser._is_filter_token``.
_BLOB_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{12,}$")


class BlobDecodeError(ValueError):
    """Raised when a blob can't be decoded (bad base64, wrong header, truncated)."""


@dataclass(frozen=True)
class DecodedBlob:
    """Result of decoding one blob.

    ``pairs`` are in the order they appeared in the blob. Avito orders them
    most-specific first (model, then brand, then type) but callers should not
    rely on that — convert to a dict if you need lookup by param_id.
    """
    pairs: tuple[tuple[int, int], ...]

    def as_dict(self) -> dict[int, int]:
        """Flatten to {param_id: value}. Drops ordering, keeps last-write-wins."""
        return {pid: val for pid, val in self.pairs}


def decode_blob(blob: str) -> DecodedBlob:
    """Decode a single ``f=AS...`` blob string to (param_id, value) pairs.

    Raises ``BlobDecodeError`` on malformed input. Empty blob yields zero pairs
    only if it parses to a valid header with count=0, which we haven't seen in
    the wild — for now an empty/missing blob is an error.
    """
    if not blob or not isinstance(blob, str):
        raise BlobDecodeError("blob is empty or not a string")
    pad = "=" * (-len(blob) % 4)
    try:
        data = base64.urlsafe_b64decode(blob + pad)
    except Exception as exc:  # binascii.Error, ValueError
        raise BlobDecodeError(f"base64 decode failed: {exc}") from exc

    # Header sanity: must start with the 6-byte prefix, then count, then 0x44.
    if len(data) < 8:
        raise BlobDecodeError(f"blob too short ({len(data)} bytes, need >=8)")
    if data[:6] != _HEADER_PREFIX:
        raise BlobDecodeError(
            f"unexpected header bytes {data[:6].hex()} "
            f"(expected {_HEADER_PREFIX.hex()})"
        )
    count = data[6]
    if data[7] != _PAIR_MARKER:
        raise BlobDecodeError(
            f"unexpected pair marker 0x{data[7]:02x} "
            f"at offset 7 (expected 0x{_PAIR_MARKER:02x})"
        )

    pairs: list[tuple[int, int]] = []
    i = 8
    for n in range(count):
        try:
            a, i = _read_varint(data, i)
            b, i = _read_varint(data, i)
        except IndexError as exc:
            raise BlobDecodeError(
                f"truncated varint while reading pair {n + 1}/{count} "
                f"at offset {i}"
            ) from exc
        if a % 2 or b % 2:
            # Avito always doubles values (zigzag-style) — odd numbers indicate
            # we mis-parsed varint boundaries.
            raise BlobDecodeError(
                f"pair {n + 1}/{count} produced odd varints "
                f"({a}, {b}) — encoding assumption broken"
            )
        pairs.append((a // 2, b // 2))

    if i != len(data):
        # Trailing garbage means the format has more fields than we modeled.
        # Still return what we got but flag for diagnostics — in practice this
        # would be the next thing to investigate.
        raise BlobDecodeError(
            f"decoded {count} pairs but {len(data) - i} bytes remain at end"
        )

    return DecodedBlob(pairs=tuple(pairs))


def extract_blob_from_url(url: str) -> str | None:
    """Pull the trailing ``f=AS...`` blob out of an Avito search URL.

    Avito puts the blob at the end of the deepest path segment, separated by
    ``-``. Example:

        /astrahan/telefony/mobilnye_telefony/apple/iphone_13-ASgBAg...
                                                            ^^^^^^^^

    Returns ``None`` if no blob-shaped token is present (e.g. plain category
    URL with no filters applied).
    """
    if not url or not isinstance(url, str):
        return None
    # Strip query string and fragment — blobs only live in the path.
    path = url.split("?", 1)[0].split("#", 1)[0]
    segments = [s for s in path.split("/") if s]
    if not segments:
        return None
    last = segments[-1]
    if "-" not in last:
        return None
    candidate = last.rsplit("-", 1)[-1]
    if not _BLOB_TOKEN_RE.match(candidate):
        return None
    if not any(c.isupper() for c in candidate):
        return None
    return candidate


def decode_url(url: str) -> DecodedBlob | None:
    """Convenience: extract blob from URL and decode in one step.

    Returns ``None`` when the URL has no blob (plain category URL). Raises
    ``BlobDecodeError`` when a blob is present but malformed.
    """
    blob = extract_blob_from_url(url)
    if blob is None:
        return None
    return decode_blob(blob)


def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    """Read one LEB128 varint starting at ``buf[i]``. Returns ``(value, new_i)``.

    Raises ``IndexError`` if the buffer ends mid-varint.
    """
    val = 0
    shift = 0
    while True:
        b = buf[i]
        val |= (b & 0x7F) << shift
        i += 1
        if not (b & 0x80):
            return val, i
        shift += 7
