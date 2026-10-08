.PHONY: install run dev test cov lint format typecheck migrate samples openapi docker-build docker-run smoke clean all help

VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
PIP ?= $(VENV)/bin/pip
UVICORN ?= $(VENV)/bin/uvicorn
PYTEST ?= $(VENV)/bin/pytest
RUFF ?= $(VENV)/bin/ruff
MYPY ?= $(VENV)/bin/mypy
ALEMBIC ?= $(VENV)/bin/alembic

help:
	@echo "Available targets:"
	@echo "  install      - Create venv and install all dependencies"
	@echo "  run          - Run production server via uvicorn on :8000"
	@echo "  dev          - Run local development server with --reload"
	@echo "  test         - Run test suite via pytest"
	@echo "  cov          - Run tests with terminal coverage and HTML report"
	@echo "  lint         - Check code style via ruff"
	@echo "  format       - Format code via ruff"
	@echo "  typecheck    - Run static type checking via mypy"
	@echo "  migrate      - Apply database schema migrations via alembic"
	@echo "  samples      - Generate sample dataset archives in samples/"
	@echo "  openapi      - Export OpenAPI schema to docs/openapi.json"
	@echo "  docker-build - Build production Docker image"
	@echo "  docker-run   - Run containerized application via docker-compose"
	@echo "  smoke        - Execute curl-based smoke test suite against running API"
	@echo "  clean        - Remove temporary artifacts and caches"
	@echo "  all          - Run lint, typecheck, and test suite"

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt -r requirements-dev.txt
	$(PIP) install -e .

run:
	$(UVICORN) app.main:app --host 0.0.0.0 --port 8000

dev:
	$(UVICORN) app.main:app --host 127.0.0.1 --port 8000 --reload

test:
	$(PYTEST) tests/

cov:
	$(PYTEST) tests/ --cov=app --cov-report=term-missing --cov-report=html

lint:
	$(RUFF) check app tests scripts
	$(RUFF) format --check app tests scripts

format:
	$(RUFF) check --fix app tests scripts
	$(RUFF) format app tests scripts

typecheck:
	$(MYPY) app scripts

migrate:
	$(ALEMBIC) upgrade head

samples:
	$(PYTHON) scripts/generate_samples.py

openapi:
	$(PYTHON) scripts/export_openapi.py

docker-build:
	docker build -t geomeasure:latest .

docker-run:
	docker-compose up -d

smoke:
	./scripts/smoke_test.sh

clean:
	rm -rf .pytest_cache htmlcov .coverage .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -f test_suite.db test_suite.db-shm test_suite.db-wal

all: lint typecheck cov
