"""
Avito SharedPreferences XML Parser

Parses and generates Android SharedPreferences XML files
for Avito app session data extraction and injection.
"""

import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import json


@dataclass
class AvitoSession:
    """
    Avito session data structure from SharedPreferences

    Corresponds to /data/data/com.avito.android/shared_prefs/session.xml
    """
    session_token: str  # JWT token
    refresh_token: Optional[str] = None
    expires_at: Optional[int] = None  # Unix timestamp
    device_id: Optional[str] = None
    user_hash: Optional[str] = None
    fingerprint: Optional[str] = None  # Header 'f' value
    remote_device_id: Optional[str] = None
    cookies: Optional[str] = None  # JSON string

    # Additional fields
    user_id: Optional[int] = None
    phone: Optional[str] = None
    is_authenticated: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def is_expired(self) -> bool:
        """Check if token is expired"""
        if not self.expires_at:
            return True
        return datetime.now().timestamp() > self.expires_at

    def time_until_expiry(self) -> int:
        """Seconds until token expires (negative if expired)"""
        if not self.expires_at:
            return -1
        return int(self.expires_at - datetime.now().timestamp())


class AvitoPrefsParser:
    """
    Parser for Avito SharedPreferences XML files

    Android SharedPreferences format:
    ```xml
    <?xml version='1.0' encoding='utf-8' standalone='yes' ?>
    <map>
        <string name="session_token">eyJ...</string>
        <long name="expires_at" value="1640000000000" />
        <boolean name="is_authenticated" value="true" />
    </map>
    ```
    """

    # Known Avito SharedPreferences files
    PREFS_FILES = {
        "session": "/data/data/com.avito.android/shared_prefs/session.xml",
        "auth": "/data/data/com.avito.android/shared_prefs/auth.xml",
        "device": "/data/data/com.avito.android/shared_prefs/device.xml",
    }

    @staticmethod
    def parse(xml_content: str) -> Dict[str, Any]:
        """
        Parse SharedPreferences XML content

        Args:
            xml_content: Raw XML string from SharedPreferences file

        Returns:
            Dictionary of key-value pairs
        """
        try:
            root = ET.fromstring(xml_content)

            if root.tag != "map":
                raise ValueError(f"Invalid root tag: {root.tag}, expected 'map'")

            result = {}

            for child in root:
                name = child.get("name")
                if not name:
                    continue

                if child.tag == "string":
                    # String value is in text content
                    result[name] = child.text or ""

                elif child.tag == "int":
                    # Integer value is in 'value' attribute
                    value = child.get("value")
                    result[name] = int(value) if value else 0

                elif child.tag == "long":
                    # Long value is in 'value' attribute
                    value = child.get("value")
                    result[name] = int(value) if value else 0

                elif child.tag == "float":
                    # Float value is in 'value' attribute
                    value = child.get("value")
                    result[name] = float(value) if value else 0.0

                elif child.tag == "boolean":
                    # Boolean value is in 'value' attribute
                    value = child.get("value")
                    result[name] = value == "true"

                elif child.tag == "set":
                    # String set (list of strings)
                    items = []
                    for item in child:
                        if item.text:
                            items.append(item.text)
                    result[name] = items

            return result

        except ET.ParseError as e:
            raise ValueError(f"XML parse error: {e}")

    @staticmethod
    def parse_session(xml_content: str) -> AvitoSession:
        """
        Parse Avito session.xml into AvitoSession object

        Args:
            xml_content: Raw XML string from session.xml

        Returns:
            AvitoSession object with parsed data
        """
        data = AvitoPrefsParser.parse(xml_content)

        # Handle cookies (might be JSON string)
        cookies = data.get("cookies")
        if cookies and isinstance(cookies, str):
            try:
                # Try to parse as JSON to validate
                json.loads(cookies)
            except json.JSONDecodeError:
                cookies = None

        return AvitoSession(
            session_token=data.get("session_token", ""),
            refresh_token=data.get("refresh_token"),
            expires_at=data.get("expires_at"),
            device_id=data.get("device_id"),
            user_hash=data.get("user_hash"),
            fingerprint=data.get("fingerprint") or data.get("f"),
            remote_device_id=data.get("remote_device_id"),
            cookies=cookies,
            user_id=data.get("user_id"),
            phone=data.get("phone"),
            is_authenticated=data.get("is_authenticated", True)
        )

    @staticmethod
    def generate(data: Dict[str, Any]) -> str:
        """
        Generate SharedPreferences XML from dictionary

        Args:
            data: Dictionary of key-value pairs

        Returns:
            XML string in SharedPreferences format
        """
        root = ET.Element("map")

        for key, value in data.items():
            if value is None:
                continue

            if isinstance(value, bool):
                elem = ET.SubElement(root, "boolean")
                elem.set("name", key)
                elem.set("value", "true" if value else "false")

            elif isinstance(value, int):
                # Use long for safety (handles both int and long)
                elem = ET.SubElement(root, "long")
                elem.set("name", key)
                elem.set("value", str(value))

            elif isinstance(value, float):
                elem = ET.SubElement(root, "float")
                elem.set("name", key)
                elem.set("value", str(value))

            elif isinstance(value, list):
                # String set
                elem = ET.SubElement(root, "set")
                elem.set("name", key)
                for item in value:
                    item_elem = ET.SubElement(elem, "string")
                    item_elem.text = str(item)

            else:
                # Default to string
                elem = ET.SubElement(root, "string")
                elem.set("name", key)
                elem.text = str(value)

        # Format with proper XML declaration
        xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")

        # Add XML declaration and format nicely
        formatted = '<?xml version="1.0" encoding="utf-8" standalone="yes" ?>\n'
        formatted += xml_str

        return formatted

    @staticmethod
    def generate_session_xml(session: AvitoSession) -> str:
        """
        Generate session.xml content from AvitoSession object

        Args:
            session: AvitoSession object

        Returns:
            XML string ready to write to session.xml
        """
        data = session.to_dict()
        return AvitoPrefsParser.generate(data)


# Convenience functions
def parse_session_xml(xml_content: str) -> AvitoSession:
    """Parse session.xml content into AvitoSession"""
    return AvitoPrefsParser.parse_session(xml_content)


def generate_session_xml(session: AvitoSession) -> str:
    """Generate session.xml content from AvitoSession"""
    return AvitoPrefsParser.generate_session_xml(session)


def parse_prefs_file(xml_content: str) -> Dict[str, Any]:
    """Parse any SharedPreferences XML file"""
    return AvitoPrefsParser.parse(xml_content)


# Example usage
if __name__ == "__main__":
    # Example XML from Avito app
    example_xml = """<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="session_token">eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1IjoxMjM0NTY3ODksImQiOiJkZXZpY2VfaWRfMTIzIiwiZXhwIjoxNjQwMDAwMDAwfQ.signature</string>
    <string name="refresh_token">refresh_abc123</string>
    <long name="expires_at" value="1640000000" />
    <string name="device_id">device_id_123</string>
    <string name="user_hash">user_hash_abc</string>
    <string name="fingerprint">A2.abc123def456</string>
    <int name="user_id" value="123456789" />
    <boolean name="is_authenticated" value="true" />
</map>"""

    # Parse
    session = parse_session_xml(example_xml)
    print("Parsed session:")
    print(f"  Token: {session.session_token[:50]}...")
    print(f"  Expires at: {session.expires_at}")
    print(f"  Device ID: {session.device_id}")
    print(f"  Fingerprint: {session.fingerprint}")
    print(f"  Is expired: {session.is_expired()}")

    # Generate back
    regenerated_xml = generate_session_xml(session)
    print("\nRegenerated XML:")
    print(regenerated_xml)
