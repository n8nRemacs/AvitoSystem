🆕 *Новый лот*

{% if payload.title %}*{{ payload.title }}*{% endif %}
{% if payload.price is not none %}{{ payload.price | money }}{% endif %}
{% if payload.condition_class %}Состояние: {{ payload.condition_class | condition_label }}{% endif %}

{% if payload.score is not none %}Соответствие: *{{ payload.score }}/100*{% endif %}
{% if payload.key_pros %}Плюсы: {{ payload.key_pros | join(", ") }}{% endif %}
{% if payload.key_cons %}Минусы: {{ payload.key_cons | join(", ") }}{% endif %}
{% if payload.reasoning %}
_{{ payload.reasoning }}_
{% endif %}
