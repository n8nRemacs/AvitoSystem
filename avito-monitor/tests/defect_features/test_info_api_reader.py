"""Phase 2.1 Task 8: info_api reader tests."""
from __future__ import annotations

import pytest

from app.services.defect_features.info_api_reader import read_info_api_features


def test_reads_memory_gb_from_param():
    params = {"Встроенная память": "128 ГБ"}
    result = read_info_api_features(params)
    assert result["memory_gb"] == {"gb": 128}


def test_reads_memory_gb_handles_no_unit():
    params = {"Встроенная память": "256"}
    result = read_info_api_features(params)
    assert result["memory_gb"] == {"gb": 256}


def test_memory_gb_missing_returns_null():
    params = {}
    result = read_info_api_features(params)
    assert result["memory_gb"] is None


def test_memory_gb_unparseable_returns_null():
    params = {"Встроенная память": "не указано"}
    result = read_info_api_features(params)
    assert result["memory_gb"] is None


def test_reads_color():
    params = {"Цвет": "Чёрный"}
    result = read_info_api_features(params)
    assert result["color"] == {"text": "Чёрный"}


def test_color_missing_returns_null():
    params = {}
    result = read_info_api_features(params)
    assert result["color"] is None


def test_reads_vendor_model_concat():
    params = {"Производитель": "Apple", "Модель": "iPhone 12 Pro Max"}
    result = read_info_api_features(params)
    assert result["vendor_model"] == {"text": "Apple iPhone 12 Pro Max"}


def test_vendor_model_only_one_field_returns_null():
    """Phase 2.1: both vendor and model must be present."""
    result = read_info_api_features({"Производитель": "Apple"})
    assert result["vendor_model"] is None


def test_full_listing_parameters_reads_all_three():
    params = {
        "Встроенная память": "256 ГБ",
        "Цвет": "Графит",
        "Производитель": "Apple",
        "Модель": "iPhone 13 Pro Max",
        "Состояние": "Б/у",  # ignored — not info_api
    }
    result = read_info_api_features(params)
    assert result["memory_gb"] == {"gb": 256}
    assert result["color"] == {"text": "Графит"}
    assert result["vendor_model"] == {"text": "Apple iPhone 13 Pro Max"}
