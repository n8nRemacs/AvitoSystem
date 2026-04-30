"""Unit tests for the shared reraise_avito_error helper."""
import pytest
from fastapi import HTTPException
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError

from tests.conftest import _curl_error
from src.routers._avito_errors import reraise_avito_error, PROPAGATE


def test_propagate_status_raises_http_exception():
    """A status code in PROPAGATE (e.g. 403) must become an HTTPException with the same code."""
    exc = _curl_error(403)
    with pytest.raises(HTTPException) as exc_info:
        reraise_avito_error(exc)
    assert exc_info.value.status_code == 403
    assert "403" in exc_info.value.detail


def test_response_none_reraises_curl_error():
    """When exc.response is None (network-level failure), the original CurlHTTPError is re-raised."""
    bare_exc = CurlHTTPError("connection reset", 0, None)
    with pytest.raises(CurlHTTPError) as exc_info:
        reraise_avito_error(bare_exc)
    assert exc_info.value is bare_exc


def test_non_propagate_status_reraises_curl_error():
    """A status outside PROPAGATE (e.g. 500) must re-raise the original CurlHTTPError, not wrap it."""
    exc = _curl_error(500)
    with pytest.raises(CurlHTTPError) as exc_info:
        reraise_avito_error(exc)
    assert exc_info.value is exc
