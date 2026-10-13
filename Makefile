.PHONY: up down api web worker test lint

up:
	docker compose up -d

down:
	docker compose down

api:
	cd apps/api && uvicorn app.main:app --reload --port 8000

web:
	npm run dev --prefix apps/web

worker:
	cd workers && python -m core.runner

test:
	cd packages/catalog && python -m pytest
	cd apps/api && python -m pytest
	cd workers && python -m pytest
	npm run test --prefix apps/web

lint:
	cd packages/catalog && ruff check . && mypy src
	cd apps/api && ruff check . && mypy app
	cd workers && ruff check . && mypy core ops
	npm run lint --prefix apps/web
