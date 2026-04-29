"""ADB-based device switcher for Avito session pool.

Управляет N физическими телефонами через `adb -s <serial>`. Per-phone
asyncio.Lock позволяет параллельные switch'и на разных устройствах.
"""
import asyncio
import logging
from typing import Tuple

log = logging.getLogger(__name__)


class DeviceSwitchError(RuntimeError):
    pass


async def _run_adb(args: list[str], timeout: float = 10.0) -> Tuple[str, int]:
    """Run `adb <args>`, return (stdout, returncode)."""
    proc = await asyncio.create_subprocess_exec(
        "adb", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise DeviceSwitchError(f"adb {args} timed out")
    return stdout.decode().strip(), proc.returncode


class DeviceSwitcher:
    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, phone_serial: str) -> asyncio.Lock:
        if phone_serial not in self._locks:
            self._locks[phone_serial] = asyncio.Lock()
        return self._locks[phone_serial]

    async def current_user(self, phone_serial: str) -> int:
        out, code = await _run_adb(["-s", phone_serial, "shell", "am", "get-current-user"])
        if code != 0:
            raise DeviceSwitchError(f"get-current-user failed: rc={code}, out={out}")
        return int(out.strip())

    async def switch_to(
        self, phone_serial: str, target: int,
        _confirm_timeout_sec: float = 5.0,
        _confirm_interval_sec: float = 0.5,
    ) -> None:
        async with self._lock_for(phone_serial):
            curr = await self.current_user(phone_serial)
            if curr == target:
                return
            out, code = await _run_adb(["-s", phone_serial, "shell", "am", "switch-user", str(target)])
            if code != 0:
                raise DeviceSwitchError(f"switch-user failed: rc={code}, out={out}")

            # confirm loop: check first, then sleep — device may already
            # be at target right after switch-user, no need to wait blindly.
            elapsed = 0.0
            while elapsed < _confirm_timeout_sec:
                if await self.current_user(phone_serial) == target:
                    return
                await asyncio.sleep(_confirm_interval_sec)
                elapsed += _confirm_interval_sec
            raise DeviceSwitchError(
                f"switch-user {target} on {phone_serial}: confirm timeout after {_confirm_timeout_sec}s"
            )

    async def health(self, phone_serial: str) -> bool:
        out, code = await _run_adb(["-s", phone_serial, "get-state"])
        return code == 0 and out.strip() == "device"

    async def list_devices(self) -> list[str]:
        out, code = await _run_adb(["devices"])
        if code != 0:
            return []
        serials = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1] == "device":
                serials.append(parts[0])
        return serials


# Singleton, инициализируется при старте xapi
device_switcher = DeviceSwitcher()
