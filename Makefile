.PHONY: up down api web worker test lint shot shot-stories shot-authed storybook types e2e e2e-jobs lhci load-test

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
	cd packages/db && python -m pytest
	cd apps/api && python -m pytest
	cd workers && python -m pytest
	cd infra && python -m pytest
	npm run test --prefix apps/web

lint:
	cd packages/catalog && ruff check . && mypy src
	cd packages/db && ruff check . && mypy src
	cd apps/api && ruff check . && mypy app
	cd workers && ruff check . && mypy core ops
	cd infra && ruff check . && mypy stacks app.py
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

# Requires `make up` (LocalStack) first, and catalog/db/api/workers/dispatcher all
# installed editable into the same environment (see infra/lambda/dispatcher/pyproject.toml).
e2e-jobs:
	cd workers && python -m pytest tests/test_e2e_quantize.py -v

lhci:
	npm run lhci --prefix apps/web

# Basic load smoke test of the API (health + catalog only — see scripts/load/api-smoke.js).
# Requires the k6 binary (https://k6.io) and MF_API_URL, e.g.:
#   make load-test MF_API_URL=https://dev-api.example.com
load-test:
	MF_API_URL=$(MF_API_URL) k6 run scripts/load/api-smoke.js
