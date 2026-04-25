.PHONY: up down build logs migrate migration admin shell ps test lint

DC := docker compose

up:
	$(DC) up -d --build

down:
	$(DC) down

build:
	$(DC) build

logs:
	$(DC) logs -f $(service)

ps:
	$(DC) ps

migrate:
	$(DC) run --rm app alembic upgrade head

migration:
	@if [ -z "$(name)" ]; then echo "Usage: make migration name=<slug>"; exit 2; fi
	$(DC) run --rm app alembic revision --autogenerate -m "$(name)"

admin:
	@if [ -z "$(user)" ] || [ -z "$(pass)" ]; then echo "Usage: make admin user=<username> pass=<password>"; exit 2; fi
	$(DC) run --rm app python -m scripts.create_admin $(user) $(pass)

seed:
	$(DC) run --rm app python -m scripts.seed_demo_data

shell:
	$(DC) exec app /bin/bash

test:
	$(DC) run --rm app pytest

lint:
	$(DC) run --rm app ruff check .
