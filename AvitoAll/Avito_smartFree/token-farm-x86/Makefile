# Token Farm x86 Development Makefile
# Quick commands for development workflow

.PHONY: help up down restart logs test clean install adb

help:
	@echo "Token Farm x86 - Development Commands"
	@echo ""
	@echo "Quick Start:"
	@echo "  make install    Install dependencies"
	@echo "  make up         Start containers"
	@echo "  make test       Run all tests"
	@echo ""
	@echo "Container Management:"
	@echo "  make up         Start containers (minimal: 2 Redroid + PostgreSQL)"
	@echo "  make up-full    Start all containers (3 Redroid)"
	@echo "  make up-api     Start containers + API server"
	@echo "  make down       Stop containers"
	@echo "  make restart    Restart containers"
	@echo "  make logs       Show logs (all containers)"
	@echo "  make clean      Remove all containers and volumes"
	@echo ""
	@echo "Testing:"
	@echo "  make test       Run x86 setup tests"
	@echo "  make test-unit  Run unit tests (pytest)"
	@echo "  make test-all   Run all tests"
	@echo ""
	@echo "ADB:"
	@echo "  make adb        Connect to all containers via ADB"
	@echo "  make adb-list   List connected devices"
	@echo ""
	@echo "Monitoring:"
	@echo "  make ps         Show container status"
	@echo "  make top        Show container resource usage"
	@echo ""
	@echo "Development:"
	@echo "  make shell      Open shell in container 1"
	@echo "  make screen     Take screenshot from container 1"

# Installation
install:
	@echo "Installing Python dependencies..."
	pip install pytest asyncio httpx
	@echo "Checking Docker..."
	docker --version
	@echo "Checking ADB..."
	adb version || echo "Warning: ADB not found. Install platform-tools."
	@echo ""
	@echo "Creating .env file..."
	@if not exist .env ( copy .env.example .env && echo Created .env from template )
	@echo ""
	@echo "✅ Installation complete!"
	@echo "Run 'make up' to start containers"

# Container management
up:
	@echo "Starting containers (minimal: 2 Redroid)..."
	docker-compose up -d postgres redroid-x86-1 redroid-x86-2
	@echo ""
	@echo "Waiting for containers to start..."
	@timeout /t 5 /nobreak > nul
	@echo "✅ Containers started!"
	@make ps

up-full:
	@echo "Starting all containers (3 Redroid)..."
	docker-compose --profile full up -d
	@echo ""
	@echo "Waiting for containers to start..."
	@timeout /t 5 /nobreak > nul
	@echo "✅ All containers started!"
	@make ps

up-api:
	@echo "Starting containers with API server..."
	docker-compose --profile api --profile full up -d
	@echo ""
	@echo "Waiting for containers to start..."
	@timeout /t 5 /nobreak > nul
	@echo "✅ Containers + API started!"
	@make ps

down:
	@echo "Stopping containers..."
	docker-compose down
	@echo "✅ Containers stopped"

restart:
	@echo "Restarting containers..."
	docker-compose restart
	@echo "✅ Containers restarted"

logs:
	docker-compose logs -f

clean:
	@echo "Removing all containers and volumes..."
	docker-compose down -v
	@echo "✅ Cleaned up"

# Testing
test:
	@echo "Running x86 setup tests..."
	python test_x86_setup.py

test-unit:
	@echo "Running unit tests..."
	pytest test_avito_prefs_parser.py -v

test-all:
	@echo "Running all tests..."
	@make test-unit
	@echo ""
	@make test

# ADB
adb:
	@echo "Connecting to containers via ADB..."
	adb connect localhost:5555
	adb connect localhost:5556
	adb connect localhost:5557
	@echo ""
	@make adb-list

adb-list:
	@echo "Connected devices:"
	adb devices

# Monitoring
ps:
	@echo "Container status:"
	docker-compose ps

top:
	@echo "Container resource usage:"
	docker stats --no-stream

# Development
shell:
	@echo "Opening shell in redroid-x86-1..."
	docker exec -it redroid-x86-1 sh

screen:
	@echo "Taking screenshot..."
	adb -s localhost:5555 exec-out screencap -p > screenshot.png
	@echo "✅ Saved to screenshot.png"

# Quick info
info:
	@echo ""
	@echo "Token Farm x86 Development Environment"
	@echo "======================================"
	@echo ""
	@echo "Containers:"
	@docker-compose ps --format "  {{.Name}}: {{.State}}"
	@echo ""
	@echo "ADB Devices:"
	@adb devices | findstr "localhost"
	@echo ""
	@echo "Database:"
	@docker-compose exec postgres psql -U avito -d avito_smartfree_x86 -c "SELECT COUNT(*) as accounts FROM accounts;" 2>nul || echo "  Database not ready"
	@echo ""
