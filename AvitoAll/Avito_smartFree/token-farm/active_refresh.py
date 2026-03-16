"""
Active Token Refresh Module

Implements zero-downtime token refresh by launching Avito before expiration
and actively simulating user behavior until token auto-refreshes.

Timeline:
---------
11:59:00 - Start refresh (60 seconds before expiration)
12:00:00 - Token expires
12:00:15 - Token auto-refreshes (Avito SDK does this automatically)
12:00:20 - Detect new token, save, and stop

Downtime: 0 seconds (token refreshes WHILE app is running)
"""

import asyncio
import random
import logging
from datetime import datetime
from typing import Optional, Callable, List
from uuid import UUID

from avito_prefs_parser import AvitoSession
from farm_manager import ADBController

logger = logging.getLogger(__name__)


class ActiveTokenRefresh:
    """
    Manages active token refresh with user simulation

    This class handles the critical task of refreshing Avito tokens
    with minimal downtime by:
    1. Starting Avito app BEFORE token expires
    2. Actively simulating user behavior
    3. Monitoring for token refresh
    4. Saving new token immediately
    """

    def __init__(
        self,
        adb: ADBController,
        check_interval: int = 17,  # seconds between token checks
        max_rounds: int = 30,       # max simulation rounds (10 minutes)
        start_before_expiry: int = 60  # start N seconds before expiry
    ):
        self.adb = adb
        self.check_interval = check_interval
        self.max_rounds = max_rounds
        self.start_before_expiry = start_before_expiry

    async def refresh_token(
        self,
        account_id: UUID,
        current_session: AvitoSession,
        on_success: Optional[Callable[[AvitoSession], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ) -> Optional[AvitoSession]:
        """
        Perform active token refresh

        Args:
            account_id: Account UUID
            current_session: Current session data
            on_success: Callback when token refreshed successfully
            on_error: Callback on error

        Returns:
            New AvitoSession if successful, None otherwise

        Timeline:
            1. Inject current session into container
            2. Start Avito app
            3. Simulate user activity in rounds
            4. Check for token refresh every 15-20 seconds
            5. Save and return new token
            6. Stop Avito app
        """
        logger.info(f"Starting active token refresh for account {account_id}")

        try:
            # Step 1: Inject current session
            logger.info("Injecting current session into container")
            success = await self.adb.set_avito_session(current_session)
            if not success:
                raise Exception("Failed to inject session")

            # Step 2: Start Avito app
            logger.info("Starting Avito app")
            await self.adb.start_avito()
            await asyncio.sleep(3)  # Wait for app to initialize

            old_expiry = current_session.expires_at
            logger.info(f"Current token expires at: {old_expiry}")

            # Step 3: Active simulation loop
            new_session = await self._simulation_loop(old_expiry)

            if not new_session:
                raise Exception("Token did not refresh within timeout")

            # Step 4: Stop Avito
            logger.info("Stopping Avito app")
            await self.adb.stop_avito()

            # Success callback
            if on_success:
                on_success(new_session)

            logger.info(f"✓ Token refreshed successfully for account {account_id}")
            return new_session

        except Exception as e:
            error_msg = f"Active refresh failed: {e}"
            logger.error(error_msg)

            # Stop Avito on error
            try:
                await self.adb.stop_avito()
            except:
                pass

            # Error callback
            if on_error:
                on_error(error_msg)

            return None

    async def _simulation_loop(
        self,
        old_expiry: Optional[int]
    ) -> Optional[AvitoSession]:
        """
        Main simulation loop - actively use app until token refreshes

        Args:
            old_expiry: Old token expiry timestamp

        Returns:
            New AvitoSession if token refreshed, None if timeout
        """
        for round_num in range(1, self.max_rounds + 1):
            logger.info(f"Simulation round {round_num}/{self.max_rounds}")

            # Simulate user actions
            await self._simulate_user_activity(round_num)

            # Check for token refresh
            await asyncio.sleep(self.check_interval)

            new_session = await self.adb.get_avito_session()

            if new_session and new_session.expires_at:
                if old_expiry is None or new_session.expires_at > old_expiry:
                    logger.info(f"✓ Token refreshed after {round_num} rounds!")
                    logger.info(f"  Old expiry: {old_expiry}")
                    logger.info(f"  New expiry: {new_session.expires_at}")
                    return new_session

            # Log progress
            if new_session and new_session.expires_at:
                time_left = new_session.expires_at - int(datetime.now().timestamp())
                logger.info(f"  Token not refreshed yet, expires in {time_left}s")

        logger.warning(f"Token did not refresh after {self.max_rounds} rounds")
        return None

    async def _simulate_user_activity(self, round_num: int) -> None:
        """
        Simulate realistic user activity

        Randomly performs 2-4 actions per round to appear like real user.

        Args:
            round_num: Current round number
        """
        # Available actions with weights (more common actions have higher weight)
        actions = [
            (self._action_scroll_feed, 3),      # Scrolling is most common
            (self._action_open_messages, 2),    # Check messages often
            (self._action_open_profile, 1),     # Profile less frequent
            (self._action_open_favorites, 1),   # Favorites occasionally
            (self._action_http_ping, 2),        # HTTP requests mixed in
        ]

        # Randomly select 2-4 actions
        num_actions = random.randint(2, 4)

        for i in range(num_actions):
            # Weighted random selection
            action_func, _ = random.choices(
                actions,
                weights=[w for _, w in actions],
                k=1
            )[0]

            try:
                await action_func()
            except Exception as e:
                logger.warning(f"Action error: {e}")

            # Random pause between actions (1-3 seconds)
            await asyncio.sleep(random.uniform(1.0, 3.0))

    # ========== Individual Actions ==========

    async def _action_scroll_feed(self) -> None:
        """Scroll through feed"""
        logger.debug("Action: Scroll feed")
        await self.adb.scroll_feed()

    async def _action_open_messages(self) -> None:
        """Open messages tab"""
        logger.debug("Action: Open messages")
        await self.adb.open_messages()
        await asyncio.sleep(1)
        # Maybe scroll messages
        if random.random() > 0.5:
            await self.adb.scroll_down()

    async def _action_open_profile(self) -> None:
        """Open profile tab"""
        logger.debug("Action: Open profile")
        await self.adb.open_profile()

    async def _action_open_favorites(self) -> None:
        """Open favorites"""
        logger.debug("Action: Open favorites")
        await self.adb.open_favorites()
        await asyncio.sleep(0.5)
        if random.random() > 0.5:
            await self.adb.scroll_feed()

    async def _action_http_ping(self) -> None:
        """Make HTTP API request"""
        logger.debug("Action: HTTP ping")
        # Get current session to make authenticated request
        session = await self.adb.get_avito_session()
        if session:
            await self.adb.http_api_ping(session)

    async def _action_random_taps(self) -> None:
        """Random taps (exploration)"""
        logger.debug("Action: Random taps")
        width, height = await self.adb.get_screen_size()

        # Tap in safe zones (middle of screen)
        x = random.randint(width // 4, width * 3 // 4)
        y = random.randint(height // 3, height * 2 // 3)

        await self.adb.tap(x, y)


# Convenience function
async def refresh_account_token(
    adb_host: str,
    adb_port: int,
    account_id: UUID,
    current_session: AvitoSession
) -> Optional[AvitoSession]:
    """
    Convenience function to refresh a single account's token

    Args:
        adb_host: ADB host
        adb_port: ADB port
        account_id: Account UUID
        current_session: Current session data

    Returns:
        New AvitoSession if successful
    """
    adb = ADBController(host=adb_host, port=adb_port)
    await adb.connect()

    refresher = ActiveTokenRefresh(adb)
    return await refresher.refresh_token(account_id, current_session)


# Example usage
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    async def main():
        # Example session (expired or about to expire)
        session = AvitoSession(
            session_token="eyJ...",
            device_id="device123",
            fingerprint="A2.fingerprint",
            expires_at=int(datetime.now().timestamp()) + 60  # Expires in 60s
        )

        # Connect to container
        adb = ADBController(host="localhost", port=5555)
        await adb.connect()

        # Refresh
        refresher = ActiveTokenRefresh(adb)
        new_session = await refresher.refresh_token(
            account_id=UUID("00000000-0000-0000-0000-000000000000"),
            current_session=session,
            on_success=lambda s: print(f"✓ Success! New expiry: {s.expires_at}"),
            on_error=lambda e: print(f"✗ Error: {e}")
        )

        if new_session:
            print("\n=== New Session ===")
            print(f"Token: {new_session.session_token[:50]}...")
            print(f"Expires: {new_session.expires_at}")
            print(f"Time until expiry: {new_session.time_until_expiry()}s")

    asyncio.run(main())
