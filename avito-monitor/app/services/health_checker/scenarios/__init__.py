"""Health-check scenarios A..G — one async function per scenario.

The registry below maps the canonical scenario letter to the coroutine. Both
the scheduler runner and the manual-trigger HTTP API consume it.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.services.health_checker.scenarios.a_token_freshness import scenario_a
from app.services.health_checker.scenarios.b_token_rotation import scenario_b
from app.services.health_checker.scenarios.base import ScenarioResult
from app.services.health_checker.scenarios.c_messenger_alive import scenario_c
from app.services.health_checker.scenarios.d_messenger_roundtrip import scenario_d
from app.services.health_checker.scenarios.e_sse_bridge import scenario_e
from app.services.health_checker.scenarios.f_messenger_typing import scenario_f
from app.services.health_checker.scenarios.g_bot_dedup import scenario_g
from app.services.health_checker.scenarios.i_notification_freshness import scenario_i
from app.services.health_checker.xapi_client import XapiClient

ScenarioFn = Callable[[XapiClient], Awaitable[ScenarioResult]]

REGISTRY: dict[str, ScenarioFn] = {
    "A": scenario_a,
    "B": scenario_b,
    "C": scenario_c,
    "D": scenario_d,
    "E": scenario_e,
    "F": scenario_f,
    "G": scenario_g,
    "I": scenario_i,
}

__all__ = ["REGISTRY", "ScenarioFn", "ScenarioResult"]
