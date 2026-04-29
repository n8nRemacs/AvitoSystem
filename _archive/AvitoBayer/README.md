# AvitoBayer — MCP Server

MCP-сервер для поиска iPhone под восстановление на Avito.

## Инструменты (11 MCP tools)

### Search (2)
- `search_items` — поиск объявлений по фильтрам
- `get_item_details` — полная карточка объявления

### Messenger (5)
- `get_channels` — список чатов
- `get_messages` — история сообщений
- `send_message` — отправить сообщение
- `create_chat_by_item` — создать чат по объявлению
- `mark_chat_read` — пометить прочитанным
- `get_unread_count` — счётчик непрочитанных

### Leads (3)
- `create_lead` — добавить в shortlist
- `get_leads` — список лидов
- `update_lead` — обновить статус/оценку

## Установка

```bash
pip install -r requirements.txt
cp .env.example .env
# Заполнить .env
```

## Применить миграцию

Выполнить `migration_leads.sql` в Supabase SQL Editor.

## Запуск

```bash
python server.py
```

## Подключение к Claude Code

```json
{
  "mcpServers": {
    "avito-bayer": {
      "command": "python",
      "args": ["C:/Projects/Sync/AvitoSystem/AvitoBayer/server.py"],
      "env": {
        "XAPI_BASE_URL": "https://avito.newlcd.ru/api/v1",
        "XAPI_API_KEY": "...",
        "SUPABASE_URL": "https://bkxpajeqrkutktmtmwui.supabase.co",
        "SUPABASE_KEY": "..."
      }
    }
  }
}
```
