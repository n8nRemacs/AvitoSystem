"""
Token Farm Manager
Orchestrates Redroid containers for token generation and refresh
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID
from dataclasses import dataclass, field
from enum import Enum

try:
    import docker
    from docker.models.containers import Container
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

import httpx

import sys
sys.path.insert(0, "..")
from shared.database import get_db, AccountRepository, SessionRepository
from shared.models import AccountStatus
from shared.config import settings
from shared.utils import (
    parse_jwt, generate_device_id, generate_android_id,
    generate_imei, generate_remote_device_id, generate_user_agent
)

# Import Avito prefs parser
from avito_prefs_parser import (
    AvitoSession, parse_session_xml, generate_session_xml
)

# Import active refresh module
from active_refresh import ActiveTokenRefresh


class ContainerState(str, Enum):
    """Container state enum"""
    IDLE = "idle"
    BUSY = "busy"
    STARTING = "starting"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class ContainerInfo:
    """Container information"""
    id: str
    name: str
    state: ContainerState = ContainerState.IDLE
    account_id: Optional[UUID] = None
    started_at: Optional[datetime] = None
    last_task: Optional[str] = None
    error_count: int = 0


class FarmManager:
    """
    Manages pool of Redroid containers for token operations

    Each container is an Android emulator that can:
    - Generate fingerprints
    - Register new accounts
    - Refresh JWT tokens
    """

    def __init__(
        self,
        max_containers: int = 10,
        container_prefix: str = "redroid",
        adb_base_port: int = 5555
    ):
        self.max_containers = max_containers
        self.container_prefix = container_prefix
        self.adb_base_port = adb_base_port

        self.containers: Dict[str, ContainerInfo] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()

        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._refresh_task: Optional[asyncio.Task] = None

        if DOCKER_AVAILABLE:
            self.docker_client = docker.from_env()
        else:
            self.docker_client = None

    async def start(self) -> None:
        """Start the farm manager"""
        self._running = True

        # Discover existing containers
        await self._discover_containers()

        # Start worker
        self._worker_task = asyncio.create_task(self._process_queue())

        # Start auto-refresh checker
        self._refresh_task = asyncio.create_task(self._auto_refresh_loop())

        print(f"Farm manager started with {len(self.containers)} containers")

    async def stop(self) -> None:
        """Stop the farm manager"""
        self._running = False

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass

        print("Farm manager stopped")

    async def _discover_containers(self) -> None:
        """Discover existing Redroid containers"""
        if not self.docker_client:
            print("Docker not available, skipping container discovery")
            return

        try:
            containers = self.docker_client.containers.list(
                all=True,
                filters={"name": self.container_prefix}
            )

            for container in containers:
                info = ContainerInfo(
                    id=container.short_id,
                    name=container.name,
                    state=ContainerState.IDLE if container.status == "running" else ContainerState.STOPPING
                )
                self.containers[container.short_id] = info
                print(f"Discovered container: {container.name} ({container.status})")

        except Exception as e:
            print(f"Error discovering containers: {e}")

    def get_active_containers(self) -> List[ContainerInfo]:
        """Get list of active containers"""
        return [c for c in self.containers.values() if c.state != ContainerState.ERROR]

    def get_containers_status(self) -> List[Dict[str, Any]]:
        """Get status of all containers"""
        result = []
        for container in self.containers.values():
            result.append({
                "id": container.id,
                "name": container.name,
                "status": container.state.value,
                "created": container.started_at.isoformat() if container.started_at else None,
                "account_id": str(container.account_id) if container.account_id else None
            })
        return result

    def _get_idle_container(self) -> Optional[ContainerInfo]:
        """Get an idle container"""
        for container in self.containers.values():
            if container.state == ContainerState.IDLE:
                return container
        return None

    async def _process_queue(self) -> None:
        """Process task queue"""
        while self._running:
            try:
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)

                task_type = task.get("type")
                account_id = task.get("account_id")

                # Get idle container
                container = self._get_idle_container()
                if not container:
                    # Re-queue if no container available
                    await asyncio.sleep(5)
                    await self.task_queue.put(task)
                    continue

                # Mark container busy
                container.state = ContainerState.BUSY
                container.account_id = account_id
                container.last_task = task_type

                try:
                    if task_type == "register":
                        await self._do_register(container, account_id)
                    elif task_type == "refresh":
                        await self._do_refresh(container, account_id)
                except Exception as e:
                    print(f"Task error ({task_type}): {e}")
                    container.error_count += 1
                finally:
                    container.state = ContainerState.IDLE
                    container.account_id = None

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Queue processing error: {e}")

    async def _auto_refresh_loop(self) -> None:
        """
        Periodically check for expiring tokens and schedule active refresh

        Strategy:
        - Check every 30 seconds
        - Find accounts with tokens expiring in < 2 minutes
        - Schedule active refresh (which starts 1 min before expiry)
        - Process up to 10 accounts in parallel

        This ensures zero-downtime token refresh.
        """
        while self._running:
            try:
                import time
                now = time.time()

                db = await get_db()
                async with db.session() as session:
                    repo = AccountRepository(session)
                    session_repo = SessionRepository(session)

                    # Get accounts where token expires in < 2 minutes
                    # Using raw SQL for precise timestamp comparison
                    query = """
                        SELECT a.*, s.expires_at
                        FROM accounts a
                        JOIN sessions s ON s.account_id = a.id
                        WHERE s.is_active = true
                        AND s.expires_at < :threshold
                        AND a.status NOT IN ('REFRESHING', 'ERROR', 'BLOCKED')
                        ORDER BY s.expires_at ASC
                    """

                    # Threshold: now + 120 seconds (2 minutes)
                    from datetime import datetime as dt, timedelta
                    threshold = dt.now() + timedelta(seconds=120)

                    # Execute query (need to adapt to repository pattern)
                    # For now, use the existing get_expiring method with minimum time
                    # Note: get_expiring(hours=0.033) ≈ 2 minutes
                    expiring = await repo.get_expiring(hours=0.033)

                    if expiring:
                        print(f"Found {len(expiring)} accounts needing refresh")

                    # Schedule refresh for each account (parallel up to 10)
                    tasks = []
                    for account in expiring:
                        # Check if not already refreshing
                        if account.status == AccountStatus.ACTIVE:
                            # Get expiry time
                            active_session = await session_repo.get_active(account.id)
                            if active_session and active_session.expires_at:
                                time_left = (active_session.expires_at - dt.now()).total_seconds()
                                print(f"Auto-scheduling refresh for {account.phone} (expires in {int(time_left)}s)")

                            # Queue the refresh task
                            task = self.refresh_token(account.id)
                            tasks.append(task)

                            # Process in batches of 10
                            if len(tasks) >= 10:
                                await asyncio.gather(*tasks, return_exceptions=True)
                                tasks = []

                    # Process remaining tasks
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)

                # Check every 30 seconds
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Auto-refresh error: {e}")
                await asyncio.sleep(60)

    async def register_account(self, account_id: UUID) -> None:
        """Queue account registration"""
        await self.task_queue.put({
            "type": "register",
            "account_id": account_id
        })

    async def refresh_token(self, account_id: UUID) -> None:
        """Queue token refresh"""
        await self.task_queue.put({
            "type": "refresh",
            "account_id": account_id
        })

    async def _do_register(self, container: ContainerInfo, account_id: UUID) -> None:
        """
        Perform account registration

        This would typically:
        1. Start Avito app in container
        2. Enter phone number
        3. Receive SMS code (via SMS service or manual)
        4. Complete registration
        5. Extract session token
        """
        print(f"Starting registration for account {account_id} on {container.name}")

        db = await get_db()
        async with db.session() as session:
            repo = AccountRepository(session)
            account = await repo.get_by_id(account_id)

            if not account:
                print(f"Account {account_id} not found")
                return

            try:
                # Update status
                await repo.update_status(account_id, AccountStatus.REGISTERING)

                # In real implementation:
                # 1. Connect to container via ADB
                # 2. Install Avito APK if not present
                # 3. Launch Avito
                # 4. Automate login flow
                # 5. Extract tokens from SharedPreferences

                # For now, simulate with delay
                await asyncio.sleep(5)

                # Mark as pending (waiting for manual SMS verification)
                await repo.update_status(account_id, AccountStatus.PENDING,
                                        "Waiting for SMS verification")

                print(f"Registration started for {account.phone}, waiting for SMS")

            except Exception as e:
                await repo.update_status(account_id, AccountStatus.ERROR, str(e))
                raise

    async def _do_refresh(self, container: ContainerInfo, account_id: UUID) -> None:
        """
        Perform active token refresh

        Uses ActiveTokenRefresh to refresh token with zero downtime by:
        1. Getting current session from database
        2. Connecting to container via ADB
        3. Running active refresh (starts Avito, simulates user, waits for refresh)
        4. Saving new token to database
        """
        print(f"Starting active token refresh for account {account_id} on {container.name}")

        db = await get_db()
        async with db.session() as session:
            repo = AccountRepository(session)
            session_repo = SessionRepository(session)

            account = await repo.get_by_id(account_id)
            if not account:
                print(f"Account {account_id} not found")
                return

            try:
                await repo.update_status(account_id, AccountStatus.REFRESHING)

                # Get current session from database
                db_session = await session_repo.get_active(account_id)
                if not db_session:
                    await repo.update_status(account_id, AccountStatus.ERROR,
                                            "No active session to refresh")
                    return

                # Build AvitoSession object from database
                current_session = AvitoSession(
                    session_token=db_session.session_token,
                    refresh_token=db_session.refresh_token,
                    expires_at=int(db_session.expires_at.timestamp()),
                    device_id=account.device_id,
                    user_hash=account.user_hash,
                    fingerprint=account.fingerprint,
                    remote_device_id=account.remote_device_id,
                    cookies=db_session.cookies
                )

                # Get container ADB port (extract from container name)
                # Container names are like "redroid-1", "redroid-2", etc.
                container_num = int(container.name.split("-")[-1])
                adb_port = self.adb_base_port + (container_num - 1)

                # Connect to container via ADB
                adb = ADBController(host="localhost", port=adb_port)
                await adb.connect()

                # Perform active refresh
                refresher = ActiveTokenRefresh(adb)

                # Success callback - save to database
                def on_success(new_session: AvitoSession):
                    print(f"✓ Token refreshed for {account.phone}")
                    # Will save in main try block below

                # Error callback
                def on_error(error: str):
                    print(f"✗ Refresh error for {account.phone}: {error}")

                new_session = await refresher.refresh_token(
                    account_id=account_id,
                    current_session=current_session,
                    on_success=on_success,
                    on_error=on_error
                )

                if new_session:
                    # Save new session to database
                    from datetime import datetime as dt
                    await session_repo.create(
                        account_id=account_id,
                        session_token=new_session.session_token,
                        refresh_token=new_session.refresh_token,
                        expires_at=dt.fromtimestamp(new_session.expires_at) if new_session.expires_at else None,
                        cookies=new_session.cookies
                    )

                    # Mark old session as inactive
                    await session_repo.deactivate(db_session.id)

                    # Update account status
                    await repo.update_status(account_id, AccountStatus.ACTIVE)

                    print(f"✓ Token saved for {account.phone}, new expiry: {new_session.expires_at}")
                else:
                    await repo.update_status(account_id, AccountStatus.ERROR,
                                            "Active refresh failed")

            except Exception as e:
                print(f"Refresh error: {e}")
                await repo.update_status(account_id, AccountStatus.ERROR, str(e))
                raise


class ADBController:
    """
    ADB controller for Redroid containers

    Handles communication with Android emulators via ADB
    """

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
            return stdout.decode("utf-8")

        except Exception as e:
            print(f"ADB shell error: {e}")
            return ""

    async def push(self, local_path: str, remote_path: str) -> bool:
        """Push file to device"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", f"{self.host}:{self.port}",
                "push", local_path, remote_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            return proc.returncode == 0

        except Exception as e:
            print(f"ADB push error: {e}")
            return False

    async def pull(self, remote_path: str, local_path: str) -> bool:
        """Pull file from device"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "adb", "-s", f"{self.host}:{self.port}",
                "pull", remote_path, local_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            return proc.returncode == 0

        except Exception as e:
            print(f"ADB pull error: {e}")
            return False

    async def get_avito_session(self) -> Optional[AvitoSession]:
        """
        Extract Avito session from SharedPreferences

        Requires root access on device

        Returns:
            AvitoSession object with parsed session data, or None if not found
        """
        prefs_path = "/data/data/com.avito.android/shared_prefs/session.xml"

        # Read SharedPreferences XML file
        output = await self.shell(f"su -c 'cat {prefs_path}'")

        if not output or "error" in output.lower() or "no such file" in output.lower():
            return None

        try:
            # Parse XML using proper parser
            session = parse_session_xml(output)
            return session
        except Exception as e:
            print(f"Error parsing session XML: {e}")
            return None

    async def set_avito_session(self, session: AvitoSession) -> bool:
        """
        Inject session data into Avito SharedPreferences

        Requires root access on device

        Args:
            session: AvitoSession object to inject

        Returns:
            True if successful, False otherwise
        """
        prefs_path = "/data/data/com.avito.android/shared_prefs"

        try:
            # Generate properly formatted XML
            xml_content = generate_session_xml(session)

            # Escape single quotes for shell command
            xml_escaped = xml_content.replace("'", "'\\''")

            # Write to temp file
            temp_path = "/data/local/tmp/session.xml"
            await self.shell(f"echo '{xml_escaped}' > {temp_path}")

            # Copy to SharedPreferences with correct permissions
            await self.shell(f"su -c 'cp {temp_path} {prefs_path}/session.xml'")
            await self.shell(f"su -c 'chmod 660 {prefs_path}/session.xml'")
            await self.shell(f"su -c 'chown u0_a* {prefs_path}/session.xml'")

            # Clean up temp file
            await self.shell(f"rm {temp_path}")

            return True

        except Exception as e:
            print(f"Error setting Avito session: {e}")
            return False

    async def start_avito(self) -> bool:
        """Start Avito app"""
        result = await self.shell(
            "am start -n com.avito.android/.main.MainActivity"
        )
        return "Error" not in result

    async def stop_avito(self) -> bool:
        """Stop Avito app"""
        result = await self.shell("am force-stop com.avito.android")
        return True

    async def clear_avito_data(self) -> bool:
        """Clear Avito app data"""
        result = await self.shell("pm clear com.avito.android")
        return "Success" in result

    # ========== UI Automation Methods ==========
    # These methods simulate user interactions for active token refresh

    async def get_screen_size(self) -> tuple[int, int]:
        """
        Get screen resolution

        Returns:
            Tuple of (width, height)
        """
        output = await self.shell("wm size")
        # Output: "Physical size: 1080x2400"
        if "Physical size:" in output:
            size_str = output.split("Physical size:")[1].strip()
            width, height = size_str.split("x")
            return int(width), int(height)
        # Default to common resolution
        return 1080, 2400

    async def tap(self, x: int, y: int) -> bool:
        """
        Tap at coordinates

        Args:
            x: X coordinate
            y: Y coordinate

        Returns:
            True if successful
        """
        result = await self.shell(f"input tap {x} {y}")
        return True  # input tap doesn't return error

    async def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """
        Swipe from one point to another

        Args:
            x1, y1: Start coordinates
            x2, y2: End coordinates
            duration_ms: Swipe duration in milliseconds

        Returns:
            True if successful
        """
        result = await self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")
        return True

    async def scroll_feed(self) -> bool:
        """
        Scroll through Avito feed (simulate user browsing)

        Returns:
            True if successful
        """
        width, height = await self.get_screen_size()

        # Swipe from bottom to top (scroll down)
        x = width // 2
        y_start = height * 2 // 3
        y_end = height // 3

        return await self.swipe(x, y_start, x, y_end, duration_ms=300)

    async def open_messages(self) -> bool:
        """
        Tap on Messages tab in Avito app

        Coordinates are for standard 1080x2400 screen.
        Messages tab is typically at bottom navigation bar.

        Returns:
            True if successful
        """
        width, height = await self.get_screen_size()

        # Messages tab is usually second from left in bottom nav
        # Approximate position: 27% from left, 97% from top
        x = int(width * 0.27)
        y = int(height * 0.97)

        return await self.tap(x, y)

    async def open_profile(self) -> bool:
        """
        Tap on Profile tab in Avito app

        Returns:
            True if successful
        """
        width, height = await self.get_screen_size()

        # Profile tab is usually rightmost in bottom nav
        # Approximate position: 88% from left, 97% from top
        x = int(width * 0.88)
        y = int(height * 0.97)

        return await self.tap(x, y)

    async def open_favorites(self) -> bool:
        """
        Tap on Favorites tab

        Returns:
            True if successful
        """
        width, height = await self.get_screen_size()

        # Favorites tab is usually in middle of bottom nav
        # Approximate position: 50% from left, 97% from top
        x = int(width * 0.50)
        y = int(height * 0.97)

        return await self.tap(x, y)

    async def scroll_up(self) -> bool:
        """Scroll up (swipe down)"""
        width, height = await self.get_screen_size()
        x = width // 2
        return await self.swipe(x, height // 3, x, height * 2 // 3, 300)

    async def scroll_down(self) -> bool:
        """Scroll down (swipe up)"""
        width, height = await self.get_screen_size()
        x = width // 2
        return await self.swipe(x, height * 2 // 3, x, height // 3, 300)

    async def back(self) -> bool:
        """Press back button"""
        await self.shell("input keyevent 4")  # KEYCODE_BACK
        return True

    async def home(self) -> bool:
        """Press home button"""
        await self.shell("input keyevent 3")  # KEYCODE_HOME
        return True

    async def recents(self) -> bool:
        """Open recent apps"""
        await self.shell("input keyevent 187")  # KEYCODE_APP_SWITCH
        return True

    async def type_text(self, text: str) -> bool:
        """
        Type text (works if input field is focused)

        Args:
            text: Text to type

        Returns:
            True if successful
        """
        # Escape special characters
        escaped = text.replace(" ", "%s").replace("'", "\\'")
        await self.shell(f"input text '{escaped}'")
        return True

    async def http_api_ping(self, session: AvitoSession) -> bool:
        """
        Make HTTP request to Avito API to simulate activity

        This helps trigger token refresh by showing server activity.

        Args:
            session: AvitoSession with auth tokens

        Returns:
            True if request succeeded (even if API returns error)
        """
        if not session.session_token:
            return False

        try:
            headers = {
                "X-Session": session.session_token,
                "X-DeviceId": session.device_id or "",
                "User-Agent": "Avito/12.34.0 (Android 13; OnePlus LE2115)",
                "Content-Type": "application/json"
            }

            if session.fingerprint:
                headers["f"] = session.fingerprint

            # Ping Avito API - simple endpoint that doesn't modify data
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://app.avito.ru/api/1/messenger/getUnreadCount",
                    headers=headers,
                    json={},
                    timeout=10.0
                )

                # Any response (even 401) means request went through
                return True

        except Exception as e:
            print(f"HTTP ping error: {e}")
            return False
