## YatraAI developer tasks.
## Windows users: run `pwsh ./tasks.ps1 <target>` for the same commands.

PY := python
VENV := .venv
ifeq ($(OS),Windows_NT)
  BIN := $(VENV)/Scripts
else
  BIN := $(VENV)/bin
endif

.DEFAULT_GOAL := help
.PHONY: help venv install install-web lint format typecheck test test-cov migrate seed \
        pipeline api web docker-up docker-down docker-logs experiments rag-eval clean verify

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

venv: ## Create the Python virtualenv
	$(PY) -m venv $(VENV)

install: ## Install Python deps (editable + dev extras)
	$(BIN)/python -m pip install --upgrade pip setuptools wheel
	$(BIN)/python -m pip install -e ".[dev]"

install-web: ## Install frontend deps
	cd apps/web && npm install

lint: ## Ruff lint (Python) + ESLint (web)
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format: ## Auto-format Python
	$(BIN)/ruff check --fix .
	$(BIN)/ruff format .

typecheck: ## mypy on the API package
	$(BIN)/mypy apps/api/yatraai

test: ## Run the Python test suite
	$(BIN)/python -m pytest

test-cov: ## Test suite with coverage report
	$(BIN)/python -m pytest --cov=apps/api/yatraai --cov-report=term-missing --cov-report=html

migrate: ## Apply database migrations
	cd apps/api && ../../$(BIN)/alembic upgrade head

revision: ## Autogenerate a migration: make revision M="message"
	cd apps/api && ../../$(BIN)/alembic revision --autogenerate -m "$(M)"

seed: ## Load the curated catalogue + knowledge base + embeddings
	$(BIN)/python -m yatraai.cli seed --knowledge --embeddings

pipeline: ## Run Bronze -> Silver -> Gold locally (no Airflow needed)
	$(BIN)/python -m yatraai.cli pipeline --all

api: ## Run the API with reload
	$(BIN)/uvicorn yatraai.main:app --reload --app-dir apps/api --port 8000

web: ## Run the Next.js dev server
	cd apps/web && npm run dev

experiments: ## Reproduce aggregation + planner + ML experiments
	$(BIN)/python ml/run_experiments.py

rag-eval: ## Run the RAG benchmark and write evaluation/reports
	$(BIN)/python evaluation/run_rag_eval.py

verify: lint test ## Lint + test (what CI runs)

docker-up: ## Start db + api + web
	docker compose up -d --build

docker-down: ## Stop and remove containers
	docker compose down -v

docker-logs: ## Tail service logs
	docker compose logs -f

clean: ## Remove caches and build artefacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
