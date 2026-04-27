📉 *Историческое дно*

{% if payload.title %}*{{ payload.title }}*{% endif %}
{% if payload.price is not none %}{{ payload.price | money }} — минимум за {{ payload.window_days or 30 }} дней{% endif %}
{% if payload.previous_low is not none %}Предыдущий минимум: {{ payload.previous_low | money }}{% if payload.previous_low_at %} ({{ payload.previous_low_at }}){% endif %}{% endif %}
{% if payload.condition_class %}Состояние: {{ payload.condition_class | condition_label }}{% endif %}
