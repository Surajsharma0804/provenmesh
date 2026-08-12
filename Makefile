.PHONY: help install dev lint type-check test test-unit test-integration test-e2e \
       format migrate docker-up docker-down docker-logs smoke clean

PYTHON := python
PYTEST := pytest
RUFF := ruff

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Setup ───────────────────────────────────────────────────────

install: ## Install production dependencies
	pip install -e .

dev: ## Install dev dependencies
	pip install -e ".[dev]"
	playwright install chromium

# ─── Quality ─────────────────────────────────────────────────────

lint: ## Run linter
	$(RUFF) check src/ tests/

format: ## Auto-format code
	$(RUFF) format src/ tests/
	$(RUFF) check --fix src/ tests/

type-check: ## Run type checker
	mypy src/provenmesh/

# ─── Testing ────────────────────────────────────────────────────

test: ## Run all tests
	$(PYTEST) tests/ -v --tb=short

test-unit: ## Run unit tests only
	$(PYTEST) tests/unit/ -v -m unit

test-integration: ## Run integration tests (requires Docker services)
	$(PYTEST) tests/integration/ -v -m integration --timeout=60

test-contract: ## Run contract tests
	$(PYTEST) tests/contract/ -v -m contract

test-e2e: ## Run end-to-end tests (requires Docker services)
	$(PYTEST) tests/e2e/ -v -m e2e --timeout=300

test-coverage: ## Run tests with coverage report
	$(PYTEST) tests/ -v --cov=src/provenmesh --cov-report=html --cov-report=term-missing

# ─── Database ───────────────────────────────────────────────────

migrate: ## Run database migrations
	alembic upgrade head

migrate-generate: ## Auto-generate a new migration
	alembic revision --autogenerate -m "$(msg)"

migrate-rollback: ## Rollback last migration
	alembic downgrade -1

# ─── Docker ─────────────────────────────────────────────────────

docker-up: ## Start all Docker services
	docker compose up -d

docker-down: ## Stop all Docker services
	docker compose down

docker-logs: ## Follow Docker service logs
	docker compose logs -f

docker-rebuild: ## Rebuild and restart workers
	docker compose up -d --build --force-recreate

docker-scale-crawlers: ## Scale crawler workers (usage: make docker-scale-crawlers n=4)
	docker compose up -d --scale crawler-worker=$(n)

# ─── Scripts ────────────────────────────────────────────────────

seed: ## Load seed entities into the database
	$(PYTHON) scripts/seed_entities.py

create-bucket: ## Create the MinIO bucket
	$(PYTHON) scripts/create_bucket.py

create-sheet: ## Create the Google Sheets document
	$(PYTHON) scripts/create_sheet.py

smoke: ## Run smoke test against local services
	$(PYTHON) scripts/smoke_test.py

# ─── Pipeline ───────────────────────────────────────────────────

run-crawl: ## Start the crawl pipeline
	$(PYTHON) -m provenmesh.main crawl

run-extract: ## Start extraction workers
	$(PYTHON) -m provenmesh.main extract

run-resolve: ## Start resolver workers
	$(PYTHON) -m provenmesh.main resolve

run-export: ## Export to Google Sheets
	$(PYTHON) -m provenmesh.main export

run-all: ## Run the full pipeline
	$(PYTHON) -m provenmesh.main run

# ─── Cleanup ────────────────────────────────────────────────────

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf dist/ build/ *.egg-info/ htmlcov/ .coverage
