"""
Unit tests for Avito SharedPreferences parser
"""

import pytest
from datetime import datetime, timedelta
from avito_prefs_parser import (
    AvitoSession,
    AvitoPrefsParser,
    parse_session_xml,
    generate_session_xml,
    parse_prefs_file
)


# Sample XML fixtures
SAMPLE_SESSION_XML = """<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="session_token">eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1IjoxMjM0NTY3ODksImQiOiJkZXZpY2VfaWRfMTIzIiwiZXhwIjoxNjQwMDAwMDAwfQ.signature</string>
    <string name="refresh_token">refresh_abc123</string>
    <long name="expires_at" value="1640000000" />
    <string name="device_id">device_id_123</string>
    <string name="user_hash">user_hash_abc</string>
    <string name="fingerprint">A2.abc123def456</string>
    <int name="user_id" value="123456789" />
    <boolean name="is_authenticated" value="true" />
    <string name="cookies">{"cookie1": "value1"}</string>
</map>"""

MINIMAL_SESSION_XML = """<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="session_token">eyJ.token.here</string>
</map>"""

COMPLEX_PREFS_XML = """<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="string_value">hello world</string>
    <int name="int_value" value="42" />
    <long name="long_value" value="9876543210" />
    <float name="float_value" value="3.14159" />
    <boolean name="bool_true" value="true" />
    <boolean name="bool_false" value="false" />
    <set name="string_set">
        <string>item1</string>
        <string>item2</string>
        <string>item3</string>
    </set>
</map>"""


class TestAvitoSession:
    """Test AvitoSession dataclass"""

    def test_session_creation(self):
        """Test creating session object"""
        session = AvitoSession(
            session_token="token123",
            device_id="device456",
            expires_at=int(datetime.now().timestamp()) + 3600
        )

        assert session.session_token == "token123"
        assert session.device_id == "device456"
        assert not session.is_expired()

    def test_session_to_dict(self):
        """Test converting session to dict"""
        session = AvitoSession(
            session_token="token123",
            device_id="device456"
        )

        data = session.to_dict()
        assert "session_token" in data
        assert "device_id" in data
        # None values should be excluded
        assert "refresh_token" not in data

    def test_is_expired(self):
        """Test expiry checking"""
        # Expired token
        expired = AvitoSession(
            session_token="token",
            expires_at=int(datetime.now().timestamp()) - 3600
        )
        assert expired.is_expired()

        # Valid token
        valid = AvitoSession(
            session_token="token",
            expires_at=int(datetime.now().timestamp()) + 3600
        )
        assert not valid.is_expired()

    def test_time_until_expiry(self):
        """Test time until expiry calculation"""
        future = int(datetime.now().timestamp()) + 3600
        session = AvitoSession(
            session_token="token",
            expires_at=future
        )

        time_left = session.time_until_expiry()
        assert 3500 < time_left <= 3600  # Allow some execution time


class TestAvitoPrefsParser:
    """Test AvitoPrefsParser class"""

    def test_parse_full_session(self):
        """Test parsing full session XML"""
        data = AvitoPrefsParser.parse(SAMPLE_SESSION_XML)

        assert data["session_token"].startswith("eyJ")
        assert data["refresh_token"] == "refresh_abc123"
        assert data["expires_at"] == 1640000000
        assert data["device_id"] == "device_id_123"
        assert data["user_hash"] == "user_hash_abc"
        assert data["fingerprint"] == "A2.abc123def456"
        assert data["user_id"] == 123456789
        assert data["is_authenticated"] is True
        assert data["cookies"] == '{"cookie1": "value1"}'

    def test_parse_minimal_session(self):
        """Test parsing minimal session XML"""
        data = AvitoPrefsParser.parse(MINIMAL_SESSION_XML)

        assert "session_token" in data
        assert data["session_token"] == "eyJ.token.here"

    def test_parse_complex_types(self):
        """Test parsing all supported types"""
        data = AvitoPrefsParser.parse(COMPLEX_PREFS_XML)

        assert data["string_value"] == "hello world"
        assert data["int_value"] == 42
        assert data["long_value"] == 9876543210
        assert abs(data["float_value"] - 3.14159) < 0.0001
        assert data["bool_true"] is True
        assert data["bool_false"] is False
        assert data["string_set"] == ["item1", "item2", "item3"]

    def test_parse_session_object(self):
        """Test parsing XML into AvitoSession object"""
        session = AvitoPrefsParser.parse_session(SAMPLE_SESSION_XML)

        assert isinstance(session, AvitoSession)
        assert session.session_token.startswith("eyJ")
        assert session.refresh_token == "refresh_abc123"
        assert session.expires_at == 1640000000
        assert session.device_id == "device_id_123"
        assert session.fingerprint == "A2.abc123def456"
        assert session.user_id == 123456789

    def test_parse_invalid_xml(self):
        """Test parsing invalid XML"""
        with pytest.raises(ValueError):
            AvitoPrefsParser.parse("not valid xml")

    def test_parse_invalid_root(self):
        """Test parsing XML with wrong root tag"""
        invalid_xml = '<?xml version="1.0"?><root></root>'
        with pytest.raises(ValueError, match="Invalid root tag"):
            AvitoPrefsParser.parse(invalid_xml)

    def test_generate_simple(self):
        """Test generating simple XML"""
        data = {
            "session_token": "token123",
            "device_id": "device456"
        }

        xml = AvitoPrefsParser.generate(data)

        assert '<?xml version="1.0"' in xml
        assert '<map>' in xml
        assert 'name="session_token"' in xml
        assert 'token123' in xml
        assert 'name="device_id"' in xml
        assert 'device456' in xml

    def test_generate_all_types(self):
        """Test generating XML with all types"""
        data = {
            "string_val": "hello",
            "int_val": 42,
            "float_val": 3.14,
            "bool_val": True,
            "list_val": ["a", "b", "c"]
        }

        xml = AvitoPrefsParser.generate(data)

        assert 'name="string_val"' in xml
        assert 'hello' in xml
        assert 'name="int_val"' in xml
        assert 'value="42"' in xml
        assert 'name="bool_val"' in xml
        assert 'value="true"' in xml

    def test_generate_session_xml(self):
        """Test generating session XML from AvitoSession"""
        session = AvitoSession(
            session_token="eyJ.token.here",
            refresh_token="refresh123",
            expires_at=1640000000,
            device_id="device123",
            user_hash="hash123",
            fingerprint="A2.fingerprint",
            user_id=999,
            is_authenticated=True
        )

        xml = AvitoPrefsParser.generate_session_xml(session)

        assert '<?xml version="1.0"' in xml
        assert 'name="session_token"' in xml
        assert 'eyJ.token.here' in xml
        assert 'name="expires_at"' in xml
        assert '1640000000' in xml
        assert 'name="fingerprint"' in xml
        assert 'A2.fingerprint' in xml

    def test_roundtrip(self):
        """Test parse -> generate -> parse roundtrip"""
        # Original session
        original = AvitoSession(
            session_token="token123",
            refresh_token="refresh123",
            expires_at=1640000000,
            device_id="device123",
            fingerprint="A2.abc"
        )

        # Generate XML
        xml = generate_session_xml(original)

        # Parse back
        parsed = parse_session_xml(xml)

        # Compare
        assert parsed.session_token == original.session_token
        assert parsed.refresh_token == original.refresh_token
        assert parsed.expires_at == original.expires_at
        assert parsed.device_id == original.device_id
        assert parsed.fingerprint == original.fingerprint


class TestConvenienceFunctions:
    """Test convenience functions"""

    def test_parse_session_xml_function(self):
        """Test parse_session_xml convenience function"""
        session = parse_session_xml(SAMPLE_SESSION_XML)

        assert isinstance(session, AvitoSession)
        assert session.session_token.startswith("eyJ")

    def test_generate_session_xml_function(self):
        """Test generate_session_xml convenience function"""
        session = AvitoSession(
            session_token="token123",
            device_id="device456"
        )

        xml = generate_session_xml(session)

        assert '<?xml version="1.0"' in xml
        assert 'token123' in xml

    def test_parse_prefs_file_function(self):
        """Test parse_prefs_file convenience function"""
        data = parse_prefs_file(COMPLEX_PREFS_XML)

        assert "string_value" in data
        assert "int_value" in data
        assert data["bool_true"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
