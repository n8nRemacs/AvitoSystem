"""Tests for DeviceSwitcher — multi-phone ADB wrapper."""
import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from src.workers.device_switcher import DeviceSwitcher, DeviceSwitchError


@pytest.fixture
def fake_adb():
    """Mock _run_adb to return (stdout, returncode) tuples."""
    with patch("src.workers.device_switcher._run_adb", new_callable=AsyncMock) as mock:
        yield mock


@pytest.mark.asyncio
async def test_switch_to_target_when_already_there_is_noop(fake_adb):
    fake_adb.side_effect = [
        ("10", 0),  # adb -s S shell am get-current-user → 10
    ]
    sw = DeviceSwitcher()
    await sw.switch_to("110139ce", 10)
    # Только один вызов get-current-user, switch-user не вызывался
    assert fake_adb.call_count == 1
    assert fake_adb.call_args_list[0][0][0] == ["-s", "110139ce", "shell", "am", "get-current-user"]


@pytest.mark.asyncio
async def test_switch_to_when_different_runs_switch_user(fake_adb):
    fake_adb.side_effect = [
        ("10", 0),  # initial: at 10
        ("", 0),    # switch-user 0
        ("0", 0),   # confirm: now at 0
    ]
    sw = DeviceSwitcher()
    await sw.switch_to("110139ce", 0)
    assert fake_adb.call_count == 3
    assert fake_adb.call_args_list[1][0][0] == ["-s", "110139ce", "shell", "am", "switch-user", "0"]


@pytest.mark.asyncio
async def test_switch_to_raises_on_timeout(fake_adb):
    fake_adb.side_effect = [
        ("10", 0),  # at 10
        ("", 0),    # switch-user 0
        ("10", 0), ("10", 0), ("10", 0),  # confirm loop returns wrong user
    ]
    sw = DeviceSwitcher()
    with pytest.raises(DeviceSwitchError):
        await sw.switch_to("110139ce", 0, _confirm_timeout_sec=1.5, _confirm_interval_sec=0.5)


@pytest.mark.asyncio
async def test_health_returns_true_when_adb_state_device(fake_adb):
    fake_adb.return_value = ("device", 0)
    sw = DeviceSwitcher()
    assert await sw.health("110139ce") is True


@pytest.mark.asyncio
async def test_health_returns_false_when_adb_unauthorized(fake_adb):
    fake_adb.return_value = ("unauthorized", 0)
    sw = DeviceSwitcher()
    assert await sw.health("110139ce") is False


@pytest.mark.asyncio
async def test_per_phone_locks_dont_block_each_other(fake_adb):
    """Switch на двух разных phone_serial'ах должны идти параллельно (разные locks)."""
    fake_adb.side_effect = [
        ("0", 0), ("", 0), ("10", 0),  # phone A
        ("0", 0), ("", 0), ("10", 0),  # phone B
    ]
    sw = DeviceSwitcher()
    await asyncio.gather(
        sw.switch_to("PHONE_A", 10),
        sw.switch_to("PHONE_B", 10),
    )
    assert fake_adb.call_count == 6


@pytest.mark.asyncio
async def test_list_devices_parses_adb_devices(fake_adb):
    fake_adb.return_value = (
        "List of devices attached\n"
        "110139ce\tdevice\n"
        "ABCDEFGH\toffline\n"
        "XYZ12345\tdevice\n",
        0,
    )
    sw = DeviceSwitcher()
    serials = await sw.list_devices()
    assert serials == ["110139ce", "XYZ12345"]
