# ModelForge

## Product

Web app. Signed-in user uploads ML model (or Hugging Face repo id). Compress it — quantization,
pruning, knowledge distillation, low-rank factorization — or convert it between formats (ONNX,
TFLite, TorchScript, SavedModel, safetensors, GGUF, OpenVINO, TensorRT, Core ML). Watch progress
live, see accuracy before/after, download result, browse history.

`docs/ui-prototype.html` is the source of truth for UX and the operation catalog (TECHS, METHODS,
CONVERTS, availability rules, param types, size-estimate formulas, progress stages, result panel).
When UI or catalog behavior is unclear, defer to it over this file.

## Stack

- `apps/web`: React + Vite + TypeScript frontend.
- `apps/api`: FastAPI on AWS Lambda via Mangum, DynamoDB for state.
- `workers/`: Python workers that do the actual model compression/conversion.
- `infra/`: AWS CDK (Python).
- `packages/catalog`: shared Python catalog of operations, used by both API and workers.

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

## Commands

- `make up` / `make down`: start/stop LocalStack (S3, SQS, DynamoDB) via docker compose.
- `make api`: run the FastAPI dev server (uvicorn --reload) against `apps/api`.
- `make web`: run the Vite dev server for `apps/web`.
- `make worker`: run the workers placeholder runner module.
- `make test`: run catalog + api + workers pytest suites and the web Vitest suite.
- `make lint`: ruff + mypy for the Python packages, eslint for `apps/web`.

## Rules

- `docs/ui-prototype.html` is the source of truth for UX and the operation catalog. Match it
  exactly unless told otherwise.
- Frontend: CSS Modules plus design tokens (`tokens.css`). No UI framework, no Tailwind. Every
  component gets a Storybook story and a test. No hardcoded colors, spacing, or font sizes outside
  `tokens.css`.
- Never load a user's model file inside the API. Only workers open model files.
- Cost first: nothing always-on, everything scales to zero, Spot by default, 7-day log retention.
- Every operation is declared once in `packages/catalog` and used by both API and workers.
- No secrets in code.
