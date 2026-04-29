# avito-farm-agent

**Назначение:** Python+JS агент для запуска на рутованном Android-устройстве. Перехватывает JWT-токены Avito через Frida, отправляет их в avito-xapi. Обеспечивает автоматическое обновление токенов.

**Статус:** prototype. Работает при наличии рутованного Android + Frida + Redroid. Используется как часть token farm.

**Стек:** Python 3 (requests, без async), JavaScript (Frida hooks), apktool, mitmproxy.

---

## Структура

- `agent.py` — основной daemon. Heartbeat → xapi `/farm/heartbeat`, опрос расписания, запуск Avito, Frida-захват токена, отправка в xapi `/farm/tokens`
- `config.json` — конфиг агента: `xapi_url`, `api_key`, `device_name`, интервалы
- `grab_token.js` — Frida script: перехват JWT из SharedPreferences Avito
- `spoof_fingerprint.js` — Frida: подмена device fingerprint (per-profile идентичность)
- `ssl_bypass.js`, `anti_detect.js` — SSL pinning bypass + анти-детект
- `apk_work/` — avito.apk, patched APK с Frida gadget, `libfrida-gadget.so`. Бинарники, не трогать
- `mitm_output/`, `sniff_output.log`, `*.pcap`, `*.mitm` — захваченный трафик. Только данные
- `patch_apk.py`, `sign_apk.py`, `zipalign.py` — инструменты патчинга APK

---

## Точки входа

```bash
# На Android-устройстве (Termux + root)
python agent.py

# Перехват fingerprint (на ПК с ADB)
python scan_fingerprint.py

# mitmproxy снифф
python run_mitm.py
```

---

## Связи

- **Отправляет токены** в `avito-xapi` `POST /api/v1/farm/tokens`
- **Получает расписание** из `GET /api/v1/farm/schedule`
- **Конфиг** `config.json` — `xapi_url` указывает на `https://avito.newlcd.ru`

---

## Конвенции / предупреждения

- `apk_work/` — содержит бинарники (.apk, .so). Не добавлять в git
- Агент работает как root на Android — запускается через `adb shell` или `systemd` в Termux
- `refresh.sh` — shell-скрипт для cron на устройстве

---

## Связано с ТЗ V1

Раздел 6 ТЗ (Token Farm): агент — это "клиент фермы" на устройстве. В V1 farm-роутер уже реализован в xapi (`routers/farm.py`). Агент переиспользуется без изменений.
