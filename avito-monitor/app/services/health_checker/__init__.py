"""V2 Messenger Reliability — health-checker service.

Runs six scheduled scenarios (A-F) against avito-xapi and persists results
to the ``health_checks`` table. Exposes a tiny FastAPI for manual triggers
(see :mod:`app.services.health_checker.api`).
"""
