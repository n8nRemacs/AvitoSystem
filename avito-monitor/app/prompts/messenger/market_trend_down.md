📊 *Тренд рынка: {{ payload.delta_pct | pct }}*

{% if payload.previous_median_clean is not none and payload.current_median_clean is not none %}
Медиана: {{ payload.previous_median_clean | money }} → {{ payload.current_median_clean | money }}
{% endif %}
{% if payload.granularity %}Период: {{ payload.granularity }}{% endif %}
{% if payload.threshold_pct is not none %}_Порог: {{ payload.threshold_pct | pct(signed=False) }}_{% endif %}
