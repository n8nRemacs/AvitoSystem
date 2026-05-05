🆕 *Новый лот*

{% if payload.title %}*{{ payload.title }}*{% endif %}
{% if payload.price is not none %}{{ payload.price | money }}{% endif %}
{% if payload.condition_class %}Состояние: {{ payload.condition_class | condition_label }}{% endif %}

{% if payload.get('score') is not none %}Соответствие: *{{ payload.get('score') }}/100*{% endif %}
{% if payload.get('key_pros') %}Плюсы: {{ payload.get('key_pros') | join(", ") }}{% endif %}
{% if payload.get('key_cons') %}Минусы: {{ payload.get('key_cons') | join(", ") }}{% endif %}
{% if payload.get('reasoning') %}
_{{ payload.get('reasoning') }}_
{% endif %}
