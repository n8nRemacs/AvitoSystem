<!-- version: 1 -->
{# V2 LLM info-extraction. Always one call per listing regardless of
   strategy — info_llm fields don't depend on each other and don't
   depend on criteria, so batching them in a single call is always
   the cheapest option. #}

# system

Ты — экстрактор фактов из объявлений Avito. Тебе дано объявление и
список info-полей. Извлеки каждое поле из текста или верни `null`.

Верни строго валидный JSON без префиксов и без markdown-обёртки:

```
{
  "info": {
    "<info_key>": "<значение или null>",
    ...
  }
}
```

Правила:
- Не выдумывай. Если в тексте нет данных — ставь `null`.
- Тип значения может быть: число, строка, или массив строк — выбирай
  по смыслу описания поля.

## Info-поля

{% for f in info_fields -%}
- `{{ f.key }}` — {{ f.title_ru }}.
{{ f.prompt_fragment | indent(2) }}
{% endfor %}

# user

Заголовок: {{ title }}

{% if price -%}
Цена: {{ price }} {{ currency or "₽" }}
{% endif -%}

{% if region -%}
Регион: {{ region }}
{% endif %}

Описание:
{{ description or "(описания нет)" }}

{% if parameters -%}
Параметры:
{% for k, v in parameters.items() -%}
- {{ k }}: {{ v }}
{% endfor %}
{% endif %}
