🔀 *Смена структуры предложения*

{% if payload.previous_working_share is not none and payload.current_working_share is not none %}
Доля рабочих лотов: {{ payload.previous_working_share | pct(signed=False) }} → {{ payload.current_working_share | pct(signed=False) }}
{% endif %}
{% if payload.delta is not none %}Изменение: *{{ payload.delta | pct }}*{% endif %}
{% if payload.granularity %}Период: {{ payload.granularity }}{% endif %}
