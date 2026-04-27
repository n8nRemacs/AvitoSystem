"""TaskIQ broker + scheduler used by the V1 worker pipeline.

V1 ships with a single Redis-list queue (`avito_monitor:default`).
The TZ specifies five queues — `high` / `default` / `llm_classify` /
`llm_match` / `analytics` — for priority isolation; we leave that as
an enhancement so we can deploy with one worker container instead of
five. Splitting later is a config-only change: add new ListQueueBroker
instances in this file and re-tag tasks with ``broker=<name>``.

Tasks register themselves with this broker through the ``@broker.task()``
decorator in ``app.tasks.polling`` and friends. Importing the task
modules at the bottom is what wires them up — keep them at the bottom
so the broker exists before the decorators run.

Scheduler uses a Redis-backed schedule source so multiple scheduler
replicas (if we ever run them HA) don't fire the same job twice.
"""
from __future__ import annotations

import logging

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app.config import get_settings

log = logging.getLogger(__name__)

_settings = get_settings()

# Single Redis-list queue. Use ``queue_name`` as both Redis list key and
# logical name so the worker logs are easy to grep.
broker = ListQueueBroker(
    url=_settings.redis_url,
    queue_name="avito_monitor:default",
).with_result_backend(
    RedisAsyncResultBackend(redis_url=_settings.redis_url)
)

# Scheduler reads ``schedule`` labels from the registered tasks so the
# crontab lives next to each task definition rather than in a separate
# config. See ``app/tasks/scheduler.py`` for the periodic tick.
scheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker)],
)


# Importing tasks AFTER the broker is constructed registers them via
# the @broker.task decorator. Keep these imports at the bottom.
def _register_tasks() -> None:
    # noqa: F401 — imports for side-effect registration.
    from app.tasks import (  # noqa: F401
        analysis,
        polling,
        scheduler as _sched,
    )


_register_tasks()
