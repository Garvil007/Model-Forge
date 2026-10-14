.PHONY: up down api web worker test lint shot shot-stories shot-authed storybook types e2e lhci

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

types:
	cd packages/catalog && python -m modelforge_catalog.export ../../apps/web/src/features/catalog/generated
	npm run generate:types --prefix apps/web

storybook:
	npm run storybook --prefix apps/web

shot:
	npm run shot --prefix apps/web -- --page $(PAGE)

shot-stories:
	npm run shot-stories --prefix apps/web

shot-authed:
	node apps/web/scripts/shot-authed.mjs

e2e:
	npm run test:e2e --prefix apps/web

lhci:
	npm run lhci --prefix apps/web
