🔻 *Цена упала{% if payload.delta_pct is not none %} на {{ payload.delta_pct | pct(signed=False) }}{% endif %}*

{% if payload.title %}*{{ payload.title }}*{% endif %}
{% if payload.previous_price is not none and payload.price is not none %}
{{ payload.previous_price | money }} → {{ payload.price | money }}
{% elif payload.price is not none %}
{{ payload.price | money }}
{% endif %}
{% if payload.condition_class %}Состояние: {{ payload.condition_class | condition_label }}{% endif %}
