# tenant-auth / src / providers

**Назначение:** Провайдеры доставки OTP-кодов. Стратегия-паттерн.

**Статус:** WIP. Реализованы заглушки, production-ready только console и частично telegram.

---

## Файлы

- `base.py` — `OtpProvider` ABC: `send_otp(target, code, purpose) → bool`, свойство `channel`
- `console.py` — dev-провайдер, печатает OTP в stdout. Для локальной разработки
- `email_provider.py` — отправка OTP на email
- `sms.py` — отправка через SMS-шлюз
- `telegram.py` — отправка через Telegram-бот (через SOCKS5 прокси)
- `vk_max.py` — VK Messenger
- `whatsapp.py` — WhatsApp Business API

---

## Конвенции

- Все провайдеры регистрируются в `otp_service.py` по ключу `channel`
- `telegram.py` должен использовать SOCKS5 `127.0.0.1:1080` (api.telegram.org заблокирован в РФ)
- В dev-режиме достаточно `console` провайдера — не нужно настраивать SMS/email
