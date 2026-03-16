"""
Telegram Bot for Avito SmartFree
aiogram 3.x bot for message forwarding
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ParseMode

import sys
sys.path.insert(0, "..")
from shared.config import settings
from shared.database import get_db, TelegramUserRepository, AccountRepository, SessionRepository
from shared.models import AccountStatus
from shared.utils import mask_phone, format_time_left


# ============== States ==============

class LinkStates(StatesGroup):
    """States for account linking flow"""
    waiting_phone = State()


# ============== Router ==============

router = Router()


# ============== Keyboards ==============

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu inline keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Чаты", callback_data="chats"),
            InlineKeyboardButton(text="Статус", callback_data="status")
        ],
        [
            InlineKeyboardButton(text="Привязать аккаунт", callback_data="link")
        ]
    ])


def chats_keyboard(channels: List[Dict[str, Any]], page: int = 0) -> InlineKeyboardMarkup:
    """Chats list keyboard"""
    buttons = []
    per_page = 5

    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_channels = channels[start_idx:end_idx]

    for i, ch in enumerate(page_channels):
        idx = start_idx + i + 1
        name = ch.get("user_name", "Unknown")[:20]
        unread = ch.get("unread_count", 0)
        unread_badge = f" ({unread})" if unread > 0 else ""

        buttons.append([
            InlineKeyboardButton(
                text=f"{idx}. {name}{unread_badge}",
                callback_data=f"chat:{ch['id']}"
            )
        ])

    # Pagination
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"chats_page:{page - 1}")
        )
    if end_idx < len(channels):
        nav_buttons.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"chats_page:{page + 1}")
        )
    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="chats"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def chat_keyboard(channel_id: str) -> InlineKeyboardMarkup:
    """Single chat keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📜 История", callback_data=f"history:{channel_id}"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"chat:{channel_id}")
        ],
        [
            InlineKeyboardButton(text="◀️ К чатам", callback_data="chats"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="menu")
        ]
    ])


# ============== Handlers ==============

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start command"""
    db = await get_db()
    async with db.session() as session:
        repo = TelegramUserRepository(session)

        # Get or create user
        user = await repo.get_or_create(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name
        )

        if user.account_id:
            # User has linked account
            text = (
                f"Добро пожаловать, {message.from_user.first_name}!\n\n"
                f"Ваш аккаунт Avito привязан.\n"
                f"Используйте меню для работы с чатами."
            )
        else:
            text = (
                f"Добро пожаловать в Avito SmartFree!\n\n"
                f"Этот бот позволяет отвечать на сообщения Avito прямо из Telegram.\n\n"
                f"Для начала работы привяжите свой аккаунт Avito."
            )

    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command"""
    text = (
        "**Команды:**\n\n"
        "/start - Начать работу\n"
        "/link - Привязать аккаунт Avito\n"
        "/chats - Список чатов\n"
        "/status - Статус подключения\n"
        "/help - Эта справка\n\n"
        "**Как пользоваться:**\n"
        "1. Привяжите аккаунт Avito\n"
        "2. Выберите чат из списка\n"
        "3. Отправляйте сообщения прямо сюда\n"
        "4. Получайте уведомления о новых сообщениях"
    )
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("link"))
async def cmd_link(message: Message, state: FSMContext):
    """Start account linking"""
    await state.set_state(LinkStates.waiting_phone)
    await message.answer(
        "Введите номер телефона вашего аккаунта Avito:\n"
        "(формат: +79991234567 или 89991234567)"
    )


@router.message(LinkStates.waiting_phone)
async def process_phone(message: Message, state: FSMContext):
    """Process phone number for linking"""
    from shared.utils import normalize_phone

    phone = normalize_phone(message.text.strip())

    db = await get_db()
    async with db.session() as session:
        account_repo = AccountRepository(session)
        tg_repo = TelegramUserRepository(session)

        # Find account by phone
        account = await account_repo.get_by_phone(phone)

        if not account:
            await message.answer(
                f"Аккаунт с номером {mask_phone(phone)} не найден.\n"
                "Обратитесь к администратору для добавления аккаунта."
            )
            await state.clear()
            return

        if account.status != AccountStatus.ACTIVE:
            await message.answer(
                f"Аккаунт {mask_phone(phone)} не активен.\n"
                f"Статус: {account.status.value}\n"
                "Дождитесь активации аккаунта."
            )
            await state.clear()
            return

        # Link account
        await tg_repo.link_account(message.from_user.id, account.id)

        await message.answer(
            f"Аккаунт {mask_phone(phone)} успешно привязан!\n\n"
            "Теперь вы можете:\n"
            "- Получать уведомления о новых сообщениях\n"
            "- Отвечать на сообщения прямо из Telegram",
            reply_markup=main_menu_keyboard()
        )

    await state.clear()


@router.message(Command("chats"))
async def cmd_chats(message: Message):
    """Show chats list"""
    await show_chats(message)


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Show account status"""
    await show_status(message)


# ============== Callback Handlers ==============

@router.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery):
    """Show main menu"""
    await callback.message.edit_text(
        "Главное меню",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "link")
async def cb_link(callback: CallbackQuery, state: FSMContext):
    """Start account linking from callback"""
    await state.set_state(LinkStates.waiting_phone)
    await callback.message.edit_text(
        "Введите номер телефона вашего аккаунта Avito:\n"
        "(формат: +79991234567 или 89991234567)"
    )
    await callback.answer()


@router.callback_query(F.data == "chats")
async def cb_chats(callback: CallbackQuery):
    """Show chats list from callback"""
    await show_chats_callback(callback)


@router.callback_query(F.data.startswith("chats_page:"))
async def cb_chats_page(callback: CallbackQuery):
    """Handle chats pagination"""
    page = int(callback.data.split(":")[1])
    await show_chats_callback(callback, page=page)


@router.callback_query(F.data == "status")
async def cb_status(callback: CallbackQuery):
    """Show status from callback"""
    await show_status_callback(callback)


@router.callback_query(F.data.startswith("chat:"))
async def cb_select_chat(callback: CallbackQuery):
    """Select a chat"""
    channel_id = callback.data.split(":")[1]

    db = await get_db()
    async with db.session() as session:
        tg_repo = TelegramUserRepository(session)
        await tg_repo.update_selected_channel(callback.from_user.id, channel_id)

    # Get chat info and last messages
    # This would use the AvitoClient to fetch messages
    await callback.message.edit_text(
        f"Чат выбран. ID: {channel_id}\n\n"
        "Отправьте сообщение, и оно будет переслано в этот чат Avito.",
        reply_markup=chat_keyboard(channel_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("history:"))
async def cb_history(callback: CallbackQuery):
    """Show chat history"""
    channel_id = callback.data.split(":")[1]

    # Would fetch messages from AvitoClient
    await callback.message.edit_text(
        f"История чата {channel_id}\n\n"
        "(здесь будут сообщения)",
        reply_markup=chat_keyboard(channel_id)
    )
    await callback.answer()


# ============== Helper Functions ==============

async def show_chats(message: Message):
    """Show chats list for message"""
    db = await get_db()
    async with db.session() as session:
        tg_repo = TelegramUserRepository(session)
        user = await tg_repo.get_by_telegram_id(message.from_user.id)

        if not user or not user.account_id:
            await message.answer(
                "Сначала привяжите аккаунт Avito.",
                reply_markup=main_menu_keyboard()
            )
            return

        # Would get channels from AvitoClient
        # For now, show placeholder
        await message.answer(
            "Загрузка чатов...\n"
            "(Здесь будет список чатов Avito)",
            reply_markup=main_menu_keyboard()
        )


async def show_chats_callback(callback: CallbackQuery, page: int = 0):
    """Show chats list for callback"""
    db = await get_db()
    async with db.session() as session:
        tg_repo = TelegramUserRepository(session)
        user = await tg_repo.get_by_telegram_id(callback.from_user.id)

        if not user or not user.account_id:
            await callback.message.edit_text(
                "Сначала привяжите аккаунт Avito.",
                reply_markup=main_menu_keyboard()
            )
            await callback.answer()
            return

        # Would get channels from AvitoClient pool
        # For demo, empty list
        channels = []

        if not channels:
            await callback.message.edit_text(
                "У вас пока нет чатов.",
                reply_markup=main_menu_keyboard()
            )
        else:
            await callback.message.edit_text(
                "Ваши чаты Avito:",
                reply_markup=chats_keyboard(channels, page)
            )

    await callback.answer()


async def show_status(message: Message):
    """Show account status for message"""
    db = await get_db()
    async with db.session() as session:
        tg_repo = TelegramUserRepository(session)
        account_repo = AccountRepository(session)
        session_repo = SessionRepository(session)

        user = await tg_repo.get_by_telegram_id(message.from_user.id)

        if not user or not user.account_id:
            await message.answer(
                "Аккаунт не привязан.",
                reply_markup=main_menu_keyboard()
            )
            return

        account = await account_repo.get_by_id(user.account_id)
        active_session = await session_repo.get_active(user.account_id)

        status_text = _format_status(account, active_session)
        await message.answer(status_text, reply_markup=main_menu_keyboard())


async def show_status_callback(callback: CallbackQuery):
    """Show account status for callback"""
    db = await get_db()
    async with db.session() as session:
        tg_repo = TelegramUserRepository(session)
        account_repo = AccountRepository(session)
        session_repo = SessionRepository(session)

        user = await tg_repo.get_by_telegram_id(callback.from_user.id)

        if not user or not user.account_id:
            await callback.message.edit_text(
                "Аккаунт не привязан.",
                reply_markup=main_menu_keyboard()
            )
            await callback.answer()
            return

        account = await account_repo.get_by_id(user.account_id)
        active_session = await session_repo.get_active(user.account_id)

        status_text = _format_status(account, active_session)
        await callback.message.edit_text(status_text, reply_markup=main_menu_keyboard())

    await callback.answer()


def _format_status(account, session) -> str:
    """Format account status text"""
    if not account:
        return "Аккаунт не найден."

    lines = [
        f"**Статус аккаунта**\n",
        f"Телефон: {mask_phone(account.phone)}",
        f"Статус: {account.status.value}",
    ]

    if session:
        hours_left = session.hours_until_expiry
        time_str = format_time_left(hours_left)

        if hours_left > 0:
            lines.append(f"Токен: действителен ({time_str})")
        else:
            lines.append(f"Токен: истёк")
    else:
        lines.append("Токен: отсутствует")

    if account.error_message:
        lines.append(f"Ошибка: {account.error_message}")

    return "\n".join(lines)


# ============== Message Forwarding ==============

@router.message(F.text)
async def forward_to_avito(message: Message):
    """
    Forward text message to selected Avito chat

    This handler catches all text messages and sends them
    to the currently selected Avito chat.
    """
    db = await get_db()
    async with db.session() as session:
        tg_repo = TelegramUserRepository(session)
        user = await tg_repo.get_by_telegram_id(message.from_user.id)

        if not user or not user.account_id:
            await message.answer(
                "Сначала привяжите аккаунт Avito.",
                reply_markup=main_menu_keyboard()
            )
            return

        if not user.selected_channel_id:
            await message.answer(
                "Сначала выберите чат для отправки сообщений.",
                reply_markup=main_menu_keyboard()
            )
            return

        # Would send via AvitoClient
        # For now, confirm receipt
        await message.answer(
            f"Сообщение отправлено в чат {user.selected_channel_id}\n"
            "(интеграция с Avito будет добавлена)"
        )


# ============== Bot Factory ==============

def create_bot() -> tuple[Bot, Dispatcher]:
    """Create and configure bot and dispatcher"""
    bot = Bot(token=settings.telegram_bot_token, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    dp.include_router(router)

    return bot, dp


async def run_bot():
    """Run the bot"""
    bot, dp = create_bot()

    print("Starting Telegram bot...")
    await dp.start_polling(bot)


# ============== Main ==============

if __name__ == "__main__":
    asyncio.run(run_bot())
