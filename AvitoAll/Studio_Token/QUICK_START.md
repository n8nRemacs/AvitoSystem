# ⚡ Быстрый старт - 5 минут до первых токенов

## 🎯 Цель
Извлечь токены Avito из эмулятора Android Studio максимально быстро.

---

## Предварительные условия

✅ Android Studio установлена
✅ Python 3.8+ установлен
✅ AVD уже создан (Pixel 6, API 33, Google APIs)
✅ Avito уже установлен и авторизован на эмуляторе

---

## 🚀 Шаги (5 минут)

### 1. Запустите эмулятор (1 минута)

**Через Android Studio:**
- Device Manager → avito_token_emulator → ▶️ Play

**Или через CMD:**
```cmd
cd C:\Users\Dimon\Pojects\Reverce\APK\Avito\Studio_Token\scripts
02_start_emulator.bat
```

Дождитесь полной загрузки (~30 секунд).

---

### 2. Примените маскировку (30 секунд)

```cmd
03_mask_device.bat
```

Это изменит Build properties чтобы Avito видел "Pixel 6" вместо "sdk_gphone64_x86_64".

---

### 3. Извлеките токены (1 минута)

```cmd
06_extract_tokens.bat
```

**Результат:** Файл `output/session_[timestamp].json` создан!

---

### 4. Проверьте результат (30 секунд)

```cmd
cd ../output
dir /O-D session_*.json
```

Откройте последний файл - там все токены:

```json
{
  "session_token": "eyJhbGci...",
  "refresh_token": "b026b73d...",
  "fingerprint": "A2.588e8ee...",
  "device_id": "050825b7f6c5255f",
  "user_id": 157920214,
  "expires_at": 1769524040
}
```

---

### 5. (Опционально) Автообновление (2 минуты)

```cmd
cd ../scripts
07_auto_refresh.bat
```

Токены будут обновляться автоматически каждый час.

---

## ✅ Готово!

Теперь у вас есть рабочие токены Avito.

**Используйте их в коде:**

```python
import json
import requests

# Загрузить токены
with open('output/session_20260126_083000.json', 'r') as f:
    s = json.load(f)

# API запрос
headers = {
    "X-Session": s['session_token'],
    "f": s['fingerprint'],
    "X-DeviceId": s['device_id']
}

response = requests.get(
    "https://api.avito.ru/messenger/v3/channels",
    headers=headers
)

print(f"Чатов: {len(response.json()['channels'])}")
```

---

## 🔄 В следующий раз

```cmd
# 1. Запустить эмулятор
02_start_emulator.bat

# 2. Извлечь токены
06_extract_tokens.bat

# Готово за 2 минуты!
```

---

## 📖 Нужны детали?

Смотрите **README.md** для полной инструкции со всеми деталями, настройками и решением проблем.

---

**⏱️ Общее время: ~5 минут**

*Если эмулятор уже настроен - всего 2 минуты!*
