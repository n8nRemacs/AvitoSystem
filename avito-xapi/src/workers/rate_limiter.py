import asyncio
import time


class TokenBucket:
    """Async token bucket rate limiter."""

    def __init__(self, rate: float = 5.0, burst: int = 10):
        self.rate = rate        # tokens per second
        self.burst = burst      # max tokens
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_refill = now

    async def acquire(self, tokens: float = 1.0) -> float:
        """Acquire tokens. Returns wait time (0 if immediate)."""
        async with self._lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0

            deficit = tokens - self.tokens
            wait_time = deficit / self.rate
            self.tokens = 0
            return wait_time

    async def wait_and_acquire(self, tokens: float = 1.0) -> None:
        """Acquire tokens, waiting if necessary."""
        wait = await self.acquire(tokens)
        if wait > 0:
            await asyncio.sleep(wait)
