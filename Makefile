# =============================================================================
# Enterprise AI Knowledge & Decision Platform
# =============================================================================
.DEFAULT_GOAL := help
.PHONY: help up dev down down-v logs ps rebuild seed \
        backend-install backend-dev backend-test backend-lint \
        frontend-install frontend-dev frontend-build frontend-lint \
        test lint

## ----------------------------------------------------------------- compose
up: ## Start the full stack (detached)
	docker compose up --build -d

dev: ## Start the full stack with logs attached
	docker compose up --build

down: ## Stop the stack
	docker compose down

down-v: ## Stop the stack and delete volumes (DATA LOSS)
	docker compose down -v

logs: ## Follow all logs
	docker compose logs -f

ps: ## Show container status
	docker compose ps

rebuild: ## Rebuild images from scratch
	docker compose build --no-cache

## ----------------------------------------------------------------- backend
backend-install:
	cd backend && python -m pip install -r requirements.txt

backend-dev: ## Run the API locally with reload (needs local Postgres+Redis)
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

backend-test:
	cd backend && python -m pytest

backend-lint:
	cd backend && ruff check app tests

## ---------------------------------------------------------------- frontend
frontend-install:
	cd frontend && npm ci

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-lint:
	cd frontend && npm run lint && npm run typecheck

## -------------------------------------------------------------------- meta
test: backend-test ## Run the backend test suite
	cd frontend && npm run typecheck

lint: backend-lint frontend-lint ## Lint everything

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
