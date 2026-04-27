📦 *Всплеск предложения {{ payload.delta_pct | pct }}*

{% if payload.previous_listings_count is not none and payload.current_listings_count is not none %}
Активных лотов: {{ payload.previous_listings_count }} → {{ payload.current_listings_count }}
{% endif %}
{% if payload.granularity %}Период: {{ payload.granularity }}{% endif %}

_Возможный сигнал к снижению цен. Следи за медианой._
