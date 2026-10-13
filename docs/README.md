# ModelForge: build guide with Claude Code on a low-cost AWS setup

This guide builds ModelForge from scratch: the frontend first, then the backend, then a live deployment on AWS, all with Claude Code. Everything is chosen for the smallest possible AWS bill: nothing runs when nobody is using the site.

**The approved interface is the specification.** Copy `modelforge-v2.html` into the repo as `docs/ui-prototype.html`. Its four techniques, every method and parameter, the availability rules, the size estimates, the progress stages and the result panel are what you are building. Leave the earlier zip out of the repo; everything here is written fresh.

The plan is 25 working days: 1 day of scaffolding, 5 days of frontend, 12 days of backend and operations, 7 days of deployment, hardening and launch. Each day has one goal, one prompt to paste into Claude Code, and a checklist to pass before moving on.

---

## 1. What the app does

A signed-in user can:

1. Upload a model, or paste a Hugging Face model ID.
2. Compress it with **quantization** (FP16, BF16, INT8 dynamic, INT8 static, GGUF, GPTQ, AWQ, NF4), **pruning** (magnitude, structured, 2:4, Wanda/SparseGPT), **knowledge distillation** (response-based, feature-based, LLM) or **low-rank factorization** (SVD, Tucker/CP).
3. Convert it to ONNX, TFLite, TorchScript, TensorFlow SavedModel, safetensors, GGUF, OpenVINO, TensorRT or Core ML.
4. Watch progress live, see accuracy before and after, download the result, and browse their history.

## 2. Architecture, chosen for cost

The rule: **no always-on servers**. Every piece either scales to zero or is billed per request.

```
            Route 53 ($0.50/month)  +  ACM certificate (free)
                            │
                  CloudFront (free tier: 1 TB out/month)
             ┌──────────────┴───────────────┐
      S3 (React app)                 API: Lambda + API Gateway HTTP API
      pennies/month                  (free tier 1M requests/month, $0 idle)
                                            │
        Cognito (free up to 10k users)      │
                    │                       │
              JWT check              DynamoDB on-demand      S3 (uploads, results)
                                     ($0 idle, pay per       deleted after 7 days
                                      request)                      │
                                            │                       │
                                          SQS (1M requests/month free)
                                            │
                              ┌─────────────┴──────────────┐
                    CPU jobs: AWS Batch on        GPU jobs: AWS Batch on
                    Fargate Spot (~70% off,       EC2 g6/g5 Spot, min 0 vCPUs
                    scales to zero)               (billed only while running)
                                            │
                   SSM Parameter Store (free) · CloudWatch logs, 7-day retention · ECR
```

### What this avoids

| Common choice | Cost | What we use instead | Idle cost |
|---|---|---|---|
| Application Load Balancer | ~$20/month | API Gateway HTTP API + Lambda | $0 |
| NAT gateway | ~$35/month | Workers in public subnets, outbound-only security groups | $0 |
| RDS PostgreSQL | ~$15/month | DynamoDB on-demand, single table | ~$0 |
| Always-on worker service | $15–60/month | Batch jobs started per message, on Spot | $0 |
| Secrets Manager | $0.40 per secret | SSM Parameter Store (SecureString) | $0 |
| Default log retention (forever) | grows | 7-day retention everywhere | ~$0 |

### What you actually pay

| Item | Cost |
|---|---|
| Route 53 hosted zone | $0.50/month |
| Domain name | ~$12/year |
| ECR image storage (a few GB, with a lifecycle rule) | ~$1–2/month |
| S3 storage for files awaiting deletion | a few cents |
| **Idle total** | **about $2–4/month** |
| One CPU job (2 vCPU, 8 GB, Fargate Spot, 5 min) | roughly 1–2 cents |
| One GPU job (g6.xlarge Spot, 20 min) | roughly 8–12 cents |

Prices vary by region and change, so check the [AWS Pricing Calculator](https://calculator.aws/) and your own bill. New accounts also get credits and a free tier that cover most of the development period.

**Region:** use `us-east-1`. It has the cheapest and most available GPU capacity.

## 3. Repository layout

```
modelforge/
├── CLAUDE.md                     # project memory for Claude Code
├── docs/
│   ├── ui-prototype.html         # modelforge-v2.html: the approved interface, the spec
│   ├── PROGRESS.md               # updated at the end of every day
│   ├── decisions.md
│   ├── COSTS.md
│   └── FRONTEND.md               # component map and UI conventions
├── packages/catalog/             # the operation catalog, shared by API and workers (Python)
├── apps/
│   ├── web/
│   │   ├── src/
│   │   │   ├── styles/           # tokens.css, themes, global styles
│   │   │   ├── ui/               # primitives: Button, Select, Range, Toggle, FileInput…
│   │   │   ├── features/
│   │   │   │   ├── model/        # ModelPanel, upload, detection
│   │   │   │   ├── catalog/      # TechniqueTable, MethodList, MethodParams
│   │   │   │   ├── job/          # JobProgress, ResultPanel
│   │   │   │   └── dashboard/
│   │   │   ├── api/              # typed client, generated types, TanStack Query hooks
│   │   │   ├── mocks/            # MSW handlers (the whole backend, faked)
│   │   │   └── routes/
│   │   └── e2e/                  # Playwright
│   └── api/                      # FastAPI on Lambda (Mangum) + DynamoDB
├── workers/
│   ├── core/                     # job runner, S3/SQS helpers, progress, training loop
│   ├── ops/                      # one module per technique and converter
│   └── images/                   # Dockerfiles: cpu-torch, cpu-tf, cpu-llm, gpu, tensorrt
├── infra/                        # AWS CDK (Python)
├── docker-compose.yml            # local stack: LocalStack (S3, SQS, DynamoDB)
└── .github/workflows/
```

---

## 4. Working with Claude Code

Install (macOS, Linux, WSL):

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Windows PowerShell: `irm https://claude.ai/install.ps1 | iex`. Then run `claude` in the repo and log in. Other options are in the [Claude Code docs](https://code.claude.com/docs/en/quickstart).

**Each day**

1. Start a fresh session (or `/clear`). One day, one session.
2. Press Shift+Tab for **plan mode**, paste the day's prompt, and read the plan before any code gets written.
3. Let it implement and run the tests. Paste full error messages when something fails.
4. Review the diff, try the app yourself, work through the checklist.
5. `git commit -am "Day N: <goal>"`.

Every prompt ends by updating `docs/PROGRESS.md`, so tomorrow's session knows where you are.

**Cost discipline while building:** days 1 to 18 run entirely on your machine. Only day 8 (Cognito, free) touches AWS before day 19. Ask Claude what a deploy will cost before running it, and run `cdk destroy --all -c env=dev` whenever you stop for a few days.

### 4a. Getting good UI out of Claude Code

Frontend work fails differently from backend work: the tests pass and it still looks wrong. These five habits fix most of it.

1. **Give it eyes.** Install Playwright on day 2 and add a `make shot` command that screenshots a page or a Storybook story into `.screenshots/`. Then end UI prompts with: *"Take a screenshot at 1280px and 390px, open it, compare against docs/ui-prototype.html, and fix what differs."* Claude can read the PNG it just produced, which turns UI work into a loop instead of a guess.
2. **One component group per prompt.** "Build the whole app" produces plausible mush. "Build these four primitives, with stories and tests" produces code you can review.
3. **Tokens before components.** Day 2 extracts every color, space and font size into CSS variables. After that no component invents a value, and dark mode comes for free.
4. **Mock the backend properly.** MSW (Mock Service Worker) intercepts real `fetch` calls, so the frontend is built against the true API shape and nothing has to change on the day the backend arrives.
5. **Say what "done" looks like.** Name the states: empty, loading, error, long content, disabled, mobile. Unlisted states don't get built.

Two things worth setting up once, early:

- **Storybook** gives each component a page of its own. That's where you review variants and where the screenshot loop runs. It costs an hour on day 2 and saves days later.
- **Keep the prototype's plain CSS**, as CSS Modules plus variables. Don't let Claude convert it to Tailwind: you'd be re-deriving a design you already approved, and small differences creep in.

---

## 5. The daily prompts

### Day 0: Accounts and setup (by hand, about an hour)

1. Create an AWS account, enable MFA on the root user, create an IAM Identity Center user for daily work.
2. Install the AWS CLI, Docker, Node.js 20+, Python 3.11 and the CDK (`npm install -g aws-cdk`).
3. Run `aws configure sso`, then `cdk bootstrap aws://<account-id>/us-east-1`.
4. In Service Quotas, request "All G and VT Spot Instance Requests" = 8 vCPUs. Approval can take days, so do it now.
5. In Billing, create a **monthly budget of $20** with alerts at 50% and 100%.
6. Create the GitHub repo, clone it, and copy `modelforge-v2.html` to `docs/ui-prototype.html`.

Then, in Claude Code:

```text
Open docs/ui-prototype.html. It is the approved interface for ModelForge and the specification for
this project: a web app where signed-in users upload ML models and compress them (quantization,
pruning, knowledge distillation, low-rank factorization) or convert them between formats.

Study its catalog (TECHS, METHODS, CONVERTS), its availability rules, its parameter types, its
size-estimate formulas, its progress stages and its result panel.

Then create:
1. CLAUDE.md covering: the product; the stack (React + Vite + TypeScript in apps/web; FastAPI on
   AWS Lambda via Mangum with DynamoDB in apps/api; Python workers in workers/; AWS CDK in infra/;
   a shared Python catalog in packages/catalog); the repo layout from README section 3; and these
   rules:
   - docs/ui-prototype.html is the source of truth for the UX and the operation catalog.
   - Frontend: CSS Modules plus design tokens. No UI framework, no Tailwind. Every component has a
     Storybook story and a test. No hardcoded colors, spacing or font sizes outside tokens.css.
   - Never load a user's model file inside the API. Only workers open model files.
   - Cost first: nothing always-on, everything scales to zero, Spot by default, 7-day log retention.
   - Every operation is declared once in packages/catalog and used by both API and workers.
   - No secrets in code.
2. docs/PROGRESS.md with the day 1-25 checklist from README.md.
3. docs/decisions.md, docs/COSTS.md and docs/FRONTEND.md as empty templates.

Write no application code yet.
```

**Done when:** those files exist and CLAUDE.md matches how you want to work.

---

### Day 1: Monorepo, shared catalog and local stack

```text
Set up the monorepo from CLAUDE.md, with no AWS dependency for local development.

1. packages/catalog: a Python package holding the operation catalog translated from
   docs/ui-prototype.html. One dataclass per operation: id, technique (quantization | pruning |
   distillation | lowrank | convert), label, description, accuracy label, typical impact, time
   estimate, source formats, allowed model families, required bit width, parameter schema
   (select / range / check / number / text / file with defaults, ranges, help text and show-if
   rules), target format, worker image and queue (cpu | gpu), plus the size-estimate function.
   Include every method and conversion shown in the prototype.
   Export two artifacts: catalog.json for the frontend, and a JSON Schema per operation's params.
   Add a test asserting the export matches the prototype's options exactly (ids, labels, defaults).
2. apps/api: FastAPI with /health, pydantic-settings, ruff, mypy, pytest. It runs on Lambda later,
   so keep it light: no torch, no tensorflow.
3. workers/: package with a placeholder runner.
4. apps/web: React + Vite + TypeScript, ESLint, Prettier, Vitest, React Router, TanStack Query.
5. docker-compose.yml with LocalStack (S3, SQS, DynamoDB) and an init script creating the buckets
   (mf-uploads, mf-results), the queues (cpu-jobs, gpu-jobs plus dead-letter queues) and the table.
6. A Makefile: make up, down, api, web, worker, test, lint.
7. A GitHub Actions workflow running lint and tests on pull requests.

Run everything, make sure make test passes, then update CLAUDE.md's command list and
docs/PROGRESS.md.
```

**Done when:** `make up && make api && make web` works and the catalog test proves parity with the prototype.

---

## Frontend track (days 2 to 6)

The whole frontend gets built against a mocked backend, so it is finished and reviewable before any API exists. Nothing in these five days needs AWS.

### Day 2: Design tokens, primitives and the screenshot loop

```text
Set up the frontend foundations in apps/web. Work only from docs/ui-prototype.html.

1. src/styles/tokens.css: extract EVERY design value from the prototype into CSS custom properties
   on :root: colors (paper, panel, ink, muted, line, soft, accent, on-accent, lossless, near, lossy,
   notice/error/badge backgrounds), a spacing scale, radii, font sizes, line heights and font
   weights. Redefine the colors for dark mode under @media (prefers-color-scheme: dark) guarded by
   :root:not([data-theme="light"]) and again under :root[data-theme="dark"], exactly as the
   prototype does. Add a ThemeProvider with light / dark / system and a header toggle that
   remembers the choice in localStorage inside try/catch.
2. src/ui/: primitives as CSS Module components, each matching the prototype's look exactly:
   Button (primary, secondary, link, disabled, loading), Chip, Panel, Tabs (roving focus, arrow
   keys), Badge (lossless / near-lossless / lossy), Select, NumberInput, TextInput, Range (with its
   value readout), Toggle, FileInput, Spinner, Notice (info / warning / error), Skeleton, Tooltip.
   Every one is keyboard accessible, has a visible focus ring, and respects prefers-reduced-motion.
   No hardcoded values: tokens only.
3. Storybook 8 with a story per primitive covering every variant and state, plus a light/dark
   toolbar switch and the viewport addon.
4. Playwright, plus `make shot PAGE=<url>` and `make shot-stories`, writing PNGs to .screenshots/
   at 1280px and 390px wide.
5. A stylelint rule that fails the build on a raw hex color or px font size outside tokens.css.

Then take screenshots of the Storybook stories in both themes, open them, compare against
docs/ui-prototype.html, and fix every difference you find. Write the component conventions into
docs/FRONTEND.md and update docs/PROGRESS.md.
```

**Done when:** Storybook shows every primitive in both themes, the screenshots match the prototype's look, and stylelint rejects a hardcoded color.

---

### Day 3: The catalog-driven core

This is the heart of the app: the technique table, the method list, and a parameter renderer that builds itself from the catalog schema. Get this right and adding a method later becomes a backend-only change.

```text
Build the operation-picking UI in apps/web/src/features/catalog/, driven entirely by data.

1. Types: generate TypeScript types from packages/catalog's JSON export (json-schema-to-typescript)
   in a `make types` step, so the catalog can never drift from the UI.
2. TechniqueTable: the four-row comparison table from the prototype (technique, how it works,
   hardware impact, effort with its small bar meter) that doubles as a radio group. Full keyboard
   support (arrow keys, Space to select), proper ARIA roles, and the prototype's stacked layout
   below 640px with its "How:" and "Impact:" labels.
3. MethodList and MethodRow: name, accuracy badge, description, "Typical impact" and "Takes"
   metadata, the selected state, and the disabled state showing the reason instead of the metadata
   ("Not available for safetensors. Works with ONNX, PyTorch, TorchScript, Keras."). Available
   methods sort above unavailable ones, as in the prototype.
4. MethodParams: a SCHEMA-DRIVEN renderer. Given an operation's param schema it renders the right
   primitive for each type (select, range, check, number, text, file), applies defaults, evaluates
   show-if rules so dependent fields appear and disappear, marks required fields, and reports
   validity. Adding a param to the catalog must require zero frontend changes. Keep param state in
   one reducer keyed by operation id, so switching methods and switching back preserves what the
   user typed.
5. SizeEstimate: live estimated output size and percentage change, recomputed as params change,
   using the estimate functions from the catalog export. Debounce slider input.
6. availability.ts: one pure module implementing the prototype's rules (source format, model
   family, required bit width, target equals source) with a table-driven test covering every method
   against every sample model.

Vitest + Testing Library tests for: the availability table, show-if behaviour, defaults, required
field blocking, and estimate math. Storybook stories for each component including empty and
all-disabled states. Screenshot both themes at 1280 and 390, compare to the prototype, fix
differences. Update docs/FRONTEND.md and docs/PROGRESS.md.
```

**Done when:** selecting a technique and a method with its parameters behaves exactly like the prototype, and adding a fake param to the catalog JSON shows up in the UI with no code change.

---

### Day 4: Model panel, uploads and the mock backend

```text
Build the model side of the app, and the mock backend the whole frontend will develop against.

1. src/mocks/: MSW handlers for the entire API surface we will build later:
   GET /api/catalog, POST /api/uploads (+ part URLs and complete), POST /api/models/import-hf,
   GET /api/models, GET /api/models/{id}, POST /api/jobs, GET /api/jobs/{id},
   POST /api/jobs/{id}/cancel, GET /api/jobs. The handlers simulate realistic timing, progress and
   failures, including format detection and the simulated results from docs/ui-prototype.html. A
   dev-only panel toggles scenarios: slow network, upload failure at part 3, job failure, quota
   exceeded, expired session. MSW runs in dev when VITE_USE_MOCKS=true, and in all Vitest tests.
2. src/api/client.ts: one typed fetch wrapper (base URL, auth header hook, JSON parsing, typed
   errors, abort support) plus TanStack Query hooks: useCatalog, useModel, useModels, useJob,
   useCreateJob, useCancelJob. Retry rules: no retry on 4xx, exponential backoff on 5xx.
3. ModelPanel: the dropzone (drag states, click to pick, accepted extensions), the sample buttons
   from the prototype, the detected-details list (file, format, size, parameter count, inputs), the
   model-type selector, the optional validation-data input, and the GGUF notice. A loading state
   while the model is being checked, and an error state with retry.
4. Upload: S3-style multipart upload from the browser against MSW, with a progress bar, speed and
   time remaining, pause/resume, per-part retry with backoff, and a warning before leaving the page
   mid-upload. Reject oversized or wrong-type files before any request goes out.
5. Hugging Face import: a second tab in the dropzone, a repo id input with inline validation, an
   optional token field, and a clear error for gated repos.

Tests: upload happy path, a part that fails twice then succeeds, a rejected file type, detection
failure, and the sample buttons. Stories for every state. Screenshot both themes at both widths,
compare to the prototype, fix differences. Update docs/PROGRESS.md.
```

**Done when:** you can "upload" a 2 GB fake file with working progress and resume, the panel shows the detected details, and every failure scenario in the dev panel renders a sensible state.

---

### Day 5: Running a job, progress and results

```text
Build the job lifecycle UI in apps/web/src/features/job/, still against MSW.

1. The run button: its label changes with context exactly as the prototype does ("Compress with
   FP16 weights", "Convert to ONNX", "Train the student model", "Add training data to continue"
   when a required param is missing), and it is disabled while a job runs.
2. A confirmation step before expensive jobs: when the catalog marks an operation as GPU or
   long-running, show estimated time and cost and require confirmation. Never for cheap CPU jobs.
3. JobProgress: the staged checklist from the prototype (done / active / pending dots), a per-epoch
   progress bar for training stages, elapsed time, a cancel button with confirmation, and a
   "reconnecting" state when polling fails. Poll with TanStack Query at a 2-second interval that
   backs off to 10 seconds when document.hidden, and stops on a terminal state.
4. ResultPanel: the headline percentage, the before/after size ruler with its animation (disabled
   under prefers-reduced-motion), the metrics table in both forms (real accuracy when validation
   data exists, output similarity otherwise; perplexity for LLMs), the speed note, download, and
   "Try other settings".
5. Error states that teach: out of memory, unsupported operator (naming it), bad calibration data,
   gated model, quota exceeded, Spot interruption and retry. Each says what happened and what to do
   next, with a link to retry with adjusted settings. Never show a raw stack trace.
6. Resilience: refreshing the page during a job restores the progress view from the job id in the
   URL, and a job that finishes while the tab is hidden shows its result when you come back.

Tests: the full run flow, cancel, each error state, polling backoff when hidden, and restore after
reload. Stories for every state including a 40-epoch training job mid-run. Screenshot and compare.
Update docs/PROGRESS.md.
```

**Done when:** you can run every scenario from the dev panel and the UI is never confusing, blank or stuck.

---

### Day 6: App shell, routes, auth screens and accessibility

```text
Finish the frontend as a complete application, still with no real backend.

1. App shell: header (logo, nav, theme toggle, account menu), footer, container widths, page
   transitions, a global toast system, and an error boundary with a friendly fallback.
2. Routes: / (landing), /app (the tool), /login, /signup, /verify, /forgot-password, /dashboard,
   /settings, /pricing, 404. Route-level code splitting with a loading skeleton.
3. Landing page: hero, the technique comparison table reused from the app, supported formats, how
   it works in three steps, and a call to action. Same tokens, no new styles.
4. Auth screens: sign up, email verification code, log in, forgot and reset password, plus a
   "Continue with Google" button. Inline validation and error messages, a password strength hint,
   and a disabled+spinner state on submit. They talk to a mock auth provider behind one interface
   (src/auth/provider.ts) so day 8 can swap in Cognito without touching the screens.
5. A route guard that redirects to /login and returns the user where they were afterwards, plus a
   session-expired toast.
6. Dashboard and settings shells with empty states ("No models yet", with a link to upload).
7. Accessibility and polish pass: run axe on every route and fix all violations; check tab order,
   focus traps in modals, a skip link, heading hierarchy, prefers-reduced-motion, 200% zoom and
   contrast in both themes. Add a Lighthouse CI check with budgets (performance 90+, accessibility
   100) and lazy-load anything heavy.
8. Playwright end-to-end tests against MSW covering: sign up, log in, upload, pick a method, run,
   see the result, download, cancel, and log out.

Screenshot every route in both themes at 1280 and 390, open them, compare to the prototype, fix
differences. Write the final component map into docs/FRONTEND.md and update docs/PROGRESS.md.
```

**Done when:** the full app is clickable end to end with no backend, axe reports zero violations, and the Playwright suite passes in CI.

---

## Backend track (days 7 to 18)

### Day 7: Data layer on DynamoDB

```text
Add persistence with a single DynamoDB table (on-demand billing, $0 when idle).

Design a single-table schema with PK/SK and one GSI covering:
- User (profile, plan, settings, Hugging Face token encrypted with KMS)
- Model (filename, S3 key, size, format, family, bits, parameter count, details, status)
- Dataset (calibration | training | validation)
- Job (operation id, params, queue, status, progress, result, error, timings, cost)
- JobEvent (stage, message, percent, timestamp) with a TTL so events expire
- Usage counters per user per month

Write the access patterns into docs/decisions.md first, then the key design.

Implement a typed repository layer tested against LocalStack. Every read and write is scoped to a
user id; add a test proving one user cannot read another's model or job. Set TTL attributes so old
jobs, events and models expire instead of accumulating storage cost.

Update docs/PROGRESS.md.
```

**Done when:** repository tests pass against LocalStack and the access patterns are documented.

---

### Day 8: Login with Cognito

```text
Add authentication with Amazon Cognito (free up to 10,000 monthly active users) and wire it into
the auth screens built on day 6.

1. infra/: a CDK "AuthStack" with a user pool (email sign-in, verification, password policy,
   optional TOTP), a hosted domain, a public app client using authorization code + PKCE, and Google
   as an optional identity provider (credentials read from SSM Parameter Store, skipped if absent).
   Callback URLs for localhost:5173 and a placeholder production domain. Use Cognito's built-in
   email sending for now (free, low daily limit) and note SES as the later upgrade. Deploy only
   this stack, to dev, and confirm it costs $0.
2. apps/web: implement src/auth/provider.ts against aws-amplify/auth so the day 6 screens work
   unchanged. Attach the access token to API requests, refresh it silently, and handle expiry with
   the session-expired toast rather than a blank page. Keep the mock provider for tests.
3. apps/api: verify Cognito access tokens (cached JWKS, issuer, client id, expiry, token_use),
   create the user record on first request, expose a current_user dependency. Tests use a fake JWKS
   so they run offline.

List the values I must put in .env files and where cdk deploy prints them.
Update docs/PROGRESS.md and docs/COSTS.md.
```

**Done when:** you can sign up, confirm by email, log in and reach /app, an unauthenticated API call returns 401, and no day 6 screen needed changing.

---

### Day 9: Uploads straight to S3

```text
Implement real uploads, keeping model bytes out of Lambda entirely. The frontend upload flow from
day 4 should keep working with only its base URL changed.

1. POST /api/uploads returns presigned S3 multipart part URLs (100 MB parts); a complete endpoint
   finishes the upload. Enforce per-plan size limits and the extensions from the prototype
   (.onnx, .tflite, .h5, .hdf5, .keras, .pt, .pth, .bin, .ckpt, .safetensors, .gguf) plus dataset
   types (.zip, .tar, .csv, .jsonl, .parquet, .txt, .npz).
   Keys: users/{user_id}/models/{model_id}/{filename}.
2. Hugging Face import by repo id with the user's optional token; the download happens in a worker.
3. On completion, create the model with status "checking" and enqueue a detect_format job that
   fills in format, family, bit width, parameter count and input shapes: exactly the fields
   ModelPanel displays, including the GGUF note. Detection inspects file contents, not just the
   extension, and never unpickles anything.
4. S3 CORS, plus lifecycle rules deleting uploads and results after 7 days (30 on paid plans).
5. Switch dev off MSW for these endpoints (keep the handlers for tests) and verify the real flow.

Update docs/PROGRESS.md.
```

**Done when:** a 2 GB file uploads from the browser against LocalStack and appears with the correct detected format, with no model bytes passing through the API.

---

### Day 10: Jobs, queues and progress

```text
Build the job system so no compute runs when there are no jobs, and connect it to the day 5 UI.

1. GET /api/catalog serves packages/catalog; the frontend stops using its local copy.
2. POST /api/jobs validates params against the operation's JSON Schema, re-checks availability for
   that model, checks the user's quota, writes the job and sends an SQS message to cpu-jobs or
   gpu-jobs.
3. A dispatcher Lambda triggered by the queue submits an AWS Batch job with the right job
   definition and the job id. Nothing polls, nothing idles.
4. workers/core: download inputs from S3, run the operation, upload results, write JobEvent rows
   per stage (and per epoch, matching the UI's training bar), heartbeat, requeue once on a Spot
   interruption, mark success or failure, always clean up local files. Jobs are idempotent and
   self-terminate at a configurable timeout (default 2 hours).
5. GET /api/jobs/{id} returns status plus events, shaped exactly like the MSW handler so the UI
   needs no changes. Cancel: queued jobs dropped, running jobs check a cancel flag between stages,
   Batch jobs terminated. Download returns a short-lived presigned URL.

Test end to end locally with LocalStack and a worker container, using a tiny generated ONNX model.
Update docs/PROGRESS.md.
```

**Done when:** a job runs queued → running → succeeded with live stages in the real UI, and killing the worker mid-job causes a retry rather than a stuck job.

---

### Day 11: Worker images and the first quantization methods

```text
Create the worker runtime and the first operations from the prototype's Quantization tab.

Images in workers/images/ (pinned versions, a lock file per image, slim final layers):
- cpu-torch: PyTorch CPU, ONNX, ONNX Runtime, onnxconverter-common, safetensors, Ultralytics
- cpu-tf: TensorFlow, tf2onnx, onnx2tf

Operations:
- FP16 and BF16 for ONNX, PyTorch (TorchScript and state_dict), Keras and safetensors, refusing
  16-bit inputs exactly as the interface does.
- INT8 dynamic for ONNX Runtime, PyTorch and TFLite.
- The output-similarity check: run original and result on the same random inputs and report cosine
  similarity, largest difference and top-1 agreement, handling NCHW vs NHWC layout differences.

Each operation declares its image and queue in packages/catalog. Add a pytest for every operation
using tiny models generated inside the test, and check the output loads in its target runtime.
Compare each real output size against the catalog's estimate and flag any that are far off.

Update docs/PROGRESS.md.
```

**Done when:** every method in this batch passes a round-trip test and its real output size lands near the interface's estimate.

---

### Day 12: INT8 static and real accuracy

```text
Add calibrated quantization and true accuracy measurement.

- INT8 static: ONNX Runtime quantize_static (min/max, entropy, percentile; per-channel option) and
  TFLite full-integer conversion with a representative dataset, driven by the user's calibration
  upload and the sample-count parameter from the interface.
- Validation datasets: image classification (zip of class folders), detection (YOLO or COCO zip),
  text classification (CSV/JSONL), language modelling (txt/JSONL).
- Evaluators: top-1/top-5, mAP50-95, accuracy/F1, perplexity. Run on original and result with the
  same preprocessing; let the user set input size, mean/std and channel order for vision models.
- Store before/after numbers in the job result so ResultPanel shows real accuracy when validation
  data exists and the output-similarity check when it doesn't, exactly as the prototype does.

Update docs/PROGRESS.md.
```

**Done when:** an INT8 static run on a real small classifier reports believable accuracy before and after.

---

### Day 13: Conversions

```text
Implement the Convert tab, except TensorRT and Core ML (day 18):

ONNX (from PyTorch, TorchScript, Keras, YOLO, and HF LLMs via Optimum, with opset and dynamic-batch
options), TFLite (from Keras, ONNX via onnx2tf, YOLO, PyTorch through ONNX), TorchScript (from ONNX
via onnx2torch, PyTorch, YOLO), TensorFlow SavedModel, safetensors, and OpenVINO IR with
FP32/FP16/INT8 weights.

Chained conversions: when no direct path exists, the catalog exposes the chain (e.g. PyTorch → ONNX
→ TFLite) and the worker runs both steps inside one job, reporting each as a stage in the UI.

Hide conversions whose target equals the source format, as the interface does. Validate every
output by loading it in its runtime and comparing outputs with the original.

Update docs/PROGRESS.md.
```

**Done when:** every conversion visible in the interface works, or is correctly hidden for that format.

---

### Day 14: LLM quantization

```text
Add the LLM methods from the interface.

1. cpu-llm image with llama.cpp built from source. GGUF: convert_hf_to_gguf.py then llama-quantize
   for Q8_0, Q6_K, Q5_K_M, Q4_K_M, Q3_K_M and Q2_K, with the optional importance matrix
   (llama-imatrix) using the user's calibration text or a bundled default. Also plain GGUF
   conversion (F32, F16, BF16, Q8_0) for the Convert tab. Keep these on the CPU queue: far cheaper
   than GPU and fast enough.
2. gpu image: GPTQ and AWQ via llm-compressor (bits, group size, calibration dataset WikiText-2 /
   C4 / user upload, activation ordering, GEMM or GEMV) and bitsandbytes NF4 with double
   quantization and compute dtype. Output must load in Transformers and vLLM.
3. Perplexity before and after, displayed as the interface expects for LLMs.
4. Gated Hugging Face models: a clear error when the user's token lacks access, plus a note that
   they must accept the model's licence.

GPU code must be testable without a GPU: add a CPU test mode using a tiny random Llama config.
Update docs/PROGRESS.md.
```

**Done when:** a GGUF Q4_K_M of a small real model loads in llama.cpp and the GPU methods pass their CPU-mode tests.

---

### Day 15: Pruning

```text
Implement the Pruning tab.

- Magnitude (unstructured): global or per-layer, sparsity 10-95%, saved as sparse tensors or dense
  zeros, for PyTorch, Keras, safetensors and ONNX.
- Structured channel/filter pruning with torch-pruning (L1, L2, Taylor) producing a genuinely
  narrower model; Keras via the TF Model Optimization toolkit.
- 2:4 semi-structured sparsity.
- One-shot LLM pruning: Wanda and SparseGPT through llm-compressor, unstructured or 2:4.
- workers/core/train.py: a shared fine-tuning loop with mixed precision, checkpoints to S3 each
  epoch, resume after a Spot interruption, per-epoch progress events (which the day 5 UI already
  renders), and the dataset formats from day 12. Pruning, low-rank and distillation all use it.

Report measured sparsity, parameter count and median latency before and after.
Update docs/PROGRESS.md.
```

**Done when:** structured pruning at 30% gives a smaller and faster model, and a fine-tuning run resumes after you kill the worker.

---

### Day 16: Low-rank factorization

```text
Implement the Low-rank tab.

- Truncated SVD for Linear/Dense layers and optionally attention projections: rank chosen by energy
  kept or by a fixed fraction; skip layers where factorizing wouldn't save parameters; replace each
  layer with two smaller ones.
- Tucker-2 and CP decomposition for Conv2d layers via tensorly.
- Optional fine-tuning through the day 15 loop.
- Report the per-layer ranks chosen and the parameter saving.

Tests: outputs stay close at high energy, parameter counts drop as predicted, and real file sizes
land near the interface's estimates.

Update docs/PROGRESS.md.
```

**Done when:** SVD at 95% energy on a small transformer keeps outputs close and shrinks the file.

---

### Day 17: Knowledge distillation

```text
Implement the Distillation tab.

- Response-based: any runnable format can be the teacher (ONNX Runtime or TFLite for inference when
  it isn't PyTorch). Students: same architecture at half width or half depth, a compact preset, or
  a user-uploaded student. Loss = alpha * KL(teacher/T, student/T) * T^2 + (1 - alpha) * task loss,
  using the temperature and alpha controls from the interface.
- Feature-based: also match intermediate features with small learned adapters, for PyTorch,
  TorchScript, Keras and YOLO teachers.
- LLM distillation: layer-dropped or smaller same-family student, trained on teacher-generated or
  user text, with the token-budget option.
- All of it uses the shared training loop, runs on the GPU queue, and exports the student in the
  teacher's format where possible.
- Feed the estimated duration and cost into the confirmation step the UI already has, and make
  cancel stop the job promptly.

Update docs/PROGRESS.md.
```

**Done when:** distilling a small classifier into a half-width student runs end to end with epoch progress in the browser.

---

### Day 18: TensorRT and Core ML

```text
Finish the converters.

- TensorRT engines from ONNX (FP32, FP16, INT8 with calibration), built on a GPU worker whose GPU
  matches the target the user picked. State clearly that an engine runs only on that GPU model and
  TensorRT version. For targets we don't run (such as Jetson), don't build: hand the user the ONNX
  file and a ready trtexec command instead.
- Core ML via coremltools (FP32, FP16) from PyTorch, TorchScript, Keras and YOLO.
- A separate tensorrt worker image so its size doesn't slow other jobs down.

Update docs/PROGRESS.md.
```

**Done when:** everything in the interface's Convert tab is implemented or clearly explained.

---

## Deployment and launch (days 19 to 25)

### Day 19: Deploy the low-cost stack

```text
Write infra/ so `cdk deploy --all -c env=dev` creates the whole app with no always-on resources.

- NetworkStack: a VPC with public subnets only and no NAT gateway. Batch tasks get public IPs with
  outbound-only security groups. Record the trade-off in docs/decisions.md.
- DataStack: DynamoDB (on-demand, TTL on, point-in-time recovery off in dev), S3 buckets
  (encrypted, public access blocked, CORS, lifecycle deletion), SQS queues with dead-letter queues.
- ApiStack: FastAPI on Lambda via Mangum, API Gateway HTTP API, 7-day log retention, and reserved
  concurrency to cap spend.
- WebStack: S3 + CloudFront with origin access control, /api routed to the API on the same domain,
  security headers, CloudFront's default certificate until I add a domain, long cache headers on
  hashed assets and no-cache on index.html.
- AuthStack from day 8 with production callback URLs.
- BatchStack: a Fargate Spot compute environment for CPU jobs (min 0 vCPUs), job definitions per
  image, ECR repositories with a lifecycle rule keeping only the last 3 images.
- Alarms: dead-letter queue depth, Lambda errors, and an AWS Budgets alarm at $20/month by email.

Then write docs/COSTS.md: every resource, whether it costs anything at idle, and the per-job cost.
Print the tear-down command. Deploy to dev and run a real FP16 job end to end from the browser.
Update docs/PROGRESS.md.
```

**Done when:** the dev site is reachable, a CPU job runs on Fargate Spot, and `docs/COSTS.md` shows an idle cost near zero.

---

### Day 20: GPU jobs and spending controls

```text
Add the GPU compute environment and hard cost limits.

- BatchStack: an EC2 compute environment using g6.xlarge and g5.xlarge on Spot, min 0 vCPUs, max
  vCPUs capped at my quota, with an on-demand fallback queue that is disabled by default.
- Limits enforced before a job is queued: maximum concurrent jobs per user, monthly CPU and GPU
  minutes by plan, maximum model size, and a maximum job duration passed to Batch as a timeout so
  nothing can run away.
- Record real cpu_seconds and gpu_seconds per job from Batch, store them in the usage counters and
  the job's cost field, and show remaining quota in the UI.
- A daily Lambda emailing me yesterday's spend by tag, and a kill switch (an SSM parameter) that
  stops new GPU jobs being queued, with a clear message in the UI when it is on.

Run one real GPTQ job on a small model, then tell me exactly what it cost.
Update docs/COSTS.md and docs/PROGRESS.md.
```

**Done when:** a GPU job starts a Spot instance that disappears afterwards, and setting the GPU quota to zero blocks the next one.

---

### Day 21: Dashboard and model library

```text
Fill in the dashboard shell from day 6, reusing existing components and tokens only.

- My models: format, size, date, actions (compress, convert, download, delete), with the empty
  state already designed.
- Job history with filters (status, technique, date), each row showing size change, accuracy change
  and cost. Pagination via the DynamoDB cursor.
- Compare view: several results from one original model side by side (size, accuracy, latency) with
  a small chart.
- Re-run with edited settings, prefilled from the previous job.
- Storage used against the plan limit, with a clear note about the retention period.
- Settings: profile, notifications, Hugging Face token, delete account (removes all S3 objects and
  DynamoDB items, behind a typed confirmation).

Stories and tests for empty, loading, error and full states. Screenshot both themes at both widths.
Update docs/PROGRESS.md.
```

**Done when:** a user with several jobs can compare them, re-run one, and delete everything they own.

---

### Day 22: Plans and payments

```text
Add plans, quotas and optional payments.

- Plans in one config file: Free (e.g. 500 MB models, CPU methods only, 20 jobs/month, 7-day
  retention) and Pro (larger models, GPU methods, more jobs, 30-day retention).
- Stripe Checkout and Customer Portal for upgrade and cancellation, with a webhook (signature
  verified, idempotent) that updates the plan. Keys in SSM Parameter Store. Test mode only.
- The /pricing page from day 6, filled in. Using the per-job costs in docs/COSTS.md, propose price
  points that stay profitable once GPU methods are included, and show the workings.
- Upgrade prompts where a limit is hit, never as a blocking modal.

Update docs/PROGRESS.md.
```

**Done when:** a Stripe test card upgrades a user and GPU methods unlock for them.

---

### Day 23: CI/CD

```text
Set up deployments with GitHub Actions and no stored AWS keys.

- A GitHub OIDC provider and least-privilege deploy roles for dev and prod, created in CDK.
- Pull requests: lint, type-check, unit tests, Playwright against MSW, Lighthouse budgets, and
  `cdk diff` posted as a comment.
- Merge to main: build and push only the worker images whose folder changed (layer caching, tagged
  with the git SHA), deploy to dev, run a smoke test (sign in as a test user, run a tiny ONNX FP16
  job).
- Release: the same to prod behind a manual approval.
- Frontend: build, sync to S3, invalidate CloudFront.
- Keep CI minutes low: cache pip, npm, Playwright browsers and Docker layers; never rebuild the GPU
  or TensorRT images unless they changed.

Document rollback in docs/decisions.md. Update docs/PROGRESS.md.
```

**Done when:** a small UI change deploys itself to dev, and a release deploys to prod after approval.

---

### Day 24: Security and testing

```text
Review the whole codebase for security and robustness, and fix what you find.

- Untrusted model files: pickled PyTorch files must load only in a worker with no credentials
  beyond its own job's S3 prefix, no inbound access and a hard timeout; Keras safe_mode on; zip
  extraction limits (path traversal, zip bombs, maximum decompressed size); file type checked by
  content rather than extension.
- API: per-user and per-IP rate limits, request size limits, strict parameter validation against
  the catalog schemas, short-lived presigned URLs, CORS locked to the site's origin, no user data
  in logs.
- Frontend: a Content Security Policy with no unsafe-inline, tokens kept out of localStorage where
  possible, no secrets in the bundle, and a dependency review of anything touching file input.
- Dependencies: pip-audit and npm audit in CI, ECR image scanning.
- Tests: the Playwright suite re-pointed at the dev deployment as a nightly smoke test, plus a
  small load test of the API.

Write docs/SECURITY.md listing the protections and any remaining risks.
Update docs/PROGRESS.md.
```

**Done when:** end-to-end tests pass against dev in CI and nothing high-risk remains open.

---

### Day 25: Launch

```text
Prepare the launch.

- Landing page content finalised: what ModelForge does, the four techniques (reusing the comparison
  table), supported formats, pricing, and an FAQ covering accuracy loss, privacy, retention and
  model licences.
- Terms of service and privacy policy drafts for me to have reviewed, stating that users must hold
  the rights to what they upload and that files are deleted after the retention period.
- 404 and 500 pages, a maintenance banner behind a flag, favicon, social preview image and
  open-graph tags.
- An admin page for a Cognito "admins" group: users, jobs, failures, spend, cancel a job, change a
  plan.
- docs/LAUNCH.md checklist: budget alarm tested, dead-letter queue alarm tested, one run of every
  operation on sample models in prod, a restore test of the DynamoDB table, and a check of every
  route in both themes on a real phone.

Update docs/PROGRESS.md.
```

**Done when:** every item in `docs/LAUNCH.md` is ticked.

---

## 6. Keeping the bill near zero afterwards

- Everything scales to zero, so your floor is the hosted zone, ECR storage and a little S3.
- S3 lifecycle rules delete models and results on schedule; DynamoDB TTL removes old jobs and events.
- CloudWatch retention stays at 7 days everywhere.
- GPU work is Spot-only, capped by per-user quotas, a job timeout and the SSM kill switch.
- Lambda reserved concurrency caps the worst case if someone hammers the API.
- The budget alarm emails you at $20. Raise it deliberately, not by accident.
- When you pause development: `cdk destroy --all -c env=dev`.

## 7. Later, when there is traffic

- Swap polling for WebSockets only if polling ever shows up on the bill.
- Cache `/api/catalog` in CloudFront; it's identical for every user.
- Move heavy CPU jobs to Graviton (ARM) Fargate for roughly 20% less.
- Add pipelines: prune, then fine-tune, then quantize in a single job.
- Add device-targeted recommendations, an API key and CLI for teams, and more formats (ExecuTorch, MLX, TensorFlow.js, FP8).
