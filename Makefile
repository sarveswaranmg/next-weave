.PHONY: help install install-embedded dev test test-sdk lint format clean docker-build docker-up docker-down migrate docs

help:
	@echo "NeuroWeave Development Commands"
	@echo "==============================="
	@echo "make install    - Install dependencies"
	@echo "make install-embedded - Install the embedded/local Memory() SDK (no server needed)"
	@echo "make dev        - Run development server"
	@echo "make test       - Run backend test suite"
	@echo "make test-sdk   - Run Python SDK test suite"
	@echo "make lint       - Run linting"
	@echo "make format     - Format code"
	@echo "make clean      - Clean cache and build files"
	@echo "make docker-build - Build Docker image"
	@echo "make docker-up  - Start Docker containers (api + worker + beat)"
	@echo "make docker-down - Stop Docker containers"
	@echo "make migrate    - Run database migrations"
	@echo "make docs       - Show where the documentation lives"

install:
	pip install -r requirements.txt

install-embedded:
	pip install -e .
	pip install -e "sdk/python[embedded]"

dev:
	export PYTHONUNBUFFERED=1 && \
	uvicorn neurowave_engine.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -v --cov=neurowave_engine --cov-report=html

test-sdk:
	pip install -e sdk/python[dev]
	pytest sdk/python/tests/ -v

lint:
	flake8 neurowave_engine
	mypy neurowave_engine

format:
	black neurowave_engine
	isort neurowave_engine

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .coverage htmlcov .pytest_cache

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d
	@echo "Waiting for services..."
	sleep 10
	docker-compose exec neuroweave alembic -c migrations/alembic.ini upgrade head
	@echo "✅ NeuroWeave is running at http://localhost:8000"

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f neuroweave

migrate:
	alembic -c migrations/alembic.ini upgrade head

db-create:
	createdb -U postgres neuroweave
	psql -U postgres -d neuroweave -c "CREATE EXTENSION IF NOT EXISTS vector;"

docs:
	@echo "Documentation:"
	@echo "- README.md - Project overview & quickstart"
	@echo "- docs/DOCUMENTATION.md - Full reference (architecture, API, deployment, security, benchmarking)"
	@echo "- CONTRIBUTING.md - How to contribute"
	@echo "- docs/archive/ - Historical build logs per milestone"
