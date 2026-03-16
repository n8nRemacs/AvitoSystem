"""
Humanized Avito Client - обёртка с задержками по времени суток

Задержки перед ответом:
- Рабочее время (9:00-18:00): 3-7 секунд
- Нерабочее время (18:00-00:00, 7:00-9:00): 15-45 секунд
- Ночное время (00:00-07:00): 1-3 минуты
"""

import random
import time
from datetime import datetime, time as dt_time
from typing import Optional, List, Callable
import logging

from avito_user_client import AvitoMessengerParser

logger = logging.getLogger(__name__)


class TimeWindow:
    """Определение временных окон"""

    # Рабочее время
    WORK_START = dt_time(9, 0)
    WORK_END = dt_time(18, 0)

    # Ночное время
    NIGHT_START = dt_time(0, 0)
    NIGHT_END = dt_time(7, 0)

    @classmethod
    def get_current_period(cls) -> str:
        """Определить текущий период: 'work', 'off', 'night'"""
        now = datetime.now().time()

        # Ночь: 00:00 - 07:00
        if cls.NIGHT_START <= now < cls.NIGHT_END:
            return 'night'

        # Рабочее: 09:00 - 18:00
        if cls.WORK_START <= now < cls.WORK_END:
            return 'work'

        # Нерабочее: 07:00-09:00, 18:00-00:00
        return 'off'


class HumanizedAvitoClient:
    """
    Обёртка над AvitoMessengerParser с человеческими задержками

    Использование:
        client = HumanizedAvitoClient(sessid="your_sessid")

        # Отправка с автоматической задержкой по времени суток
        client.send_message_humanized(channel_id, "Привет!")

        # Принудительно задержка как в рабочее время
        client.send_message_humanized(channel_id, "Срочно!", force_period='work')
    """

    # Задержки в секундах (min, max)
    DELAYS = {
        'work': (3, 7),           # Рабочее время: 3-7 сек
        'off': (15, 45),          # Нерабочее: 15-45 сек
        'night': (60, 180),       # Ночь: 1-3 минуты
    }

    # Дополнительная задержка на "печатание" (символов в секунду)
    TYPING_SPEED = 5.0  # ~5 символов в секунду

    def __init__(
        self,
        sessid: str,
        output_dir: str = "avito_chats",
        typing_simulation: bool = True,
        on_delay_start: Callable[[str, float], None] = None,
        custom_delays: dict = None
    ):
        """
        Args:
            sessid: Cookie sessid из браузера Avito
            output_dir: Папка для экспорта
            typing_simulation: Добавлять задержку на "печатание" по длине текста
            on_delay_start: Callback при начале задержки (period, seconds)
            custom_delays: Свои задержки {'work': (min, max), 'off': ..., 'night': ...}
        """
        self.client = AvitoMessengerParser(sessid=sessid, output_dir=output_dir)
        self.typing_simulation = typing_simulation
        self.on_delay_start = on_delay_start

        if custom_delays:
            self.DELAYS = {**self.DELAYS, **custom_delays}

    def _get_delay(self, period: str = None, text_length: int = 0) -> float:
        """
        Рассчитать задержку

        Args:
            period: Принудительно период ('work', 'off', 'night') или None для авто
            text_length: Длина текста для симуляции печатания

        Returns:
            Задержка в секундах
        """
        if period is None:
            period = TimeWindow.get_current_period()

        min_delay, max_delay = self.DELAYS.get(period, self.DELAYS['work'])
        base_delay = random.uniform(min_delay, max_delay)

        # Добавляем время на "печатание"
        typing_delay = 0
        if self.typing_simulation and text_length > 0:
            typing_delay = text_length / self.TYPING_SPEED
            # Добавляем случайность ±20%
            typing_delay *= random.uniform(0.8, 1.2)

        return base_delay + typing_delay

    def _do_delay(self, delay: float, period: str):
        """Выполнить задержку с логированием"""
        if self.on_delay_start:
            self.on_delay_start(period, delay)

        logger.info(f"Humanized delay: {delay:.1f}s (period: {period})")
        time.sleep(delay)

    def send_message_humanized(
        self,
        channel_id: str,
        text: str,
        quote_message_id: Optional[str] = None,
        force_period: str = None,
        skip_delay: bool = False
    ) -> dict:
        """
        Отправить сообщение с человеческой задержкой

        Args:
            channel_id: ID чата
            text: Текст сообщения
            quote_message_id: ID сообщения для цитирования
            force_period: Принудительно использовать период ('work', 'off', 'night')
            skip_delay: Пропустить задержку (для срочных)

        Returns:
            Ответ API
        """
        period = force_period or TimeWindow.get_current_period()

        if not skip_delay:
            delay = self._get_delay(period, len(text))
            self._do_delay(delay, period)

        return self.client.send_message(
            channel_id=channel_id,
            text=text,
            quote_message_id=quote_message_id
        )

    def read_chats_humanized(
        self,
        channel_ids: List[str],
        category: int = 1,
        force_period: str = None,
        skip_delay: bool = False
    ) -> dict:
        """
        Пометить чаты прочитанными с задержкой

        Args:
            channel_ids: Список ID чатов
            category: Категория (1=продажи, 2=покупки)
            force_period: Принудительно период
            skip_delay: Пропустить задержку
        """
        period = force_period or TimeWindow.get_current_period()

        if not skip_delay:
            # Для чтения используем меньшую задержку (1/3 от отправки)
            min_d, max_d = self.DELAYS.get(period, self.DELAYS['work'])
            delay = random.uniform(min_d / 3, max_d / 3)
            self._do_delay(delay, period)

        return self.client.read_chats(channel_ids=channel_ids, category=category)

    # === Проксирование методов без задержки ===

    def get_channels(self, *args, **kwargs):
        """Получить список чатов (без задержки)"""
        return self.client.get_channels(*args, **kwargs)

    def get_all_channels(self, *args, **kwargs):
        """Получить все чаты (без задержки)"""
        return self.client.get_all_channels(*args, **kwargs)

    def get_messages(self, *args, **kwargs):
        """Получить сообщения (без задержки)"""
        return self.client.get_messages(*args, **kwargs)

    def get_all_messages(self, *args, **kwargs):
        """Получить все сообщения (без задержки)"""
        return self.client.get_all_messages(*args, **kwargs)

    def get_channel_by_id(self, *args, **kwargs):
        """Получить чат по ID (без задержки)"""
        return self.client.get_channel_by_id(*args, **kwargs)

    def get_users(self, *args, **kwargs):
        """Получить инфо о пользователях (без задержки)"""
        return self.client.get_users(*args, **kwargs)

    def create_item_channel(self, *args, **kwargs):
        """Создать чат по объявлению (без задержки)"""
        return self.client.create_item_channel(*args, **kwargs)

    # === Call tracking (без задержки) ===

    def get_call_history(self, *args, **kwargs):
        return self.client.get_call_history(*args, **kwargs)

    def get_all_calls(self, *args, **kwargs):
        return self.client.get_all_calls(*args, **kwargs)

    def download_call_recording(self, *args, **kwargs):
        return self.client.download_call_recording(*args, **kwargs)


# === Пример использования ===

if __name__ == '__main__':
    import sys

    def on_delay(period: str, seconds: float):
        print(f"⏳ Ожидание {seconds:.1f}с ({period})...")

    if len(sys.argv) < 2:
        print("Usage: python humanized_client.py <sessid> [channel_id] [message]")
        print("\nПример:")
        print("  python humanized_client.py 'xxx' 'u2i-yyy' 'Добрый день!'")
        print("\nТекущий период:", TimeWindow.get_current_period())
        sys.exit(1)

    sessid = sys.argv[1]
    client = HumanizedAvitoClient(sessid=sessid, on_delay_start=on_delay)

    print(f"🕐 Текущее время: {datetime.now().strftime('%H:%M:%S')}")
    print(f"📅 Период: {TimeWindow.get_current_period()}")

    if len(sys.argv) >= 4:
        channel_id = sys.argv[2]
        message = sys.argv[3]

        print(f"\n📤 Отправка в {channel_id}: {message[:50]}...")
        result = client.send_message_humanized(channel_id, message)
        print(f"✅ Отправлено: {result}")
    else:
        # Просто показать чаты
        print("\n📥 Загрузка чатов...")
        channels = client.get_channels(limit=5)
        for ch in channels.get('success', {}).get('channels', [])[:5]:
            print(f"  - {ch.get('id')}: {ch.get('info', {}).get('name', 'N/A')}")
