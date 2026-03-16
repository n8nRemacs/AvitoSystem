import asyncio
import time
import pytest
from src.workers.rate_limiter import TokenBucket


@pytest.mark.asyncio
async def test_burst_within_limit():
    bucket = TokenBucket(rate=10.0, burst=5)
    # Should acquire 5 tokens immediately (burst)
    for _ in range(5):
        wait = await bucket.acquire()
        assert wait == 0.0


@pytest.mark.asyncio
async def test_throttle_after_burst():
    bucket = TokenBucket(rate=10.0, burst=2)
    # Exhaust burst
    await bucket.acquire()
    await bucket.acquire()
    # Next should require waiting
    wait = await bucket.acquire()
    assert wait > 0


@pytest.mark.asyncio
async def test_refill_over_time():
    bucket = TokenBucket(rate=100.0, burst=5)
    # Exhaust all tokens
    for _ in range(5):
        await bucket.acquire()
    # Wait for refill
    await asyncio.sleep(0.1)
    # Should have ~10 tokens refilled (100 rps * 0.1s)
    wait = await bucket.acquire()
    assert wait == 0.0


@pytest.mark.asyncio
async def test_wait_and_acquire():
    bucket = TokenBucket(rate=100.0, burst=1)
    await bucket.acquire()  # Exhaust
    start = time.monotonic()
    await bucket.wait_and_acquire()
    elapsed = time.monotonic() - start
    # Should have waited ~0.01s (1/100 rps)
    assert elapsed >= 0.005


@pytest.mark.asyncio
async def test_burst_cap():
    bucket = TokenBucket(rate=100.0, burst=3)
    await asyncio.sleep(0.1)  # Let tokens accumulate
    # Even after waiting, should cap at burst=3
    for _ in range(3):
        wait = await bucket.acquire()
        assert wait == 0.0
    wait = await bucket.acquire()
    assert wait > 0
