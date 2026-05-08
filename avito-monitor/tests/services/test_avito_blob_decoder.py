"""Tests for app.services.avito_blob_decoder.

Three blobs were captured live from avito.ru in Chrome DevTools (2026-05-08)
and cross-checked against a 50-model iPhone catalog the user pulled from the
same UI session. They are the contract for this decoder.
"""
from __future__ import annotations

import pytest

from app.services.avito_blob_decoder import (
    BlobDecodeError,
    decode_blob,
    decode_url,
    extract_blob_from_url,
)


# ── Known good blobs ─────────────────────────────────────────────────────────

# (param_id, value) for "Тип товара" = "Мобильные телефоны". Implicit in every
# phone-category blob — Avito always includes it as the deepest-fallback.
TYPE_PHONE = (110680, 458500)

# Brand "Apple".
BRAND_APPLE = (110618, 469735)

# Model "iPhone 13".
MODEL_IPHONE_13 = (110617, 1642358)


@pytest.mark.parametrize(
    "blob, expected_pairs",
    [
        # /astrahan/telefony/mobile-...
        ("ASgBAgICAUSwwQ2I_Dc", [TYPE_PHONE]),
        # /astrahan/telefony/mobilnye_telefony/apple-...
        ("ASgBAgICAkS0wA3OqzmwwQ2I_Dc", [BRAND_APPLE, TYPE_PHONE]),
        # /astrahan/telefony/mobilnye_telefony/apple/iphone_13-...
        (
            "ASgBAgICA0SywA3svcgBtMANzqs5sMENiPw3",
            [MODEL_IPHONE_13, BRAND_APPLE, TYPE_PHONE],
        ),
    ],
)
def test_decode_blob_known_urls(blob, expected_pairs):
    result = decode_blob(blob)
    assert list(result.pairs) == expected_pairs


def test_decoded_blob_as_dict():
    result = decode_blob("ASgBAgICA0SywA3svcgBtMANzqs5sMENiPw3")
    d = result.as_dict()
    assert d == {
        110617: 1642358,  # model
        110618: 469735,   # brand
        110680: 458500,   # type
    }


# ── Error paths ──────────────────────────────────────────────────────────────


def test_decode_blob_empty_raises():
    with pytest.raises(BlobDecodeError, match="empty"):
        decode_blob("")


def test_decode_blob_garbage_base64_raises():
    with pytest.raises(BlobDecodeError, match="base64 decode failed"):
        decode_blob("!!!not-base64!!!")


def test_decode_blob_truncated_header_raises():
    # Decodes to 4 bytes — too short for our 8-byte minimum header.
    with pytest.raises(BlobDecodeError, match="too short"):
        decode_blob("AAAAAA")


def test_decode_blob_wrong_header_raises():
    # 8 bytes of zeros — passes length check but fails prefix check.
    import base64

    payload = base64.urlsafe_b64encode(b"\x00" * 8).decode().rstrip("=")
    with pytest.raises(BlobDecodeError, match="unexpected header"):
        decode_blob(payload)


# ── URL helpers ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url, expected_blob",
    [
        (
            "https://www.avito.ru/astrahan/telefony/mobile-ASgBAgICAUSwwQ2I_Dc",
            "ASgBAgICAUSwwQ2I_Dc",
        ),
        (
            "https://www.avito.ru/astrahan/telefony/mobilnye_telefony/apple-ASgBAgICAkS0wA3OqzmwwQ2I_Dc?context=H4sI",
            "ASgBAgICAkS0wA3OqzmwwQ2I_Dc",
        ),
        (
            "https://www.avito.ru/astrahan/telefony/mobilnye_telefony/apple/iphone_13-ASgBAgICA0SywA3svcgBtMANzqs5sMENiPw3?context=xxx&localPriority=0",
            "ASgBAgICA0SywA3svcgBtMANzqs5sMENiPw3",
        ),
    ],
)
def test_extract_blob_from_url_strips_query_and_segments(url, expected_blob):
    assert extract_blob_from_url(url) == expected_blob


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://www.avito.ru/astrahan/telefony",  # no blob, no `-`
        "https://www.avito.ru/astrahan/telefony/iphone_12_pro_max",  # only lowercase model slug
        "https://www.avito.ru/astrahan/telefony/short-ab",  # too short to be a blob
    ],
)
def test_extract_blob_from_url_returns_none_when_no_blob(url):
    assert extract_blob_from_url(url) is None


def test_decode_url_end_to_end():
    url = "https://www.avito.ru/astrahan/telefony/mobilnye_telefony/apple/iphone_13-ASgBAgICA0SywA3svcgBtMANzqs5sMENiPw3?localPriority=0"
    result = decode_url(url)
    assert result is not None
    assert result.as_dict() == {110617: 1642358, 110618: 469735, 110680: 458500}


def test_decode_url_returns_none_for_blob_less_url():
    assert decode_url("https://www.avito.ru/astrahan/telefony") is None
