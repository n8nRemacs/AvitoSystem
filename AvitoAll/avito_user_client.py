"""
Avito Messenger & IP Telephony User API Client
Работает с мессенджером и IP-телефонией Avito через User API

=== MESSENGER API (m.avito.ru) ===
- POST /web/1/messenger/getChannels - Получить список чатов
- POST /web/1/messenger/getChannelById - Получить чат по ID
- POST /web/1/messenger/getUserVisibleMessages - Получить сообщения
- POST /web/1/messenger/sendTextMessage - Отправить сообщение
- POST /web/1/messenger/readChats - Пометить как прочитанные
- POST /web/1/messenger/createItemChannel - Создать чат по объявлению
- POST /web/1/messenger/getUsers - Получить инфо о пользователях
WebSocket: socket.avito.ru (fallback: socket-fallback.avito.ru)

=== IP TELEPHONY API (www.avito.ru) ===
- POST /web/1/calltracking-pro/history - История звонков
- GET  /web/1/calltracking-pro/audio?historyId={id} - Скачать запись звонка

Использование:
1. Залогиньтесь на www.avito.ru в браузере
2. Откройте DevTools (F12) → Application → Cookies
3. Скопируйте значение cookie 'sessid'
4. Запустите нужную команду:

CLI команды:
    # Экспорт чатов мессенджера
    python avito_user_client.py --sessid "xxx" chats

    # Экспорт звонков с записями за год
    python avito_user_client.py --sessid "xxx" calls

    # Экспорт звонков за период без аудио
    python avito_user_client.py --sessid "xxx" calls --from 2024-01-01 --to 2024-12-31 --no-audio

    # Скачать одну запись
    python avito_user_client.py --sessid "xxx" download-call 12345 -o call.mp3

Пример кода:
    client = AvitoMessengerParser(sessid="your_sessid")

    # === MESSENGER ===
    channels = client.get_channels()
    result = client.send_message(channel_id="u2i-xxx", text="Привет!")
    client.read_chats(channel_ids=["u2i-xxx"])

    # === IP TELEPHONY ===
    # Получить историю звонков
    calls = client.get_call_history(date_from="2024-01-01", date_to="2024-12-31")

    # Получить все звонки с пагинацией
    all_calls = client.get_all_calls()

    # Скачать запись звонка
    audio = client.download_call_recording("12345", "call.mp3")

    # Экспортировать все звонки с записями
    stats = client.export_calls_with_recordings(output_dir="avito_calls")
"""

import argparse
import json
import time
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import requests


class AvitoMessengerParser:
    def __init__(self, sessid: str, output_dir: str = "avito_chats"):
        self.session = requests.Session()
        self.session.cookies.set('sessid', sessid)
        self.session.cookies.set('auth', '1')
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
            'Origin': 'https://m.avito.ru',
            'Referer': 'https://m.avito.ru/profile/messenger',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
        })
        self.base_url = 'https://m.avito.ru/web/1/messenger'
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def get_channels(self, limit: int = 30, category: int = 1, offset_timestamp: int = None) -> dict:
        """Получить список чатов"""
        payload = {
            'limit': limit,
            'category': category,
            'filters': {'anyTags': [], 'excludeTags': []}
        }
        if offset_timestamp:
            payload['offsetTimestamp'] = offset_timestamp

        resp = self.session.post(f'{self.base_url}/getChannels', json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_all_channels(self, category: int = 1) -> list:
        """Получить ВСЕ чаты с пагинацией"""
        all_channels = []
        offset = None
        page = 1

        print(f"\n📥 Загрузка чатов (категория {category})...")

        while True:
            try:
                data = self.get_channels(limit=30, category=category, offset_timestamp=offset)
            except requests.exceptions.HTTPError as e:
                print(f"❌ Ошибка HTTP: {e}")
                if e.response.status_code == 401:
                    print("   → Сессия истекла. Получите новый sessid.")
                break
            except Exception as e:
                print(f"❌ Ошибка: {e}")
                break

            success = data.get('success', {})
            channels = success.get('channels', [])

            if not channels:
                break

            all_channels.extend(channels)
            print(f"   Страница {page}: +{len(channels)} чатов (всего: {len(all_channels)})")

            if not success.get('hasMore', False):
                break

            # Берём sortingTimestamp последнего чата как offset
            offset = channels[-1]['sortingTimestamp']
            page += 1

            # Rate limit protection
            time.sleep(1.5)

        return all_channels

    def get_messages(self, channel_id: str, limit: int = 100) -> list:
        """Получить сообщения чата"""
        payload = {
            'channelId': channel_id,
            'limit': limit,
            'order': 0
        }
        resp = self.session.post(f'{self.base_url}/getUserVisibleMessages', json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get('success', {}).get('messages', [])

    def get_all_messages(self, channel_id: str) -> list:
        """Получить ВСЕ сообщения чата (с пагинацией если нужно)"""
        # Пока берём последние 100 сообщений
        # TODO: добавить пагинацию для длинных чатов
        return self.get_messages(channel_id, limit=100)

    # ========== NEW METHODS FROM REVERSE ENGINEERING ==========

    def send_message(self, channel_id: str, text: str, quote_message_id: Optional[str] = None) -> dict:
        """
        Отправить текстовое сообщение в чат

        Args:
            channel_id: ID чата (например, 'u2i-...')
            text: Текст сообщения
            quote_message_id: ID сообщения для цитирования (опционально)

        Returns:
            dict: Ответ API с отправленным сообщением
        """
        payload = {
            'channelId': channel_id,
            'text': text,
            'idempotencyKey': str(uuid.uuid4()),  # UUID для предотвращения дублей
        }

        if quote_message_id:
            payload['quoteMessageId'] = quote_message_id

        resp = self.session.post(f'{self.base_url}/sendTextMessage', json=payload)
        resp.raise_for_status()
        return resp.json()

    def read_chats(self, channel_ids: List[str], category: int = 1) -> dict:
        """
        Пометить чаты как прочитанные

        Args:
            channel_ids: Список ID чатов для пометки
            category: Категория чатов (1=продажи, 2=покупки)

        Returns:
            dict: Ответ API
        """
        payload = {
            'channelIds': channel_ids,
            'category': category
        }

        resp = self.session.post(f'{self.base_url}/readChats', json=payload)
        resp.raise_for_status()
        return resp.json()

    def create_item_channel(self, item_id: str, user_id: str = None) -> dict:
        """
        Создать чат по объявлению

        Args:
            item_id: ID объявления
            user_id: ID пользователя-продавца (опционально)

        Returns:
            dict: Ответ API с информацией о созданном чате
        """
        payload = {
            'itemId': item_id
        }

        if user_id:
            payload['userId'] = user_id

        resp = self.session.post(f'{self.base_url}/createItemChannel', json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_channel_by_id(self, channel_id: str) -> dict:
        """
        Получить информацию о чате по ID

        Args:
            channel_id: ID чата

        Returns:
            dict: Информация о чате
        """
        payload = {
            'channelId': channel_id
        }

        resp = self.session.post(f'{self.base_url}/getChannelById', json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_users(self, user_ids: List[str]) -> dict:
        """
        Получить информацию о пользователях

        Args:
            user_ids: Список ID пользователей

        Returns:
            dict: Информация о пользователях
        """
        payload = {
            'userIds': user_ids
        }

        resp = self.session.post(f'{self.base_url}/getUsers', json=payload)
        resp.raise_for_status()
        return resp.json()

    # ========== IP TELEPHONY (CALL TRACKING) API ==========

    def get_call_history(
        self,
        date_from: str = None,
        date_to: str = None,
        limit: int = 20,
        offset: int = 0,
        sorting_field: str = "createTime",
        sorting_direction: str = "desc",
        new_or_repeated: str = "all",
        received_or_missed: str = "all",
        show_spam: bool = True,
        item_filters: dict = None
    ) -> dict:
        """
        Получить историю звонков IP-телефонии Avito

        Args:
            date_from: Начало периода (YYYY-MM-DD), по умолчанию год назад
            date_to: Конец периода (YYYY-MM-DD), по умолчанию сегодня
            limit: Количество записей (по умолчанию 20)
            offset: Смещение для пагинации
            sorting_field: Поле сортировки (createTime)
            sorting_direction: Направление (desc/asc)
            new_or_repeated: Фильтр: all/new/repeated
            received_or_missed: Фильтр: all/received/missed
            show_spam: Показывать спам-звонки
            item_filters: Фильтры по объявлениям

        Returns:
            dict: {
                'result': {
                    'items': [...],  # список звонков
                    'total': int     # общее количество
                },
                'status': 'success'
            }

        Структура записи звонка:
            - id: ID звонка (для скачивания записи)
            - caller: номер звонившего
            - receiver: номер принявшего
            - duration: длительность "M:SS"
            - hasRecord: есть ли запись
            - createTime: время звонка (ISO)
            - waitingTime: время ожидания
            - isNew, isSpamTagged, isCallback и др.
        """
        from datetime import datetime, timedelta

        # Дефолтные даты - последний год
        if not date_to:
            date_to = datetime.now().strftime('%Y-%m-%d')
        if not date_from:
            date_from = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

        payload = {
            'dateFrom': date_from,
            'dateTo': date_to,
            'limit': limit,
            'offset': offset,
            'sortingField': sorting_field,
            'sortingDirection': sorting_direction,
            'newOrRepeated': new_or_repeated,
            'receivedOrMissed': received_or_missed,
            'showSpam': show_spam,
            'itemFilters': item_filters or {}
        }

        # Calltracking API использует www.avito.ru, не m.avito.ru
        url = 'https://www.avito.ru/web/1/calltracking-pro/history'

        resp = self.session.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_all_calls(
        self,
        date_from: str = None,
        date_to: str = None,
        **kwargs
    ) -> list:
        """
        Получить ВСЕ звонки за период с автоматической пагинацией

        Args:
            date_from: Начало периода (YYYY-MM-DD)
            date_to: Конец периода (YYYY-MM-DD)
            **kwargs: Дополнительные параметры для get_call_history

        Returns:
            list: Все записи звонков
        """
        all_calls = []
        offset = 0
        limit = 50  # Максимум за раз
        page = 1

        print(f"\n📞 Загрузка истории звонков...")

        while True:
            try:
                data = self.get_call_history(
                    date_from=date_from,
                    date_to=date_to,
                    limit=limit,
                    offset=offset,
                    **kwargs
                )
            except requests.exceptions.HTTPError as e:
                print(f"❌ Ошибка HTTP: {e}")
                if e.response.status_code == 401:
                    print("   → Сессия истекла. Получите новый sessid.")
                break
            except Exception as e:
                print(f"❌ Ошибка: {e}")
                break

            result = data.get('result', {})
            items = result.get('items', [])
            total = result.get('total', 0)

            if not items:
                break

            all_calls.extend(items)
            print(f"   Страница {page}: +{len(items)} звонков (всего: {len(all_calls)}/{total})")

            if len(all_calls) >= total:
                break

            offset += limit
            page += 1
            time.sleep(1)  # Rate limit

        print(f"✅ Загружено {len(all_calls)} звонков")
        return all_calls

    def download_call_recording(self, call_id: str, output_path: str = None) -> bytes:
        """
        Скачать запись звонка

        Args:
            call_id: ID звонка из истории (поле 'id')
            output_path: Путь для сохранения файла (опционально)

        Returns:
            bytes: Аудио-данные записи

        Example:
            # Получить запись
            audio = client.download_call_recording("12345")

            # Или сразу сохранить в файл
            client.download_call_recording("12345", "call_12345.mp3")
        """
        url = f'https://www.avito.ru/web/1/calltracking-pro/audio?historyId={call_id}'

        resp = self.session.get(url, stream=True)
        resp.raise_for_status()

        audio_data = resp.content

        if output_path:
            with open(output_path, 'wb') as f:
                f.write(audio_data)
            print(f"✅ Запись сохранена: {output_path}")

        return audio_data

    def export_calls_with_recordings(
        self,
        date_from: str = None,
        date_to: str = None,
        output_dir: str = "avito_calls",
        download_audio: bool = True
    ) -> dict:
        """
        Экспортировать все звонки с записями

        Args:
            date_from: Начало периода
            date_to: Конец периода
            output_dir: Папка для сохранения
            download_audio: Скачивать аудио-записи

        Returns:
            dict: Статистика экспорта
        """
        from pathlib import Path

        out_path = Path(output_dir)
        out_path.mkdir(exist_ok=True)

        # Получаем все звонки
        calls = self.get_all_calls(date_from=date_from, date_to=date_to)

        # Сохраняем JSON
        calls_file = out_path / f"calls_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(calls_file, 'w', encoding='utf-8') as f:
            json.dump({
                'exported_at': datetime.now().isoformat(),
                'date_from': date_from,
                'date_to': date_to,
                'total': len(calls),
                'calls': calls
            }, f, ensure_ascii=False, indent=2)
        print(f"📋 Список звонков: {calls_file}")

        # Скачиваем записи
        downloaded = 0
        skipped = 0
        errors = 0

        if download_audio:
            audio_dir = out_path / "recordings"
            audio_dir.mkdir(exist_ok=True)

            for i, call in enumerate(calls, 1):
                call_id = call.get('id')
                has_record = call.get('hasRecord', False)

                if not has_record:
                    skipped += 1
                    continue

                # Формируем имя файла
                create_time = call.get('createTime', '')[:10]  # YYYY-MM-DD
                caller = call.get('caller', 'unknown').replace('+', '')
                duration = call.get('duration', '0-00').replace(':', '-')
                filename = f"{create_time}_{caller}_{duration}_{call_id}.mp3"
                filepath = audio_dir / filename

                if filepath.exists():
                    print(f"   [{i}/{len(calls)}] Пропуск (уже есть): {filename}")
                    downloaded += 1
                    continue

                try:
                    print(f"   [{i}/{len(calls)}] Скачиваю: {filename}")
                    self.download_call_recording(call_id, str(filepath))
                    downloaded += 1
                    time.sleep(0.5)  # Rate limit
                except Exception as e:
                    print(f"      ❌ Ошибка: {e}")
                    errors += 1

        stats = {
            'total_calls': len(calls),
            'with_recording': sum(1 for c in calls if c.get('hasRecord')),
            'downloaded': downloaded,
            'skipped': skipped,
            'errors': errors
        }

        print(f"\n📊 Статистика:")
        print(f"   Всего звонков: {stats['total_calls']}")
        print(f"   С записью: {stats['with_recording']}")
        print(f"   Скачано: {stats['downloaded']}")
        print(f"   Ошибок: {stats['errors']}")

        return stats

    def parse_timestamp(self, ns_timestamp: int) -> str:
        """Конвертировать наносекунды в читаемую дату"""
        if not ns_timestamp:
            return None
        seconds = ns_timestamp / 1_000_000_000
        return datetime.fromtimestamp(seconds).strftime('%Y-%m-%d %H:%M:%S')

    def extract_channel_info(self, channel: dict) -> dict:
        """Извлечь полезную информацию из чата"""
        info = channel.get('info', {})
        details = info.get('details', {})
        last_msg = channel.get('lastMessage', {})
        users = channel.get('users', [])

        # Найти собеседника (не себя)
        other_user = None
        for user in users:
            if user.get('id') != channel.get('userId'):
                other_user = user
                break

        return {
            'id': channel.get('id'),
            'type': 'item' if channel.get('id', '').startswith('u2i-') else 'support',
            'created': self.parse_timestamp(channel.get('created')),
            'updated': self.parse_timestamp(channel.get('updated')),
            'is_read': channel.get('isRead', False),
            'is_answered': channel.get('isAnswered', False),
            # Информация об объявлении
            'item_id': details.get('itemId'),
            'item_title': details.get('title'),
            'item_url': details.get('url'),
            'item_price': details.get('price'),
            'item_image': details.get('images', [None])[0] if details.get('images') else None,
            # Контакт
            'contact_name': other_user.get('name') if other_user else info.get('name'),
            'contact_id': other_user.get('id') if other_user else None,
            'last_message_text': last_msg.get('body', {}).get('text', {}).get('text'),
            'last_message_date': self.parse_timestamp(last_msg.get('createdAt')),
        }

    def extract_message_info(self, message: dict, my_user_id: str) -> dict:
        """Извлечь полезную информацию из сообщения"""
        body = message.get('body', {})
        text_obj = body.get('text', {})
        is_mine = message.get('authorId') == my_user_id
        read_at = message.get('readAt')

        # Определяем тип сообщения и извлекаем медиа
        msg_type = 'text'
        media_url = None
        media_info = {}

        if body.get('image'):
            msg_type = 'image'
            img = body['image']
            media_url = img.get('url') or img.get('imageUrl')
            media_info = {
                'image_id': img.get('imageId'),
                'width': img.get('width'),
                'height': img.get('height'),
            }
        elif body.get('voice'):
            msg_type = 'voice'
            voice = body['voice']
            media_info = {
                'voice_id': voice.get('voiceId'),
                'duration': voice.get('duration'),
            }
        elif body.get('video'):
            msg_type = 'video'
            video = body['video']
            media_info = {
                'video_id': video.get('videoId'),
                'file_id': video.get('fileId'),
            }
        elif body.get('file'):
            msg_type = 'file'
            file = body['file']
            media_info = {
                'file_id': file.get('fileId'),
                'file_name': file.get('name'),
                'file_size': file.get('size'),
            }
        elif body.get('location'):
            msg_type = 'location'
            loc = body['location']
            media_info = {
                'lat': loc.get('lat'),
                'lon': loc.get('lon'),
                'address': loc.get('address'),
            }

        return {
            'id': message.get('id'),
            'date': self.parse_timestamp(message.get('createdAt')),
            'is_mine': is_mine,
            'author_id': message.get('authorId'),
            'type': msg_type,
            'text': text_obj.get('text') if isinstance(text_obj, dict) else str(text_obj),
            'media_url': media_url,
            'media_info': media_info if media_info else None,
            'is_first': message.get('isFirstMessage', False),
            'read_at': self.parse_timestamp(read_at),
            # Статус прочтения (для исходящих сообщений)
            'is_read': read_at is not None if is_mine else None,  # True = ✓✓, False = ✓
            'status': '✓✓' if (is_mine and read_at) else ('✓' if is_mine else None),
        }

    def parse_all(self, categories: list = [1, 2], save_raw: bool = False):
        """Спарсить все чаты и сообщения"""
        all_data = {
            'parsed_at': datetime.now().isoformat(),
            'chats': []
        }

        # Собираем чаты из всех категорий
        all_channels = []
        for cat in categories:
            channels = self.get_all_channels(category=cat)
            all_channels.extend(channels)
            time.sleep(1)

        # Убираем дубликаты по ID
        seen_ids = set()
        unique_channels = []
        for ch in all_channels:
            if ch['id'] not in seen_ids:
                seen_ids.add(ch['id'])
                unique_channels.append(ch)

        print(f"\n📊 Найдено {len(unique_channels)} уникальных чатов")
        print(f"\n💬 Загрузка сообщений...")

        # Определяем свой user_id из первого чата
        my_user_id = unique_channels[0].get('userId') if unique_channels else None

        for i, channel in enumerate(unique_channels, 1):
            channel_info = self.extract_channel_info(channel)
            print(f"   [{i}/{len(unique_channels)}] {channel_info['contact_name'] or 'Unknown'}: {channel_info['item_title'] or 'N/A'}")

            try:
                messages = self.get_all_messages(channel['id'])
                channel_info['messages'] = [
                    self.extract_message_info(msg, my_user_id)
                    for msg in messages
                ]
                channel_info['message_count'] = len(messages)
            except Exception as e:
                print(f"      ⚠️ Ошибка загрузки сообщений: {e}")
                channel_info['messages'] = []
                channel_info['message_count'] = 0
                channel_info['error'] = str(e)

            if save_raw:
                channel_info['_raw'] = channel

            all_data['chats'].append(channel_info)

            # Rate limit
            time.sleep(1)

        # Сохраняем результат
        output_file = self.output_dir / f"avito_chats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)

        print(f"\n✅ Готово! Сохранено в: {output_file}")
        print(f"   Чатов: {len(all_data['chats'])}")
        print(f"   Сообщений: {sum(ch['message_count'] for ch in all_data['chats'])}")

        # Также сохраняем в читаемом формате
        self.save_readable(all_data)

        return all_data

    def save_readable(self, data: dict):
        """Сохранить в читаемом текстовом формате"""
        output_file = self.output_dir / f"avito_chats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"AVITO CHATS EXPORT\n")
            f.write(f"Дата экспорта: {data['parsed_at']}\n")
            f.write(f"Всего чатов: {len(data['chats'])}\n")
            f.write("=" * 80 + "\n\n")

            for chat in data['chats']:
                f.write(f"{'=' * 80}\n")
                f.write(f"ЧАТ: {chat['contact_name'] or 'Unknown'}\n")
                f.write(f"Объявление: {chat['item_title'] or 'N/A'}\n")
                f.write(f"Создан: {chat['created']}\n")
                f.write(f"Обновлён: {chat['updated']}\n")
                f.write(f"Сообщений: {chat['message_count']}\n")
                f.write("-" * 80 + "\n\n")

                # Сообщения в хронологическом порядке
                for msg in reversed(chat.get('messages', [])):
                    sender = "Я" if msg['is_mine'] else chat['contact_name']
                    status = f" {msg.get('status', '')}" if msg.get('status') else ""
                    msg_type = msg.get('type', 'text')
                    type_icon = {'image': '📷', 'voice': '🎤', 'video': '🎬', 'file': '📎', 'location': '📍'}.get(msg_type, '')
                    f.write(f"[{msg['date']}] {sender}:{status} {type_icon}\n")
                    if msg['text']:
                        f.write(f"  {msg['text']}\n")
                    if msg.get('media_url'):
                        f.write(f"  🔗 {msg['media_url']}\n")
                    if msg.get('media_info'):
                        f.write(f"  📦 {msg['media_info']}\n")
                    f.write("\n")

                f.write("\n")

        print(f"   Читаемый формат: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Avito Messenger & Calls Parser')
    parser.add_argument('--sessid', required=True, help='Cookie sessid из браузера')
    parser.add_argument('--output', default='avito_chats', help='Папка для результатов')

    subparsers = parser.add_subparsers(dest='command', help='Команды')

    # Команда: chats - парсинг чатов
    chats_parser = subparsers.add_parser('chats', help='Экспорт чатов мессенджера')
    chats_parser.add_argument('--categories', default='1,2', help='Категории чатов (1=продажи, 2=покупки)')
    chats_parser.add_argument('--raw', action='store_true', help='Сохранять сырые данные')

    # Команда: calls - экспорт звонков
    calls_parser = subparsers.add_parser('calls', help='Экспорт истории звонков IP-телефонии')
    calls_parser.add_argument('--from', dest='date_from', help='Начало периода (YYYY-MM-DD)')
    calls_parser.add_argument('--to', dest='date_to', help='Конец периода (YYYY-MM-DD)')
    calls_parser.add_argument('--no-audio', action='store_true', help='Не скачивать аудио-записи')

    # Команда: download-call - скачать одну запись
    download_parser = subparsers.add_parser('download-call', help='Скачать запись конкретного звонка')
    download_parser.add_argument('call_id', help='ID звонка')
    download_parser.add_argument('--output-file', '-o', help='Имя файла для сохранения')

    args = parser.parse_args()

    # По умолчанию - chats
    if not args.command:
        args.command = 'chats'
        args.categories = '1,2'
        args.raw = False

    client = AvitoMessengerParser(sessid=args.sessid, output_dir=args.output)

    if args.command == 'chats':
        categories = [int(c) for c in args.categories.split(',')]
        print("🚀 Avito Messenger Parser")
        print(f"   Output: {args.output}/")
        print(f"   Categories: {categories}")
        client.parse_all(categories=categories, save_raw=args.raw)

    elif args.command == 'calls':
        print("📞 Avito Calls Exporter")
        print(f"   Output: {args.output}/")
        print(f"   Period: {args.date_from or 'last year'} - {args.date_to or 'today'}")
        print(f"   Download audio: {not args.no_audio}")
        client.export_calls_with_recordings(
            date_from=args.date_from,
            date_to=args.date_to,
            output_dir=args.output,
            download_audio=not args.no_audio
        )

    elif args.command == 'download-call':
        output_file = args.output_file or f"call_{args.call_id}.mp3"
        print(f"📥 Скачиваю запись звонка {args.call_id}...")
        client.download_call_recording(args.call_id, output_file)


if __name__ == '__main__':
    main()
