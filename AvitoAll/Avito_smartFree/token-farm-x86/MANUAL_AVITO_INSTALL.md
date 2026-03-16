# Manual Avito APK Installation Guide

Автоматическое скачивание APK не работает из-за ограничений APK сайтов. Нужна ручная установка.

## Вариант 1: Скачать и загрузить на сервер (Windows)

### Шаг 1: Скачать APK

Скачай Avito APK с одного из источников:

**APKMirror (рекомендую):**
1. Открой: https://www.apkmirror.com/apk/avito/avito/
2. Выбери последнюю версию (например, Avito 12.34.0)
3. Нажми "Download APK"
4. Скачай файл (обычно ~80-100 MB)

**APKPure:**
1. Открой: https://apkpure.com/ru/avito/com.avito.android
2. Нажми "Скачать APK"
3. Скачай файл

**Важно:** Скачивай базовый APK, не split APKs (не XAPK bundle)!

### Шаг 2: Загрузить на сервер

Открой PowerShell/CMD в папке со скачанным APK:

```powershell
# Если файл называется com.avito.android_12.34.0-apk.apk
scp com.avito.android*.apk root@85.198.98.104:/tmp/avito_latest.apk
```

### Шаг 3: Установить на сервере

```bash
ssh root@85.198.98.104
cd /root/avito-token-farm-x86
bash install_avito.sh
```

---

## Вариант 2: Использовать существующий APK (если есть)

Если у тебя уже есть Avito APK (например, с рутованного телефона):

### Извлечь APK с устройства

```bash
# На устройстве или через ADB
adb shell pm path com.avito.android
# Output: package:/data/app/~~xxx/com.avito.android-yyy/base.apk

# Скачать
adb pull /data/app/~~xxx/com.avito.android-yyy/base.apk avito_from_phone.apk

# Загрузить на сервер
scp avito_from_phone.apk root@85.198.98.104:/tmp/avito_latest.apk
```

---

## Вариант 3: Прямое скачивание (если знаешь URL)

Если есть прямая ссылка на APK:

```bash
ssh root@85.198.98.104

# Скачать напрямую
wget -O /tmp/avito_latest.apk "DIRECT_URL_HERE"

# Или через curl
curl -L -o /tmp/avito_latest.apk "DIRECT_URL_HERE"

# Установить
cd /root/avito-token-farm-x86
bash install_avito.sh
```

---

## После установки

### Проверка

```bash
ssh root@85.198.98.104

# Проверить что установлено
docker exec redroid-x86-1 sh -c "pm list packages | grep avito"
# Output: package:com.avito.android

# Версия
docker exec redroid-x86-1 sh -c "dumpsys package com.avito.android | grep versionName"
```

### Запуск приложения

```bash
# Запустить Avito
docker exec redroid-x86-1 sh -c "am start -n com.avito.android/.main.MainActivity"

# Подождать 5 секунд, затем сделать скриншот
sleep 5
docker exec redroid-x86-1 sh -c "screencap -p" > /tmp/avito_screen.png

# Скачать скриншот на компьютер
scp root@85.198.98.104:/tmp/avito_screen.png .
```

### Мониторинг логов

```bash
# Смотреть логи Avito в реальном времени
docker exec redroid-x86-1 sh -c "logcat | grep -i avito"
```

---

## Проблемы и решения

### APK не устанавливается

```bash
# Ошибка: INSTALL_FAILED_UPDATE_INCOMPATIBLE
# Решение: Удалить старую версию
docker exec redroid-x86-1 sh -c "pm uninstall com.avito.android"

# Ошибка: INSTALL_FAILED_INVALID_APK
# Решение: APK поврежден или это XAPK bundle
# Скачай другую версию или используй базовый APK
```

### APK слишком большой

Если APK > 200 MB, скорее всего это XAPK (bundle). Нужен базовый APK.

На APKMirror выбирай файлы с типом "APK", а не "APK Bundle" или "XAPK".

---

## Быстрая команда (после скачивания)

```bash
# Все в одной команде (после того как скачал APK в Downloads)
cd ~/Downloads
scp com.avito.android*.apk root@85.198.98.104:/tmp/avito_latest.apk && ssh root@85.198.98.104 "cd /root/avito-token-farm-x86 && bash install_avito.sh"
```

---

## Следующие шаги

После успешной установки:

1. ✅ Запустить приложение
2. 📱 Пройти авторизацию (нужен номер телефона + SMS код)
3. 🔍 Проверить SharedPreferences
4. 💾 Извлечь session token и fingerprint
5. 🔄 Протестировать активное обновление токена

Следуй инструкции в `TEST_AUTHORIZATION.md` (будет создана после установки APK).
