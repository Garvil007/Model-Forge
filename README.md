# ModelForge

Web app for compressing and converting ML models. Sign in, upload a model (or point at a
Hugging Face repo id), run quantization, pruning, knowledge distillation, or low-rank
factorization — or convert between formats (ONNX, TFLite, TorchScript, SavedModel, safetensors,
GGUF, OpenVINO, TensorRT, Core ML). Watch progress live, compare accuracy before/after, download
the result, browse job history.

`docs/ui-prototype.html` is the source of truth for UX and the operation catalog (techs, methods,
converts, availability rules, param types, size-estimate formulas, progress stages, result
panel). Defer to it over this README when behavior is unclear.

## Stack

- `apps/web` — React + Vite + TypeScript frontend
- `apps/api` — FastAPI on AWS Lambda via Mangum, DynamoDB for state
- `workers/` — Python workers doing the actual model compression/conversion
- `infra/` — AWS CDK (Python)
- `packages/catalog` — shared Python catalog of operations, used by both API and workers

## Repo layout

```
modelforge/
├── CLAUDE.md
├── docs/
│   ├── ui-prototype.html
│   ├── PROGRESS.md
│   ├── decisions.md
│   ├── COSTS.md
│   └── FRONTEND.md
├── packages/catalog/
├── apps/
│   ├── web/
│   │   ├── src/
│   │   │   ├── styles/
│   │   │   ├── ui/
│   │   │   ├── features/
│   │   │   │   ├── model/
│   │   │   │   ├── catalog/
│   │   │   │   ├── job/
│   │   │   │   └── dashboard/
│   │   │   ├── api/
│   │   │   ├── mocks/
│   │   │   └── routes/
│   │   └── e2e/
│   └── api/
├── workers/
│   ├── core/
│   ├── ops/
│   └── images/
├── infra/
├── docker-compose.yml
└── .github/workflows/
```

## Getting started

```bash
make up      # start LocalStack (S3, SQS, DynamoDB) via docker compose
make api     # run FastAPI dev server (uvicorn --reload) against apps/api
make web     # run Vite dev server for apps/web
make worker  # run the workers placeholder runner module
```

## Commands

| Command | Purpose |
|---|---|
| `make up` / `make down` | start/stop LocalStack dependencies |
| `make api` | run API dev server |
| `make web` | run web dev server |
| `make worker` | run workers runner |
| `make test` | catalog + api + workers pytest suites, web Vitest suite |
| `make lint` | ruff + mypy for Python packages, eslint for `apps/web` |

## Conventions

- `docs/ui-prototype.html` is the source of truth for UX and the operation catalog. Match it
  exactly unless told otherwise.
- Frontend: CSS Modules + design tokens (`tokens.css`). No UI framework, no Tailwind. Every
  component gets a Storybook story and a test. No hardcoded colors/spacing/font sizes outside
  `tokens.css`.
- Never load a user's model file inside the API — only workers open model files.
- Cost first: nothing always-on, everything scales to zero, Spot by default, 7-day log retention.
- Every operation is declared once in `packages/catalog` and used by both API and workers.
- No secrets in code.
