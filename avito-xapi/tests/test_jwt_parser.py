import json
import base64
import time
import pytest
from src.workers.jwt_parser import (
    decode_jwt_payload, decode_jwt_header, get_expiry,
    is_expired, time_left, get_user_id,
)


def _make_jwt(payload: dict, header: dict | None = None) -> str:
    """Create a test JWT (not signed, just for parsing)."""
    if header is None:
        header = {"alg": "HS512", "typ": "JWT"}
    h = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{h}.{p}.fake_signature"


class TestDecodeJwtPayload:
    def test_valid_jwt(self):
        token = _make_jwt({"user_id": 12345, "exp": 9999999999})
        payload = decode_jwt_payload(token)
        assert payload["user_id"] == 12345
        assert payload["exp"] == 9999999999

    def test_invalid_jwt_single_part(self):
        with pytest.raises(ValueError, match="at least 2 parts"):
            decode_jwt_payload("not-a-jwt")

    def test_empty_string(self):
        with pytest.raises(ValueError):
            decode_jwt_payload("")

    def test_payload_with_unicode(self):
        token = _make_jwt({"name": "Test User", "city": "Moscow"})
        payload = decode_jwt_payload(token)
        assert payload["city"] == "Moscow"


class TestDecodeJwtHeader:
    def test_valid_header(self):
        token = _make_jwt({"user_id": 1}, header={"alg": "HS512", "typ": "JWT"})
        header = decode_jwt_header(token)
        assert header["alg"] == "HS512"
        assert header["typ"] == "JWT"


class TestGetExpiry:
    def test_with_exp(self):
        token = _make_jwt({"exp": 1707086400})
        assert get_expiry(token) == 1707086400

    def test_without_exp(self):
        token = _make_jwt({"user_id": 1})
        assert get_expiry(token) is None

    def test_invalid_token(self):
        assert get_expiry("invalid") is None


class TestIsExpired:
    def test_not_expired(self):
        token = _make_jwt({"exp": int(time.time()) + 3600})
        assert is_expired(token) is False

    def test_expired(self):
        token = _make_jwt({"exp": int(time.time()) - 3600})
        assert is_expired(token) is True

    def test_no_exp(self):
        token = _make_jwt({"user_id": 1})
        assert is_expired(token) is True

    def test_invalid(self):
        assert is_expired("bad") is True


class TestTimeLeft:
    def test_positive(self):
        future = int(time.time()) + 7200
        token = _make_jwt({"exp": future})
        left = time_left(token)
        assert 7100 < left <= 7200

    def test_negative(self):
        past = int(time.time()) - 600
        token = _make_jwt({"exp": past})
        left = time_left(token)
        assert left < 0

    def test_no_exp(self):
        token = _make_jwt({"user_id": 1})
        assert time_left(token) == -1


class TestGetUserId:
    def test_user_id_field(self):
        token = _make_jwt({"user_id": 99999999})
        assert get_user_id(token) == 99999999

    def test_sub_field(self):
        token = _make_jwt({"sub": 88888888})
        assert get_user_id(token) == 88888888

    def test_no_user_id(self):
        token = _make_jwt({"foo": "bar"})
        assert get_user_id(token) is None

    def test_invalid(self):
        assert get_user_id("bad") is None
