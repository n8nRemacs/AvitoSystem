# Avito Official API — Snapshots

Реальные ответы официального API Avito, снятые 2026-04-25 для категории «Мобильная техника» V1.

## Файлы

| Файл | Endpoint | Размер | Описание |
|---|---|---|---|
| `categories_tree.json` | `GET /autoload/v1/user-docs/tree` | 222 KB | Полное дерево категорий Avito (slug + name + nested) |
| `fields_mobilnye_telefony.json` | `GET /autoload/v1/user-docs/node/mobilnye_telefony/fields` | 58 KB | Поля для категории «Мобильные телефоны» (57 полей) |
| `fields_plansety.json` | `.../plansety/fields` | 59 KB | Планшеты (56 полей) |
| `fields_nausniki.json` | `.../nausniki/fields` | 44 KB | Наушники аудио (38 полей, без бренда!) |
| `fields_garnitury_i_naushniki_3730.json` | `.../garnitury_i_naushniki_3730/fields` | 45 KB | Гарнитуры/наушники к телефонам (39 полей) |
| `fields_smart_casy_ili_braslet.json` | `.../smart_casy_ili_braslet/fields` | 55 KB | Смарт-часы/браслеты (53 поля) |

## Slug-и категорий мобильной техники (полные пути)

- `mobilnye_telefony` — Электроника / Телефоны / Мобильные телефоны
- `plansety` — Электроника / Планшеты и электронные книги / Планшеты
- `nausniki` — Электроника / Аудио и видео / Наушники
- `garnitury_i_naushniki_3730` — Электроника / Телефоны / Аксессуары / Гарнитуры и наушники
- `smart_casy_ili_braslet` — Личные вещи / Часы и украшения / Часы / Смарт-часы или браслет

## Структура полей

Каждое поле — это объект с тегом, типом, обязательностью и значениями:

```json
{
  "tag": "Vendor",
  "label": "Производитель",
  "content": [{
    "field_type": "select",
    "is_catalog": true,
    "name_in_catalog": "Vendor",
    "required": true,
    "values_link_xml": "https://avito.ru/web/1/catalogs/content/feed/phone_catalog.xml"
  }]
}
```

Три варианта значений:
- `values: [...]` inline — для select с малым числом значений (Condition: Новое/Б/у)
- `is_catalog: true` + `values_link_xml` — внешний XML-справочник связок (Vendor+Model+Memory+Color)
- `dependencies: [...]` — поле появляется при выполнении условий на других полях

## XML-каталоги (✅ добыты через SOCKS5-туннель к homelab)

Защищены QRATOR-firewall, не отдаются с зарубежных IP. Получены через SSH SOCKS5 на 213.108.170.194 (см. `DOCS/RU_PROXY_SETUP.md`).

| Каталог | Размер | Содержимое |
|---|---|---|
| `phone_catalog.xml` | 6.8 МБ | 524 бренда, 16149 моделей телефонов, 260 вариантов памяти, 17 цветов, 76 вариантов RAM. Структура: `<Phones><Vendor name="Apple"><Model name="iPhone 15 Pro"><MemorySize name="256 ГБ"><Color name="чёрный"><RamSize name="8 ГБ"/></Color></MemorySize></Model></Vendor>` |
| `tablets.xml` | 2 МБ | 486 брендов, 7391 моделей. Структура: Brand → Model → MemorySize → SimSlot → RamSize → Color |
| `brendy_fashion.xml` | 336 КБ | 7522 fashion-бренда (используется для смарт-часов как справочник Brand) |

Apple в `phone_catalog.xml`: 52 модели (от iPhone оригинального до iPhone 15 Pro Max + iPhone Air + iPhone SE 2020/2022).
Топ-5 брендов по числу моделей: Samsung 1202, Nokia 630, Motorola 559, LG 466, Alcatel 462.

## Важные ограничения

1. **autoload-API даёт поля для размещения объявлений по XML-фиду**, не полный список фильтров поиска. Дополнительные параметры поиска (5G, eSIM, защита от воды) могут существовать только в реверс-API.
2. **Для «Наушников» и «Гарнитур» поля Brand нет** — Avito извлекает бренд из названия. В нашей системе нужно делать то же самое (LLM/regex).
3. **Числовых category_id в этих ответах нет** — только string slug. Для реверс-API поиска (`GET app.avito.ru/api/11/items?categoryId=84`) маппинг slug→id нужно делать отдельно.
