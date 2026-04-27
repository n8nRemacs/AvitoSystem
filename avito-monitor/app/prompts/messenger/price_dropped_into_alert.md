⬇️ *Лот вошёл в alert-зону*

{% if payload.title %}*{{ payload.title }}*{% endif %}
{% if payload.price is not none %}{{ payload.price | money }}{% endif %}
{% if payload.alert_min is not none and payload.alert_max is not none %}
Alert-вилка: {{ payload.alert_min | money }} – {{ payload.alert_max | money }}
{% endif %}
{% if payload.condition_class %}Состояние: {{ payload.condition_class | condition_label }}{% endif %}
