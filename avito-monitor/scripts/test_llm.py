"""Manual smoke for LLMAnalyzer against a real OpenRouter key.

Examples
--------

Classify a real Avito listing (xapi must have an active session)::

    docker exec avito-monitor-app-1 python -m scripts.test_llm \\
        classify --avito-id 7512611043

Classify a synthetic listing for one of the eight condition classes::

    docker exec avito-monitor-app-1 python -m scripts.test_llm \\
        classify --mock blocked_icloud

Match a real listing against custom criteria::

    docker exec avito-monitor-app-1 python -m scripts.test_llm \\
        match --avito-id 7512611043 --criteria "аккумулятор >= 85%, без iCloud"

The script intentionally skips the DB cache and uses an in-memory
:class:`InMemoryLLMCache` so each run hits OpenRouter — that's the point
of a smoke test. It prints cost + latency so you can sanity-check
billing.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any

from app.config import get_settings
from app.integrations.openrouter import OpenRouterClient
from app.services.llm_analyzer import LLMAnalyzer
from app.services.llm_cache import InMemoryLLMCache
from avito_mcp.integrations.xapi_client import XapiClient
from avito_mcp.tools.listings import avito_get_listing_impl
from shared.models.avito import ListingDetail

log = logging.getLogger("scripts.test_llm")


# Eight canned listings, one per ConditionClass — used by --mock to test
# the classifier without hitting Avito.
_MOCK_LISTINGS: dict[str, ListingDetail] = {
    "working": ListingDetail(
        id=900001,
        title="iPhone 12 Pro Max 256 ГБ Pacific Blue",
        price=35000,
        description=(
            "Полностью рабочий, без iCloud, аккумулятор 89%, состояние "
            "хорошее, есть мелкие потёртости на корпусе. Чек и коробка."
        ),
        parameters={"Память": "256 ГБ", "Цвет": "Pacific Blue"},
        first_seen="2026-04-20T10:00:00Z",
    ),
    "blocked_icloud": ListingDetail(
        id=900002,
        title="iPhone 11 на запчасти/восстановление",
        price=12000,
        description=(
            "iCloud lock, привязан к чужому Apple ID. Корпус целый, "
            "экран рабочий, остальное проверить не могу."
        ),
        parameters={"Память": "128 ГБ"},
        first_seen="2026-04-21T10:00:00Z",
    ),
    "blocked_account": ListingDetail(
        id=900003,
        title="Xiaomi Redmi Note 12, требует ввод аккаунта Mi",
        price=4500,
        description=(
            "Заблокирован на учётке Mi, FRP. Включается, экран целый, "
            "но пройти настройку нельзя."
        ),
        parameters={},
        first_seen="2026-04-22T10:00:00Z",
    ),
    "not_starting": ListingDetail(
        id=900004,
        title="Samsung Galaxy S21 не включается",
        price=6000,
        description=(
            "Не включается, висит на лого, бутлуп. На зарядку не реагирует. "
            "Что именно — не разбирался."
        ),
        parameters={},
        first_seen="2026-04-22T10:00:00Z",
    ),
    "broken_screen": ListingDetail(
        id=900005,
        title="iPhone XS со стеклом-паутинкой",
        price=8500,
        description=(
            "Разбит экран, тачскрин работает частично, в остальном телефон "
            "рабочий, без iCloud, аккумулятор около 80%."
        ),
        parameters={"Память": "64 ГБ"},
        first_seen="2026-04-23T10:00:00Z",
    ),
    "broken_other": ListingDetail(
        id=900006,
        title="Pixel 7 не работает динамик и нижний микрофон",
        price=11000,
        description=(
            "Экран целый, акум норм, но не слышит собеседника при звонке "
            "и динамик хрипит. Заряжается нормально."
        ),
        parameters={},
        first_seen="2026-04-23T10:00:00Z",
    ),
    "parts_only": ListingDetail(
        id=900007,
        title="iPhone 8 на запчасти / донор",
        price=2500,
        description=(
            "Не рабочий, на разбор. Плата под вопросом, дисплей рабочий, "
            "корпус целый. Продаю как комплект деталей."
        ),
        parameters={},
        first_seen="2026-04-24T10:00:00Z",
    ),
    "unknown": ListingDetail(
        id=900008,
        title="Продам айфон, торг",
        price=15000,
        description="Срочно. Пишите в личку.",
        parameters={},
        first_seen="2026-04-24T10:00:00Z",
    ),
}


def _print_block(title: str, body: dict[str, Any]) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(body, ensure_ascii=False, indent=2))


def _build_analyzer() -> LLMAnalyzer:
    settings = get_settings()
    if not settings.openrouter_api_key:
        print("ERROR: OPENROUTER_API_KEY is empty in .env", file=sys.stderr)
        sys.exit(2)

    openrouter = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        app_base_url=settings.app_base_url,
        app_title="Avito Monitor (smoke)",
    )
    return LLMAnalyzer(
        openrouter=openrouter,
        cache=InMemoryLLMCache(),
        default_text_model=settings.openrouter_default_text_model,
        default_vision_model=settings.openrouter_default_vision_model,
    )


async def _resolve_listing(args) -> ListingDetail:
    if args.mock:
        if args.mock not in _MOCK_LISTINGS:
            print(
                f"ERROR: --mock must be one of {sorted(_MOCK_LISTINGS)}",
                file=sys.stderr,
            )
            sys.exit(2)
        return _MOCK_LISTINGS[args.mock]

    if not args.avito_id:
        print("ERROR: provide --avito-id <int> or --mock <class>", file=sys.stderr)
        sys.exit(2)

    xapi = XapiClient()
    try:
        return await avito_get_listing_impl(args.avito_id, client=xapi)
    except Exception as exc:
        print(f"ERROR: avito_get_listing failed: {exc}", file=sys.stderr)
        sys.exit(2)


async def _cmd_classify(args) -> int:
    analyzer = _build_analyzer()
    listing = await _resolve_listing(args)
    print(f"listing: id={listing.id} title={listing.title[:80]!r} price={listing.price}")

    result = await analyzer.classify_condition(listing, model=args.model)
    _print_block("ConditionClassification", result.model_dump(mode="json"))
    return 0


async def _cmd_match(args) -> int:
    if not args.criteria:
        print("ERROR: --criteria required for match", file=sys.stderr)
        return 2
    analyzer = _build_analyzer()
    listing = await _resolve_listing(args)
    allowed = (args.allowed_conditions or "working").split(",")
    allowed = [c.strip() for c in allowed if c.strip()]
    print(
        f"listing: id={listing.id} title={listing.title[:80]!r} "
        f"criteria={args.criteria!r} allowed={allowed}"
    )

    result = await analyzer.match_criteria(
        listing,
        criteria=args.criteria,
        allowed_conditions=allowed,
        model=args.model,
    )
    _print_block("MatchResult", result.model_dump(mode="json"))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scripts.test_llm")
    sub = p.add_subparsers(dest="command", required=True)

    common_kwargs = {"help": "Numeric Avito item id, e.g. 7512611043"}
    common_mock = {"help": f"One of: {', '.join(sorted(_MOCK_LISTINGS))}"}
    common_model = {
        "help": "Override OpenRouter model (default = settings.openrouter_default_text_model)",
    }

    pc = sub.add_parser("classify", help="Run classify_condition")
    pc.add_argument("--avito-id", type=int, **common_kwargs)
    pc.add_argument("--mock", type=str, **common_mock)
    pc.add_argument("--model", type=str, default=None, **common_model)

    pm = sub.add_parser("match", help="Run match_criteria")
    pm.add_argument("--avito-id", type=int, **common_kwargs)
    pm.add_argument("--mock", type=str, **common_mock)
    pm.add_argument("--criteria", type=str, required=False)
    pm.add_argument(
        "--allowed-conditions",
        type=str,
        default="working",
        help="Comma-separated, e.g. 'working,broken_screen'",
    )
    pm.add_argument("--model", type=str, default=None, **common_model)

    return p


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "WARNING"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = _build_parser().parse_args()

    if args.command == "classify":
        sys.exit(asyncio.run(_cmd_classify(args)))
    elif args.command == "match":
        sys.exit(asyncio.run(_cmd_match(args)))
    else:
        print(f"unknown command: {args.command}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
