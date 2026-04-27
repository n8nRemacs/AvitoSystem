# Avito_Redroid_Token — Извлечение токенов через Redroid

**Назначение:** Полный набор скриптов и инструкций для запуска Android в Docker (Redroid), маскировки под Google Pixel 6 и извлечения токенов Avito.

**Статус:** working — отлаженный pipeline с пошаговыми bat-скриптами.

**Стек/технологии:** Docker (Redroid), ADB, Python, Frida, Windows bat-скрипты.

## Что внутри

- `scripts/01-07_*.bat` — последовательные шаги: Docker → Redroid → маскировка → Frida → Avito APK → извлечение токенов → полный автозапуск
- `automation/extract_tokens.py` — Python: извлечение токенов из SharedPrefs, сохранение в JSON
- `automation/check_device.py` — проверка что маскировка применена корректно
- `frida_scripts/ssl_unpin.js` — SSL unpinning (упрощённая версия)
- `frida_scripts/http_capture.js` — HTTP capture (упрощённая версия)
- `frida_scripts/shared_prefs.js` — чтение SharedPreferences через Frida
- `config/build.prop.pixel6` — готовый build.prop для маскировки под Pixel 6
- `docker-compose.yml` — Redroid container (Android 13, root, ADB :5555)
- `FULL_DOCUMENTATION.md` — детальная инструкция

## Важно

- Redroid требует Hyper-V / WSL2 на Windows или kvm на Linux
- Авторизация в Avito — ТОЛЬКО ВРУЧНУЮ через scrcpy или VNC (:5900)
- После авторизации обязательно открыть вкладку "Сообщения" — иначе токены не запишутся

## Дубликаты

`frida_scripts/` здесь — упрощённые копии скриптов из корня `AvitoAll/`. Для расширенного захвата использовать корневые скрипты.

`Studio_Token/` — параллельная реализация той же задачи через Android Studio эмулятор вместо Redroid. Функционально эквивалентна.

## Что полезно для V1

`automation/extract_tokens.py` — рабочий парсер SharedPrefs XML в JSON. Используется напрямую для получения начального токена в V1.

## Что НЕ использовать

`README.md` и `FULL_DOCUMENTATION.md` уже содержат полные инструкции. CLAUDE.md — только навигационный указатель.

## Ссылки

- `../Studio_Token/` — аналог для Android Studio эмулятора
- `../Avito_smartFree/token-farm/` — серверная версия для масштабирования
- `../avito-system/part5-token-bridge/SPEC.md` — ТЗ аналогичного компонента
