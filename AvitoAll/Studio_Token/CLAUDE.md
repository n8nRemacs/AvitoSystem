# Studio_Token — Извлечение токенов через Android Studio Emulator

**Назначение:** Аналог `Avito_Redroid_Token/`, но использует Android Studio AVD (QEMU-эмулятор) вместо Redroid. Маскировка под Pixel 6, Frida-скрипты, bat-автоматизация.

**Статус:** working — рабочий pipeline, но требует установленного Android Studio.

**Стек/технологии:** Android Studio AVD, ADB, Frida, Python, Windows bat-скрипты.

## Что внутри

- `scripts/01-07_*.bat` — те же шаги что и в `Avito_Redroid_Token/scripts/`
- `frida_scripts/ssl_unpin.js`, `http_capture.js`, `shared_prefs.js` — упрощённые копии корневых Frida-скриптов
- `frida_scripts/build_mask.js` — маскировка build properties через Frida (без изменения build.prop)
- `check_token_status.py` — показывает время до истечения токена
- `check_device_info.py` — проверка что маскировка применена

## Отличие от Avito_Redroid_Token

| | Studio_Token | Avito_Redroid_Token |
|--|--------------|---------------------|
| Движок | QEMU (Android Studio AVD) | Docker (Redroid) |
| Требования | Android Studio | Docker Desktop + Hyper-V/WSL2 |
| Масштабирование | Сложно (один AVD) | Легко (docker-compose scale) |
| Маскировка build.prop | Через Frida | Через docker build.prop mount |

## Что полезно для V1

`frida_scripts/build_mask.js` — маскировка через Frida (runtime подмена Build properties) в отличие от статического build.prop. Полезно для эмулятора без root.

## Что НЕ использовать

Функционально дубликат `Avito_Redroid_Token/`. Если оба набора скриптов доступны — предпочесть Redroid для серверного использования.

## Ссылки

- `../Avito_Redroid_Token/` — предпочтительный вариант для сервера
- Корневые Frida-скрипты (`../ssl_simple.js`, `../http_capture.js`) — полные версии
