# 10 — Avito web URL `f=AS...` blob decoder

**Создано:** 2026-05-08
**Статус:** verified empirically against 3 known URLs (см. §3).
**Реализация:** `avito-monitor/app/services/avito_blob_decoder.py`

---

## §1. Что это и зачем

Avito прячет structured-search фильтры в URL'ах в виде binary blob, закодированного URL-safe base64. Примеры:

```
/astrahan/telefony/mobile-ASgBAgICAUSwwQ2I_Dc                                       ← все телефоны
/astrahan/telefony/mobilnye_telefony/apple-ASgBAgICAkS0wA3OqzmwwQ2I_Dc               ← все Apple
/astrahan/telefony/mobilnye_telefony/apple/iphone_13-ASgBAgICA0SywA3svcgBtMANzqs5sMENiPw3   ← iPhone 13
```

Часть после последнего `-` — это и есть blob. Если его декодировать, получим список пар `(param_id, value)` — точно таких же, какие mobile API ждёт в строке `params[<param_id>][0]=<value>`.

**Зачем декодировать:** юзер кликает фильтры в браузере → копирует URL → мы автоматически добываем `param_id`+`value` для каталога. Не нужно обращаться к закрытому endpoint `/16/dicts/parameters` (см. `06-structured-params-discovery.md`) и сжигать JWT.

---

## §2. Формат

После URL-safe base64-декодирования получается binary stream:

| Байты | Что | Пример |
|---|---|---|
| `01 28 01 02 02 02` | Constant header (не меняется между URL'ами) | — |
| `0X 44` | `X` = количество filter pairs (1, 2, 3, …) | `01 44`, `02 44`, `03 44` |
| `varintₐ varint_b` | Pair: (param_id × 2, value × 2) — оба LEB128, little-endian | `b0c10d 88fc37` |
| … | (повторяется X раз) | — |

**Каждое поле — varint в LEB128 (Protocol Buffers стиль)**: 7 бит данных + старший бит "continuation". Little-endian (младшие байты первыми).

**Числа умножены на 2** — это zigzag-style protobuf encoding для signed varints (Avito пишет всё через protobuf-runtime, поэтому формат «варинт ÷ 2 = исходное значение» сохраняется автоматически).

---

## §3. Verified examples (decoded by hand)

### `ASgBAgICAUSwwQ2I_Dc` — все телефоны

```
hex: 0128010202020144 b0c10d 88fc37
     └─ header ──┘└─ X=1 + 0x44
                            ↓
              pair: (0xd_41_30/2, 0x37_7c_08/2) = (110680, 458500)
                    = (Тип товара, "Мобильные телефоны")
```

### `ASgBAgICAkS0wA3OqzmwwQ2I_Dc` — все Apple

```
hex: 0128010202020244 b4c00d ceab39 b0c10d 88fc37
     └─ header ──┘└─ X=2 + 0x44
                            ↓
              pair 1: (0xd_40_34/2, 0x39_2b_4e/2) = (110618, 469735) = Apple
              pair 2: (110680, 458500) = "Мобильные телефоны"
```

### `ASgBAgICA0SywA3svcgBtMANzqs5sMENiPw3` — iPhone 13

```
hex: 0128010202020344 b2c00d ecbdc801 b4c00d ceab39 b0c10d 88fc37
     └─ header ──┘└─ X=3 + 0x44
              pair 1: (0xd_40_32/2, 0x01_48_3d_6c/2) = (110617, 1642358) = iPhone 13
              pair 2: (110618, 469735) = Apple
              pair 3: (110680, 458500) = "Мобильные телефоны"
```

Implicit фильтры (бренд, тип) **встроены в каждый blob**, даже если юзер их явно не выбирал — Avito navigationally наследует их от parent-категории в URL.

---

## §4. Decode pseudocode

```python
import base64

def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    """Read one LEB128 varint starting at buf[i]. Returns (value, new_i)."""
    val, shift = 0, 0
    while True:
        b = buf[i]
        val |= (b & 0x7F) << shift
        i += 1
        if not (b & 0x80):
            return val, i
        shift += 7

def decode_avito_blob(blob: str) -> list[tuple[int, int]]:
    pad = "=" * (-len(blob) % 4)
    data = base64.urlsafe_b64decode(blob + pad)
    # data[0:6] = constant header `01 28 01 02 02 02`
    # data[6]   = pair count X
    # data[7]   = 0x44 marker
    count = data[6]
    i = 8
    pairs: list[tuple[int, int]] = []
    for _ in range(count):
        a, i = _read_varint(data, i)
        b, i = _read_varint(data, i)
        pairs.append((a // 2, b // 2))
    return pairs
```

---

## §5. Применение в нашей системе

1. **Catalog mining**: юзер копирует web-URL'ы для каждого known filter combination (Apple+iPhone 13, Apple+iPhone 14, Memory=128GB, Color=Black, …) → decoder извлекает `(param_id, value)` пары → они сохраняются в `avito_param_catalog` table с `human_name` из URL slug'а.

2. **URL-based search**: profile хранит URL Avito (ADR-001). При polling:
   - `parse_avito_url(url)` извлекает blob из slug'а
   - `decode_avito_blob(blob)` даёт structured pairs
   - Передаём в xapi `extra_params={110617: 1642358, 110618: 469735, …}`
   - xapi форвардит в Avito API как `params[110617][0]=1642358&...`
   - Получаем precise результаты (не fuzzy text+post-filter)

3. **Не-phone категории**: формат универсален — работает для машин, ноутбуков, etc. Param-IDs другие, но decoder тот же.

---

## §6. Ограничения

- Header `01 28 01 02 02 02` подтверждён только на 3 URL'ах. Если у других URL'ов он отличается — нужен fallback.
- Marker `0x44` после count — назначение неизвестно. Может оказаться частью более сложной структуры в URL'ах с group-фильтрами (например, диапазоны цен внутри blob'а — пока не встречали).
- Location в blob НЕ кодируется — только в URL slug (например, `/astrahan/`). Для location-id нужен отдельный mapping (есть в `app/data/avito_regions.json`).
- Free-text query (`?q=...`) хранится отдельно от blob.

---

## §7. Reference

- `DOCS/REFERENCE/05-search-query-formation.md` — общий контекст web ↔ mobile mismatch
- `DOCS/REFERENCE/06-structured-params-discovery.md` — альтернативные пути добычи catalog (subscription mining, /dicts/parameters POST)
- `DOCS/avito_api_snapshots/iphone_models.json` — текущий каталог iPhone моделей (50 штук + Apple + type)
- `avito-monitor/app/services/avito_blob_decoder.py` — реализация
- `avito-monitor/tests/services/test_avito_blob_decoder.py` — тесты на эти 3 URL'а
