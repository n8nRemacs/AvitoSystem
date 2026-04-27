"""Handlers for the bot's slash-commands."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import func, select

from app.config import get_settings
from app.db.base import get_sessionmaker
from app.db.models import LLMAnalysis, ProfileRun, SearchProfile
from app.services import runtime_state

log = logging.getLogger(__name__)
router = Router(name="commands")


HELP_TEXT = (
    "*Avito Monitor — команды*\n\n"
    "/status — состояние системы\n"
    "/profiles — список профилей\n"
    "/pause — приостановить мониторинг\n"
    "/resume — возобновить\n"
    "/silent <минут> — тихий режим\n"
    "/help — это сообщение"
)


def _local_tz() -> ZoneInfo:
    try:
        return ZoneInfo(get_settings().timezone)
    except Exception:
        return ZoneInfo("UTC")


def _fmt_local(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tz = _local_tz()
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    user = message.from_user
    user_label = f"id={user.id}" if user else "anon"
    log.info("bot.cmd.start user=%s", user_label)
    await message.answer(
        "Привет! Я бот Avito Monitor.\n\n"
        "Доступ подтверждён. Уведомления о найденных лотах и рыночных "
        "сигналах будут приходить сюда.\n\n"
        + HELP_TEXT
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    sessionmaker = get_sessionmaker()
    now = datetime.now(timezone.utc)
    cutoff_24h = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with sessionmaker() as session:
        active_count = (
            await session.execute(
                select(func.count())
                .select_from(SearchProfile)
                .where(SearchProfile.is_active.is_(True))
            )
        ).scalar_one()
        last_run = (
            await session.execute(
                select(ProfileRun.started_at)
                .order_by(ProfileRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        spend_24h = (
            await session.execute(
                select(func.coalesce(func.sum(LLMAnalysis.cost_usd), 0))
                .where(LLMAnalysis.created_at >= cutoff_24h)
            )
        ).scalar_one()

    paused = await runtime_state.is_paused()
    silent_until = await runtime_state.silent_until()
    silent_line = (
        f"Тихий режим до {_fmt_local(silent_until)}"
        if silent_until and silent_until > now
        else "Тихий режим: выкл."
    )

    pause_line = "🟡 *Поставлено на паузу*\n\n" if paused else ""
    await message.answer(
        f"{pause_line}"
        f"Активных профилей: *{active_count}*\n"
        f"Последний прогон: {_fmt_local(last_run)}\n"
        f"LLM-расход за сутки: *${float(spend_24h):.4f}*\n"
        f"{silent_line}"
    )


@router.message(Command("pause"))
async def cmd_pause(message: Message) -> None:
    await runtime_state.set_paused(True)
    await message.answer("⏸ Мониторинг поставлен на паузу.")


@router.message(Command("resume"))
async def cmd_resume(message: Message) -> None:
    await runtime_state.set_paused(False)
    await message.answer("▶️ Мониторинг возобновлён.")


@router.message(Command("silent"))
async def cmd_silent(message: Message, command: CommandObject) -> None:
    arg = (command.args or "").strip()
    if not arg:
        await message.answer(
            "Используй `/silent <минут>` — например `/silent 60`. "
            "`/silent 0` отключает тихий режим."
        )
        return
    try:
        minutes = int(arg.split()[0])
    except ValueError:
        await message.answer(f"Не понял `{arg}`. Нужно целое число минут.")
        return
    if minutes <= 0:
        await runtime_state.clear_silent()
        await message.answer("🔔 Тихий режим отключён.")
        return
    until = await runtime_state.set_silent_for(minutes)
    await message.answer(
        f"🔕 Тихий режим до {_fmt_local(until)}.\n"
        f"Уведомления продолжат накапливаться, после окончания — отправятся."
    )


@router.message(Command("profiles"))
async def cmd_profiles(message: Message) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(SearchProfile.id, SearchProfile.name, SearchProfile.is_active)
                .order_by(SearchProfile.created_at.desc())
                .limit(20)
            )
        ).all()
    if not rows:
        await message.answer("Профилей нет.")
        return
    lines = ["*Профили:*"]
    for pid, name, is_active in rows:
        marker = "▶️" if is_active else "⏸"
        lines.append(f"{marker} {name}\n  `{pid}`")
    await message.answer("\n".join(lines))
