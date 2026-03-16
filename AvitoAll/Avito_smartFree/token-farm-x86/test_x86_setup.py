"""
Test script for x86 development setup

This script tests basic functionality on x86 containers:
- ADB connection
- Screen size detection
- UI automation (tap, swipe)
- SharedPreferences read/write
- Active refresh logic (without real Avito)

Run with: python test_x86_setup.py
"""

import asyncio
import sys
from datetime import datetime
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, "../token-farm")

from avito_prefs_parser import AvitoSession, parse_session_xml, generate_session_xml


class SimpleADBController:
    """Simplified ADB controller for testing"""

    def __init__(self, host: str = "localhost", port: int = 5555):
        self.host = host
        self.port = port
        self._connected = False

    async def connect(self) -> bool:
        """Connect to ADB"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "connect", f"{self.host}:{self.port}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            self._connected = b"connected" in stdout.lower()
            return self._connected

        except Exception as e:
            print(f"ADB connect error: {e}")
            return False

    async def shell(self, command: str) -> str:
        """Execute shell command"""
        if not self._connected:
            await self.connect()

        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", f"{self.host}:{self.port}", "shell", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            return stdout.decode("utf-8").strip()

        except Exception as e:
            print(f"ADB shell error: {e}")
            return ""

    async def get_screen_size(self) -> tuple[int, int]:
        """Get screen resolution"""
        output = await self.shell("wm size")
        if "Physical size:" in output:
            size_str = output.split("Physical size:")[1].strip()
            width, height = size_str.split("x")
            return int(width), int(height)
        return 1080, 2400

    async def tap(self, x: int, y: int) -> bool:
        """Tap at coordinates"""
        await self.shell(f"input tap {x} {y}")
        return True

    async def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """Swipe from one point to another"""
        await self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")
        return True

    async def get_prop(self, prop: str) -> str:
        """Get system property"""
        return await self.shell(f"getprop {prop}")


async def test_adb_connection(port: int = 5555) -> bool:
    """Test 1: ADB Connection"""
    print(f"\n{'='*60}")
    print(f"Test 1: ADB Connection (port {port})")
    print('='*60)

    adb = SimpleADBController(host="localhost", port=port)

    print(f"Connecting to localhost:{port}...")
    connected = await adb.connect()

    if connected:
        print("✅ Connected successfully!")

        # Get device info
        manufacturer = await adb.get_prop("ro.product.manufacturer")
        model = await adb.get_prop("ro.product.model")
        android = await adb.get_prop("ro.build.version.release")

        print(f"\nDevice Info:")
        print(f"  Manufacturer: {manufacturer}")
        print(f"  Model: {model}")
        print(f"  Android: {android}")

        return True
    else:
        print("❌ Connection failed!")
        print("\nTroubleshooting:")
        print("  1. Check if container is running: docker-compose ps")
        print("  2. Check logs: docker-compose logs redroid-x86-1")
        print("  3. Try: adb kill-server && adb start-server")
        return False


async def test_screen_interaction(port: int = 5555) -> bool:
    """Test 2: Screen Interaction"""
    print(f"\n{'='*60}")
    print(f"Test 2: Screen Interaction")
    print('='*60)

    adb = SimpleADBController(host="localhost", port=port)
    await adb.connect()

    # Get screen size
    width, height = await adb.get_screen_size()
    print(f"Screen size: {width}x{height}")

    # Test tap
    print("\nTesting tap at center...")
    center_x, center_y = width // 2, height // 2
    await adb.tap(center_x, center_y)
    print(f"✅ Tapped at ({center_x}, {center_y})")

    # Test swipe
    print("\nTesting swipe (scroll down)...")
    x = width // 2
    y_start = height * 2 // 3
    y_end = height // 3
    await adb.swipe(x, y_start, x, y_end, 300)
    print(f"✅ Swiped from ({x}, {y_start}) to ({x}, {y_end})")

    return True


async def test_shared_prefs_parser() -> bool:
    """Test 3: SharedPreferences Parser"""
    print(f"\n{'='*60}")
    print(f"Test 3: SharedPreferences Parser")
    print('='*60)

    # Create test session
    session = AvitoSession(
        session_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.signature",
        refresh_token="refresh_test_123",
        expires_at=int(datetime.now().timestamp()) + 86400,  # 24h from now
        device_id="test_device_123",
        user_hash="test_user_hash",
        fingerprint="A2.test_fingerprint_123",
        user_id=123456789,
        is_authenticated=True
    )

    print(f"Created test session:")
    print(f"  Token: {session.session_token[:50]}...")
    print(f"  Device ID: {session.device_id}")
    print(f"  Expires in: {session.time_until_expiry()}s")
    print(f"  Is expired: {session.is_expired()}")

    # Generate XML
    print("\nGenerating XML...")
    xml = generate_session_xml(session)
    print(f"✅ Generated {len(xml)} bytes of XML")

    # Parse back
    print("\nParsing XML back...")
    parsed = parse_session_xml(xml)

    # Verify
    assert parsed.session_token == session.session_token, "Token mismatch!"
    assert parsed.device_id == session.device_id, "Device ID mismatch!"
    assert parsed.expires_at == session.expires_at, "Expiry mismatch!"

    print("✅ Roundtrip successful! All fields match.")

    return True


async def test_mock_refresh_logic(port: int = 5555) -> bool:
    """Test 4: Mock Active Refresh Logic"""
    print(f"\n{'='*60}")
    print(f"Test 4: Mock Active Refresh Logic")
    print('='*60)

    print("This simulates the active refresh algorithm without real Avito app")

    adb = SimpleADBController(host="localhost", port=port)
    await adb.connect()

    # Create mock session
    session = AvitoSession(
        session_token="mock_token",
        device_id="mock_device",
        expires_at=int(datetime.now().timestamp()) + 60  # Expires in 60s
    )

    print(f"\nMock session expires in: {session.time_until_expiry()}s")

    # Simulate 3 rounds of user activity
    print("\nSimulating user activity (3 rounds):")

    for round_num in range(1, 4):
        print(f"\n  Round {round_num}:")

        # Action 1: Scroll
        print("    - Scrolling feed...")
        width, height = await adb.get_screen_size()
        await adb.swipe(width//2, height*2//3, width//2, height//3, 300)

        await asyncio.sleep(1)

        # Action 2: Tap messages
        print("    - Opening messages...")
        await adb.tap(int(width * 0.27), int(height * 0.97))

        await asyncio.sleep(2)

        # Check for "new token" (mock)
        print(f"    - Checking for token refresh... (mock)")

        await asyncio.sleep(1)

    print("\n✅ Mock refresh simulation completed!")
    print("\nIn real scenario:")
    print("  - Avito app would be running")
    print("  - Token would auto-refresh after expiration")
    print("  - We'd detect new token via SharedPreferences")
    print("  - Save to database and stop app")

    return True


async def test_all_containers() -> None:
    """Test all available containers"""
    print(f"\n{'='*60}")
    print(f"Testing All Containers")
    print('='*60)

    containers = [
        (5555, "redroid-x86-1"),
        (5556, "redroid-x86-2"),
        (5557, "redroid-x86-3"),
    ]

    results = []

    for port, name in containers:
        print(f"\nTesting {name} (port {port})...")
        adb = SimpleADBController(host="localhost", port=port)
        connected = await adb.connect()

        if connected:
            model = await adb.get_prop("ro.product.model")
            print(f"  ✅ {name}: {model}")
            results.append((name, True, model))
        else:
            print(f"  ❌ {name}: Not available")
            results.append((name, False, None))

    print(f"\n{'='*60}")
    print("Summary:")
    print('='*60)
    for name, connected, model in results:
        status = "✅" if connected else "❌"
        print(f"{status} {name}: {model if model else 'Offline'}")


async def main():
    """Run all tests"""
    print("="*60)
    print("Token Farm x86 Development Setup Tests")
    print("="*60)

    print("\nThese tests verify that x86 development environment is working.")
    print("Note: This does NOT test real Avito integration (requires ARM)")

    # Test 1: ADB Connection
    success = await test_adb_connection(port=5555)
    if not success:
        print("\n❌ ADB connection failed. Fix this before continuing.")
        return

    # Test 2: Screen Interaction
    await test_screen_interaction(port=5555)

    # Test 3: Parser
    await test_shared_prefs_parser()

    # Test 4: Mock Refresh
    await test_mock_refresh_logic(port=5555)

    # Bonus: Test all containers
    await test_all_containers()

    print("\n" + "="*60)
    print("✅ All tests completed!")
    print("="*60)

    print("\nNext steps:")
    print("  1. Run unit tests: pytest test_avito_prefs_parser.py -v")
    print("  2. Test UI automation manually: adb shell input tap 500 1000")
    print("  3. Install test APK: adb install test.apk")
    print("  4. When ready, migrate to ARM server")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTests cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
