# Progress

Update at the end of every day. Check items off as "Done when" criteria pass.

- [x] Day 0: Accounts and setup — files exist, CLAUDE.md matches how you want to work.
- [x] Day 1: Monorepo, shared catalog and local stack — `make api` and `make web` verified live
      (health check / dev server both respond); `make test` and `make lint` pass end to end;
      catalog test proves parity with the prototype. `make up` (LocalStack via docker compose)
      is written and reviewed but unverified live — Docker Desktop's daemon wasn't running in
      this environment, so `docker compose up` itself hasn't actually been exercised yet.
- [x] Day 2: Design tokens, primitives and the screenshot loop — `src/styles/tokens.css` carries
      every color/spacing/radius/type value from the prototype plus light/dark redefinitions; 15
      CSS-Module primitives (Button, Chip, Panel, Tabs, Badge, Select, NumberInput, TextInput,
      Range, Toggle, FileInput, Spinner, Notice, Skeleton, Tooltip) plus a `ThemeProvider` /
      `ThemeToggle` live under `src/ui`, each with a Storybook story and a Vitest + Testing
      Library test (62 tests, all green). Storybook had to move to v10 (not 8 as originally
      planned) since `@storybook/react-vite` only supports the repo's Vite 8 from v10 onward —
      see `docs/FRONTEND.md`. `make shot-stories` captured all 32 stories at 1280px/390px in both
      themes (128 PNGs in `apps/web/.screenshots/`); spot-checked against the prototype, no
      visual mismatches found. `stylelint` (custom config) rejects raw hex colors and px
      font-size/spacing outside `tokens.css`; wired into `make lint`. `make test` and `make lint`
      pass end to end for `apps/web`.
- [x] Day 3: The catalog-driven core — `apps/web/src/features/catalog/` is fully data-driven:
      `make types` exports `catalog.json`/`catalog.schema.json` from `packages/catalog` and
      generates `catalog.types.ts` via json-schema-to-typescript, so the catalog can't drift from
      the UI. `TechniqueTable` (keyboard radio group, stacks below 640px), `MethodList`/`MethodRow`
      (available methods sort above unavailable, disabled reason shown instead of metadata),
      `MethodParams` (schema-driven over select/range/check/number/text/file, show-if, required
      marking, defaults — adding a param to the catalog needs zero frontend changes, verified by
      a test), and `SizeEstimate` (debounced live estimate) are built on `availability.ts`
      (table-driven test, every catalog operation against sample models per format/family),
      `paramVisibility.ts`, `sizeEstimateFormulas.ts` (TS port of the prototype's size/ratio
      formulas) and a `paramsReducer` keyed by operation id so typed values survive switching
      methods and back. 260 tests total, all green; Storybook stories (incl. empty/
      all-disabled states) screenshot-matched against the prototype in both themes at 1280/390 —
      no visual mismatches. `make test` and `make lint` pass end to end. See `docs/FRONTEND.md`.
- [x] Day 4: Model panel, uploads and the mock backend — `src/mocks/` (MSW) serves the full API
      surface (`catalog`, `uploads` + parts + complete, `models/import-hf`, `models`, `jobs`) with
      realistic latency and a `ScenarioPanel` dev toggle for slow network, a failing upload part,
      job failure, quota exceeded and expired session. `src/api/client.ts` + `queryClient.ts` +
      `hooks.ts` give typed fetch, no-retry-on-4xx/backoff-on-5xx, and
      `useCatalog`/`useModel`/`useModels`/`useJob`/`useCreateJob`/`useCancelJob`.
      `src/features/model/` has the dropzone + sample buttons, detected-details list (file/format/
      size/params/inputs), model-type override, validation-data input, GGUF notice, a real
      S3-style multipart upload (`useFileUpload`, progress/speed/ETA/pause/resume/per-part retry
      with backoff, leave-page warning, reject-before-request for bad type/oversized), and a
      Hugging Face import tab (repo id validation, optional token, gated-repo error). 287 tests
      total, all green (including upload-happy-path, part-fails-twice, rejected type, oversized
      detection failure, and sample-button tests); `make test` and `make lint` pass end to end.
      Manually verified live against the mock backend (sample button → detected details, no
      console errors) — did not run the full `shot-stories` theme/width screenshot matrix against
      the prototype for this feature, unlike Days 2-3; worth doing before Day 6's a11y pass.
- [x] Day 5: Running a job, progress and results — `src/features/job/` builds the full lifecycle
      against MSW: `runButtonState` ports the prototype's `updateRun()` label logic exactly
      ("Compress with <label>", "Convert to <label>", "Train the student model", "Add <param> to
      continue", disabled while running); `jobConfirmation.ts`'s `isExpensiveOperation` requires a
      confirmation (with a time + cost estimate) for any GPU-queued or hours/days-long operation
      and never for a cheap CPU one. `JobProgress` renders the done/active/pending staged
      checklist with a per-epoch progress bar on training stages, elapsed time, cancel-with-
      confirmation, and a "reconnecting" state (driven by `useJob`'s `failureCount`). `useJob`
      (`src/api/hooks.ts`) polls every 2s, backs off to 10s via `refetchIntervalInBackground` when
      `document.hidden`, and stops once the job is terminal — the interval decision is pulled into
      a pure `jobPollIntervalMs()` so the backoff itself is unit-tested without real timers.
      `ResultPanel` shows the headline percentage, an animated before/after size ruler (plain CSS
      transition, disabled under `prefers-reduced-motion`), the metrics table in both forms (real
      accuracy when the model has validation data, output similarity otherwise — mock worker in
      `src/mocks/handlers.ts` decides which), a speed note, download and "Try other settings".
      `JobError` teaches six failure codes (out of memory, unsupported operator — named — bad
      calibration data, gated model, quota exceeded, spot interruption) with what happened and
      what to do next, never a raw stack trace; the mock worker's `jobErrorKind` scenario
      (`ScenarioPanel`) drives all of them. The job id round-trips through the URL
      (`useSearchParams`) so a reload restores the progress/result view from the mock backend's
      current job state, and polling continuing in the background means a job that finishes while
      the tab is hidden is already showing its result by the time you come back. 349 tests total,
      all green (including the full run flow, cancel, every error state, and the URL-restore
      path); stories cover every state, including a 40-epoch training job mid-run. `make test`
      and `make lint` pass end to end. Did not run the `shot-stories` screenshot matrix against
      the prototype for this feature (no reference in the prototype to diff against — it has no
      error/progress/result markup of its own beyond the inline simulation) — worth a manual pass
      before Day 6's a11y work.
- [x] Day 6: App shell, routes, auth screens and accessibility — the full app is clickable end to
      end with no backend: a `react-router-dom` route tree (10 routes, all lazy-loaded behind one
      `Suspense`) under an `AppShell` (header with logo/nav/theme toggle/account menu, footer, skip
      link, reduced-motion page fade), a global toast system (`src/ui/toast/`), and an
      `ErrorBoundary` with a friendly fallback. Auth (`src/auth/`) is a mock provider behind one
      swappable interface (`provider.ts`) — sign up, email-code verification, log in, forgot/reset
      password (one two-stage screen), "Continue with Google" — plus a `RouteGuard` that redirects
      to `/login` and returns the user afterward, with a session-expired toast. The landing page
      reuses the catalog's `TechniqueTable` verbatim (no new styles); `ToolPage` gained the
      previously-missing `OperationPanel`, wiring `MethodList`/`MethodParams`/`SizeEstimate`/
      `JobRunner` (built Days 3 and 5 but never connected to a page) into one usable flow — upload
      or Hugging-Face-import a model, pick a method, run it, see the result, download. Dashboard
      and settings are empty-state shells for later days. 387 Vitest tests total, all green
      (`make test`); `make lint` passes. `e2e/a11y.spec.ts` (axe via Playwright) actually ran
      against every route in both themes — **zero violations**, including two real fixes it
      caught: the lazy-route `Suspense` fallback had no landmark/heading, and `tokens.css` never
      styled bare `<a>` tags so plain links kept the browser's default blue (fails contrast in
      dark mode). `lighthouserc.cjs` (`make lhci`) actually ran against `/`, `/pricing`, `/login`
      with `performance >= 90` / `accessibility === 100` as hard assertions — scored 1.0/1.0 on
      both for all three. `e2e/flows.spec.ts` (`make e2e`) covers sign up → verify → log in/out,
      upload → pick a method → run → see result → download, and start-job → cancel — all three
      passed against a real Chromium run, not just written. Screenshotted every new route at
      1280/390 in both themes (`make shot`, and a new `make shot-authed` for the three guarded
      routes) and spot-checked against the prototype's tokens/spacing — no mismatches beyond one
      header-link wrap at 390px, fixed. See `docs/FRONTEND.md`'s "App shell, routing and auth"
      section for the full component map. Not done: Storybook stories for the new shell/page
      components (tests exist for all of them; stories were judged lower-value for one-off pages
      vs. reusable primitives, given the time this phase already took — worth reconsidering before
      Day 19 if these pages grow more interactive states).
- [x] Day 7: Data layer on DynamoDB — `packages/db` (`modelforge_db`) is a new shared package
      (alongside `packages/catalog`) holding a typed repository per entity (`UserRepository`,
      `ModelRepository`, `DatasetRepository`, `JobRepository`, `JobEventRepository`,
      `UsageRepository`) over one single-table design: table `modelforge`, one GSI (`GSI1`),
      on-demand billing. Every item's base-table `PK` starts with `USER#<userId>` (job events:
      `USER#<userId>#JOB#<jobId>`), so ownership is structural — there's no query shape that
      returns another user's item. `docs/decisions.md` ("Day 7: Single-table DynamoDB schema")
      has the full access-pattern table and the key design (GSI1 overloaded across
      Model/Dataset/Job listings plus the user-by-email lookup) and why `PK` embeds the user id
      directly rather than an `ownerId` filter checked after the fact. The Hugging Face token is
      envelope-encrypted with KMS (`KmsEncryptor`) before it ever reaches a DynamoDB item.
      `ttl.py` sets per-entity retention (JobEvents 14 days, Jobs 90, Models 365; User/Usage
      items never expire) and the table has native TTL enabled on the `ttl` attribute, so old
      jobs/events/models age out without a cleanup job. 34 tests in `packages/db/tests/`
      (`test_users`, `test_models`, `test_datasets_and_usage`, `test_jobs_and_events`, `test_ttl`,
      and `test_isolation` — which proves user A gets nothing, not an error that would leak
      existence, when it tries to get/list/update/delete user B's model or job, or list B's job
      events) ran live against a real LocalStack container (`docker compose up`, table + GSI1 +
      TTL + KMS key created per test session) — all 34 passed, not just written. `ruff check` and
      `mypy src` pass for `packages/db`. `infra/localstack/init-aws.sh` and `docker-compose.yml`
      were updated to match (table renamed from the old `modelforge-jobs` placeholder to
      `modelforge`, GSI1 + TTL + a KMS key added for local `make up` dev use); `Makefile` and
      `.github/workflows/ci.yml` run `packages/db`'s tests and lint, with a LocalStack service
      container added to the CI `test` job so the integration tests actually run there too, not
      just locally. Not done: wiring the repositories into `apps/api` endpoints or `workers` —
      out of scope for this day, which was the data layer itself; that's Days 8-10's job as auth,
      uploads and the job queue land.
- [x] Day 8: Login with Cognito — `infra/stacks/auth_stack.py` is a new CDK `AuthStack`: a
      user pool (email sign-in/verification, 12-char password policy requiring upper/lower/
      digit/symbol, optional TOTP MFA, `EMAIL_ONLY` account recovery), a hosted domain, a
      public app client (no secret — authorization-code + PKCE, since Cognito requires PKCE
      once a client has no secret) and an **optional** Google identity provider: `cdk synth`
      checks SSM Parameter Store for `/modelforge/<env>/google-client-id` and
      `-client-secret` (metadata only, via `describe_parameters` — the secret's value is
      never read at synth time, only resolved by CloudFormation at deploy time via
      `SecretValue.ssm_secure`) and adds the provider only if both exist; `GoogleIdpEnabled`
      is `false` in this environment, confirmed by a real `cdk synth` run. Email delivery
      uses Cognito's own built-in sender (free, low daily cap) — SES is the noted upgrade
      once volume needs it (`docs/COSTS.md`). `infra/tests/test_auth_stack.py` (6 tests, a
      fake SSM client so they're offline) proves the single user pool, the hosted domain,
      the client's `GenerateSecret: false` + `AllowedOAuthFlows: [code]`, the Google IdP
      being skipped when absent *and* added when present, and the `UserPoolId`/
      `UserPoolClientId`/`HostedDomain` outputs. Only this stack was synthesized/tested here
      — not deployed to a real AWS account from this session; see the deploy command and the
      `.env` values it prints in the handoff notes.
      `apps/web/src/auth/`: `cognitoAuthProvider.ts` implements the existing `AuthProvider`
      interface against `aws-amplify/auth` (sign up with `autoSignIn`, confirm, sign in, the
      Google button via `signInWithRedirect` to the hosted UI, forgot/reset password), so
      `provider.ts` swaps between it and the Day 6 mock behind one `VITE_AUTH_PROVIDER` env
      var — every Day 6 screen and its tests are unchanged. `attachTokenSync` (Amplify `Hub`
      listener) keeps `apiClient`'s bearer token in sync on sign-in and silent refresh, and
      routes a failed refresh to `expireSession()` — the existing session-expired toast, not
      a blank page. `apps/api/app/auth.py` verifies the access token Cognito issues: a
      `PyJWKClient` per issuer (built-in TTL cache, no refetch per request) checks signature,
      issuer, expiry, `token_use == "access"`, and `client_id` match; `current_user`
      provisions a `UserRecord` via `packages/db`'s `UserRepository` on first sight of a
      `sub` and reuses it after. `apps/api/tests/test_auth.py` (5 tests, a fake JWKS client —
      fully offline) covers missing token (401), wrong `token_use`, wrong `client_id`,
      expired token, and first-request user creation not duplicating on a second request.
      `make test`/`make lint` pass end to end across `infra`, `apps/api`, and `apps/web`
      (387 web tests still green, unchanged). Not done: actually deploying the stack and
      pointing a running app at it — that's an AWS action with real account side effects,
      left for the user to run (or ask for) explicitly.
- [ ] Day 9: Uploads straight to S3 — `POST /api/uploads` creates an S3 multipart upload and
      returns presigned `upload_part` URLs (100 MiB parts, S3 key
      `users/{user_id}/models/{model_id}/{filename}`); `POST /api/uploads/{id}/complete` lists
      parts, verifies size, completes the upload, creates the model at `status: "checking"`,
      and enqueues a `detect_format` message on a new dedicated `system-jobs` SQS queue (kept
      separate from Day 10's `cpu-jobs`/`gpu-jobs` so a sub-second detection doesn't wait behind
      a Batch/Fargate cold start). `POST /api/models/import-hf` checks repo metadata
      (`huggingface_hub`, 404/403/400/502 mapped per `HfImportForm.tsx`'s error handling),
      stores the optional token KMS-encrypted, and enqueues `import_hf`. Per-plan limits: Free
      2 GiB/7-day retention, Pro+Team 5 GiB/30-day (`packages/catalog/plans.py`); the model's
      DynamoDB TTL is set to retention+1 day so the record outlives the S3 object.
      `workers/ops/detect.py` identifies format from file contents (GGUF binary header,
      safetensors JSON header, ONNX via `onnx`'s protobuf loader, HDF5 `.h5`/`.keras` via
      `h5py`) and **never unpickles** torch's `.pt`/`.pth`/`.bin`/`.ckpt` zip checkpoints — it
      decodes the pickle stream with `pickletools.genops` (opcode decode only, nothing
      instantiated or called) just to read storage dtypes, and gets actual tensor byte counts
      from the zip's own member sizes, never from executing the pickle graph; `torch`,
      `tensorflow`/`keras`, `dill` and `joblib` are deliberately absent from
      `workers/pyproject.toml`. `infra/storage_rules.json` is the single source of truth for S3
      CORS + lifecycle (7d/30d tag-based expiration, 30-day untagged catch-all, abort-incomplete
      after 1 day), consumed by both the new `StorageStack`/`QueueStack` CDK stacks and
      `infra/localstack/init-aws.sh`. Frontend: fixed a real bug found while wiring this up —
      the Day 4 upload hook was PUTting part bytes to the API itself (`apiClient.putRaw`
      against `/uploads/.../parts/N`) rather than to S3, which would have blown both the "no
      model bytes through the API" rule and API Gateway's payload limit; added
      `apiClient.putPresigned` and pointed `useFileUpload` at `upload.partUrls` instead — the
      MSW mock's part URLs were already shaped this way, so no mock or test changed. Also
      added a try/catch around the initial `POST /uploads` (it could leave the UI stuck
      "uploading" forever on a server rejection) and `useModel` polling while
      `status ∈ {importing, checking}` so `ModelPanel` shows the server's real detected values,
      not just the client-side guess, once the worker finishes. `VITE_LIVE_API_PATHS` (new
      `.env.development`, commented out by default) lets `apps/web/src/mocks/browser.ts`
      bypass MSW for `/api/uploads` and `/api/models` in local dev only — `server.ts` (tests)
      imports the handlers directly and is unaffected, and `vite.config.ts` proxies `/api` to
      `apps/api` for whatever MSW lets through.
      **Not run live in this session:** no Docker daemon was available here (same limitation
      noted on Day 1), so `make up`/`make api`/`make worker` and the real browser→LocalStack
      upload flow were written and reviewed but not executed — someone with Docker should run
      `make up && make api && make worker && make web`, set `VITE_LIVE_API_PATHS` in
      `apps/web/.env.development`, and try a real upload before trusting this day's "done
      when". **Also left for a follow-up, not done here:** TFLite detection only checks the
      `TFL3` magic bytes and reports a size-based estimate (no FlatBuffers schema parsing);
      CDK tests for `StorageStack`/`QueueStack`; a Playwright spec against the live stack; an
      AST-level guard test banning `pickle`/`torch`/etc. imports under `workers/ops/detect*`
      (the dependency list already omits them, but no test enforces it); subprocess-level
      sandboxing (timeout/memory limits) around detection parsing; `docs/decisions.md`,
      `FRONTEND.md` and `COSTS.md` entries for this day's design choices.
- [ ] Day 10: Jobs, queues and progress — `GET /api/catalog` serves `packages/catalog` live;
      `apps/web`'s `main.tsx` fetches it at bootstrap and calls the new `setCatalog()` instead of
      the module ever reading only the bundled `generated/catalog.json` (that file stays as the
      `make types` codegen source and the MSW/test fixture — `src/test/setup.ts` seeds it the
      same way so all 387 existing web tests needed zero changes). `POST /api/jobs` validates
      `values` against `build_param_schema(op)` (`jsonschema`), re-checks availability with a new
      `modelforge_catalog.availability.check_availability` (a line-for-line port of the
      frontend's `availability.ts`, since the API only ever sees model metadata, never the file
      itself), enforces a new `PlanLimits.max_concurrent_jobs` (free 2, pro/team 10) against the
      user's own queued/running jobs, then writes the job via the existing `JobRepository` and
      sends a message — a new, deliberately separate `job_messages.py` schema, not
      `system_jobs.py`'s — to `cpu-jobs` or `gpu-jobs` by the operation's `.queue`. Nothing reads
      that queue until a job exists: idle app, idle compute, as intended.
      A dispatcher Lambda (`infra/lambda/dispatcher/`) consumes `cpu-jobs`/`gpu-jobs`, re-checks
      the job is still `queued` (skips a redelivered or already-canceled message rather than
      double-submitting), and submits to AWS Batch through a `BatchJobClient` abstraction —
      `RealBatchJobClient` (boto3) for prod, `LocalBatchJobClient` (runs the worker in-process)
      for local dev/tests, since LocalStack Community has no Batch emulation at all. `workers/
      core` actually executes a job now: idempotent dispatch (a terminal-status job is a no-op,
      handling SQS at-least-once redelivery), downloads the model from S3, runs the operation,
      uploads the result, writes a `JobEvent` per stage (stage labels come from a new
      `job_stages.py`, ported from the mock's `jobStages.ts` and imported by both the API — to
      reconstruct `JobStage[]` for `GET /api/jobs/{id}` — and the worker, so they can't drift), a
      heartbeat touching `updated_at`, a configurable timeout (`MF_JOB_TIMEOUT_SECONDS`, default
      7200) via a background-timer flag checked between stages, and a requeue-once-then-fail path
      for a Spot interruption (shares the same "check a flag between stages" mechanism as
      cancellation — a `JobControl.check()` call the op makes between its stages — differing only
      in what sets the flag: DB status for cancel, a `SIGTERM` handler in prod, an env var hook
      for local testing). Cleanup is `try/finally` over a `TemporaryDirectory`, always. Only one
      operation has real logic end to end: **`q_int8_dyn`** (ONNX Runtime dynamic int8
      quantization) — simplest stage list (3 flat stages, no calibration/epochs), pure Python, no
      GPU. The other 22 catalog operations hit the dispatch table's clean `unsupported_operator`
      failure, which is the deliberate extension point for Days 11+, not a bug.
      `GET /api/jobs/{id}` assembles the exact `ApiJob` shape the Day 5 UI already polls for, so
      the frontend needed no changes beyond one small contract addition: `JobErrorCode` gained a
      `"timeout"` value (`JobError.tsx` + `types.ts`), since a 2-hour timeout had nowhere honest
      to map before. `POST /api/jobs/{id}/cancel`: a `queued` job is dropped by the idempotency
      check at dispatch time (there's no cheap way to pull a specific message back out of SQS);
      a `running` job's status flips immediately and the worker notices between stages, plus
      `BatchJobClient.terminate_job` if a `batch_job_id` was recorded. `GET /api/jobs/{id}/download`
      returns a short-lived presigned S3 URL. `infra/stacks/compute_stack.py` is a new CDK stack
      (Fargate Spot compute environment, cpu/gpu job definitions, the dispatcher Lambda wired to
      both queues via an SQS event source) — `cdk synth`-tested, not deployed; worker container
      images are still placeholders (`busybox`) pending Day 11's real images, and there's no CDK
      DynamoDB table stack yet (the table is LocalStack-only via `init-aws.sh`), so the dispatcher's
      IAM policy scopes to a hardcoded table name as a documented gap.
      **Not run live in this session:** same Docker Desktop limitation as Days 1 and 9 — `make
      e2e-jobs` (the full chain: real `POST /jobs` → SQS → dispatcher → in-process worker → real
      `onnxruntime` quantization of a tiny generated ONNX model → `GET /jobs/{id}` →
      presigned-download) was written, is skip-gated the same way `packages/db`'s LocalStack
      tests are, and collects/skips cleanly, but has never actually executed against live
      LocalStack. Someone with Docker should run `make up && make e2e-jobs` before trusting this
      slice; a known possible gap flagged during implementation is that `StorageService
      .presign_download` may need a LocalStack public-endpoint override to be reachable from
      outside the LocalStack container network — unverified either way. Every other layer's own
      unit/integration tests did run and pass (`packages/catalog`, `packages/db`, `apps/api`,
      `workers`, `infra`, and all 387 `apps/web` tests plus a clean `tsc --noEmit`).
      **Also noted, not fixed (pre-existing, out of scope):** `system_jobs.py`'s `build_message`/
      `parse_message` round-trip has a key-case mismatch bug; the new `job_messages.py` added for
      real jobs deliberately avoided repeating it rather than fixing the older file.
- [x] Day 11: Worker images and the first quantization methods — every method in this batch
      passes a round-trip test (reloads in its target runtime), real output size checked
      against the catalog's estimate. Two new images under `workers/images/` (multi-stage
      Dockerfiles + a pinned `requirements.lock.txt` each, slim `python:3.12-slim` final
      layer, non-root user): **cpu-torch** (PyTorch CPU, ONNX, ONNX Runtime,
      onnxconverter-common, safetensors, Ultralytics) and **cpu-tf** (TensorFlow, tf2onnx,
      onnx2tf). `workers/pyproject.toml` gained matching `torch-ops`/`tf-ops` optional-dep
      extras — torch and tensorflow stay out of the base `modelforge-workers` install (see
      `ops/detect.py`'s docstring on why detection never touches them), but `dev` now pulls
      both in so the full suite runs locally.
      Two new ops, each dispatching per source-model format rather than one tool fits all:
      `ops/fp_cast.py` (**q_fp16**/**q_bf16**) casts weights to half precision — ONNX via
      `onnxconverter_common.float16` (fp16 only), PyTorch `torch` (state_dict, via
      `torch.load(weights_only=True)` and a recursive tensor-tree cast — fp16 and bf16),
      PyTorch `torchscript` (`.half()` on the loaded `ScriptModule` — fp16 only), Keras
      (rewrites float32 HDF5 datasets to float16 directly with `h5py`, no TensorFlow
      needed to produce the result — fp16 only), and `safetensors` (`safetensors.torch`,
      fp16 and bf16). `ops/quantize_dynamic.py` (**q_int8_dyn**) now dispatches ONNX to
      `onnxruntime.quantization.quantize_dynamic` (unchanged from Day 10), PyTorch
      `torchscript` to `torch.ao.quantization.quantize_jit.quantize_dynamic_jit` — the
      *actual* graph-rewriting API; `torch.quantization.quantize_dynamic` turned out to be
      a silent no-op on an already-scripted/traced module (its children are
      `RecursiveScriptModule` wrappers, never `isinstance(..., nn.Linear)`, so the
      eager-mode type-swap never matches — caught by inspecting the reloaded graph in a
      test, not by any exception), and Keras to `tf.lite.TFLiteConverter` with
      `optimizations=[tf.lite.Optimize.DEFAULT]` — TensorFlow has no in-place
      weights-only dynamic quantizer the way ONNX Runtime and PyTorch do, so this *is*
      "INT8 dynamic" for a Keras source, and the result format changes to `.tflite`
      accordingly. A bare PyTorch `torch` (state_dict) source is refused with
      `unsupported_operator` for `q_int8_dyn` specifically — dynamic quantization needs a
      module to replace layers on, and a state_dict has no architecture; FP16/BF16 don't
      have this problem since casting dtype element-wise needs no architecture at all.
      `core/similarity.py` is the shared output-similarity check (cosine similarity,
      largest absolute difference, top-1 agreement via argmax, with NCHW/NHWC alignment
      before comparing) — used wherever an op can actually execute both the original and
      the result (ONNX, Keras, Keras's TFLite output). Where it can't (a bare state_dict,
      raw safetensors, a TorchScript graph whose serialized form has no static input shape
      to replay after a save/load round-trip — verified empirically, not assumed) it
      reports "not measured (reason)" rather than guessing. 48 worker tests pass
      (`test_fp_cast.py`, `test_similarity.py`, extended `test_quantize_dynamic.py`), each
      building its tiny model inside the test (ONNX via `onnx.helper`, PyTorch via a real
      `nn.Linear`, Keras via `tf.keras.Sequential`, safetensors via
      `safetensors.torch.save_file`) and reloading the real output in its target runtime
      (`onnxruntime.InferenceSession`, `torch.jit.load`/`torch.load(weights_only=True)`,
      `tf.lite.Interpreter`, `safetensors.torch.load_file`) — not just checking bytes
      changed. Every test also checks the real output size against
      `OperationSpec.size_estimate(ModelInfo, {})` within a loose 0.1x-10x band (a
      hand-built matrix is nowhere near the smooth-scaling regime those formulas assume;
      the formulas are tuned against real models, not a 64x64 test fixture) — nothing came
      back far enough off to flag.
      **Known gaps, left for a follow-up:** `infra/stacks/compute_stack.py`'s
      `_WORKER_IMAGES` still only has `cpu-base`/`gpu-base` with the Day 10 placeholder
      busybox image — wiring real `cpu-torch`/`cpu-tf` job definitions (and an ECR push)
      is Day 11+ infra work, not done here. Neither image was actually built or run with
      Docker (same Docker Desktop limitation noted on Days 1, 9 and 10) — both Dockerfiles
      are written and reviewed, and every package they install was verified by installing
      it directly into this environment's venv and running the real test suite against it,
      but `docker build` itself hasn't been exercised. `q_fp16`'s `yolo` source format
      (declared in the catalog, matching the prototype) has no caster yet — a job for it
      hits the same clean `unsupported_operator` "no worker implementation" message other
      not-yet-built operations already use. TorchScript's "not measured" similarity result
      is a deliberate scope decision, not a missing feature: a serialized TorchScript
      graph's input `TensorType.sizes()` comes back `None` after a save/load round-trip
      (checked directly, not assumed), so there's no honest way to synthesize a matching
      input without the model's declared shape.
      **Security, flagged by automated review, partly addressed:** `tf.keras.models.load_model`
      now passes `safe_mode=True, compile=False` (rejects Lambda-layer/arbitrary-callable
      configs, skips optimizer deserialization) and the PyTorch state_dict path already
      used `torch.load(..., weights_only=True)`. What's *not* addressed here, because it's
      an `infra/` concern, not something a worker op module can fix on its own: these jobs
      still run with the worker's full IAM credentials and a credentialed boto3 client
      rather than per-object pre-signed URLs, and there's no seccomp/gVisor sandbox around
      `torch.jit.load` or `tf.keras.models.load_model` — both still parse untrusted bytes
      from the user's uploaded file. Worth a dedicated pass before any of this touches
      production traffic.
- [x] Day 12: INT8 static and real accuracy — INT8 static run on a real small classifier reports believable accuracy before and after.
      **Dataset persistence (apps/api + packages/db):** `POST /uploads/{id}/complete` for
      `kind="dataset"` now actually persists a `DatasetRecord` via `DatasetRepository.create`
      instead of echoing an unpersisted dict (a pre-existing gap — the repository was fully
      implemented but never called). Added `GET /datasets` and `PATCH /models/{id}/validation`
      (`{datasetId, taskType, preprocess?}`) to attach a labeled validation set to a model —
      validation data lives at the model level, reused across every op/job on it, matching the
      prototype. Neither endpoint opens the uploaded file; only ownership/id/schema are checked
      in apps/api, per the "workers only open model/dataset files" rule.
      **Catalog (packages/catalog):** new `validation.py` — `TaskType` (`image_cls`/`detection`/
      `text_cls`/`lm`), `PreprocessSpec` (input size/mean/std/channel order/layout, vision
      defaults), `TASK_TYPE_INFO` (accepted extensions + metric label + `lower_is_better` per
      task), `format_metric()` for the two "X (was Y)" / "X before, Y after (lower is better)"
      display conventions the prototype and `ResultPanel` already use. Fixed `q_int8_static`
      missing `worker_image="cpu-torch"` (present on sibling `q_int8_dyn`, missing here — a
      pre-existing bug). Added a `"dataset"` param type (schema-equivalent to `"file"`, but lets
      apps/api branch on "this value must be an owned dataset id" without hardcoding the param
      name) and switched `calib` to it.
      **Workers — dataset loaders (`workers/core/datasets/`):** `imagefolder.py` (ImageFolder-zip
      image classification), `detection.py` (YOLO-zip or COCO-zip, auto-detected), `text.py`
      (CSV/JSONL text classification), `lm.py` (txt/JSONL language modeling), `calibration.py`
      (unlabeled zip-of-images or `.npy`/`.npz`, feeding `q_int8_static`'s calibration). All
      zip loaders go through `base.py`'s `safe_extract_zip` (zip-slip rejection, file-count and
      total-size caps) and respect `max_samples` + cooperative `JobControl.check()` so
      cancellation/timeout still work mid-load. `.npy`/`.npz` loading refuses
      `allow_pickle=True` unconditionally. A security review during this work flagged a second
      path-traversal vector in `detection.py`'s COCO loader (an `annotations.json` `file_name`
      joined straight into a filesystem path, with no containment check) — fixed with a new
      `safe_join()` helper in `base.py` shared with the zip-slip check, and the fix no longer
      echoes the attacker-supplied filename in the error message; covered by a new regression
      test (`test_coco_file_name_path_traversal_is_rejected`).
      **Workers — evaluators (`workers/core/evaluators/`):** top-1/top-5 (`topk.py`), accuracy +
      macro-F1 (`cls_f1.py`), perplexity (`perplexity.py`, takes a pre-built tokenizer), and
      mAP50-95 (`map_eval.py`) behind a shared `Evaluator` protocol. `map_eval.py` uses a
      pure-Python, VOC2012-style IoU-matching AP calculation rather than
      `pycocotools.cocoeval.COCOeval` — `pycocotools` is now installed (see below) for other
      callers, but swapping this evaluator onto `COCOeval` needs its own in-memory COCO-JSON
      construction and a dedicated verification pass, left as a follow-up; treat this
      evaluator's numbers as directionally correct; it is covered only by its own unit tests on
      synthetic boxes, not validated against COCO's official reference metric.
      `workers/core/model_runner.py` unifies ONNX Runtime / TFLite / torch/TorchScript inference
      behind one `ModelRunnerProtocol`, so the same evaluator runs against the original and
      quantized model.
      **Workers — `evaluation.py` and `quantize_static.py`:** `evaluate_or_fallback()` is the
      single entry point: if a model has a validation dataset configured, it runs the matching
      evaluator on both models and returns real before/after numbers formatted via
      `format_metric`; otherwise it falls back to the existing random-input `compare_runs`
      similarity check, unchanged. Any failure on the validation-data path (bad format, missing
      tokenizer, S3 error, ...) degrades gracefully to the fallback rather than failing the job,
      with a note explaining why real accuracy wasn't measured — cooperative-cancellation
      exceptions are still re-raised, never swallowed. `q_int8_static` (`workers/ops/
      quantize_static.py`) is the new op: ONNX via `onnxruntime.quantization.quantize_static`
      (QDQ format, minmax/entropy/percentile calibration methods, per-channel option, all
      driven by the catalog's existing params), Keras/SavedModel via `TFLiteConverter` with a
      `representative_dataset` generator for full INT8 conversion, and TorchScript sources via
      auto-export to ONNX first (using the calibration data's own sample shape, since no other
      shape source exists) then the same ONNX path — a clean `unsupported_operator` error if
      export fails. Registered in `runner.py`'s `_OPS_BY_OPERATION_ID`. `quantize_dynamic.py`
      (`q_int8_dyn`) was retrofitted to call `evaluate_or_fallback()` too, as a cheap proof the
      shared layer works for an existing op — but it still passes no `runner_factory`, so it
      only ever takes the fallback path for now; wiring real per-format runners into it so
      `q_int8_dyn` also gets real validation accuracy is a natural follow-up, not done here.
      **Dependencies:** `pillow`, `transformers`, and `pycocotools` added as base deps in
      `workers/pyproject.toml` (needed regardless of which worker image runs the op, since
      evaluation can run on either). Both `workers/images/cpu-torch` and `cpu-tf`
      `requirements.lock.txt` updated with real pip-resolved pins for all three plus their
      transitive deps (`tokenizers`, `regex`, `typer`, `rich`, etc.) — `cpu-tf`'s lock
      previously had no `pillow`/`tqdm`/`filelock`/`fsspec` at all, since nothing on that image
      needed them before. Neither Dockerfile has actually been rebuilt with the new lock files
      in this environment (same Docker Desktop limitation noted on Days 1, 9, 10, 11) — every
      added package was verified by installing it directly into `workers/.venv` and running the
      real test suite (128 passed) against it.
      **Known gaps, left for a follow-up:** text classification and language-modeling
      evaluation need a tokenizer, fetched lazily via `transformers.AutoTokenizer.from_pretrained`
      against the model's HF repo id if it has one — a model with no repo id and no uploaded
      tokenizer degrades to the similarity fallback rather than failing. The detection loader's
      box-coordinate convention (absolute pixels in a resized, non-aspect-preserving square
      frame) is a documented simplification, not a production-grade letterboxed pipeline.
- [ ] Day 13: Conversions — every conversion visible in the interface works, or is correctly hidden for that format.
- [ ] Day 14: LLM quantization — GGUF Q4_K_M of a small real model loads in llama.cpp; GPU methods pass CPU-mode tests.
- [ ] Day 15: Pruning — structured pruning at 30% gives a smaller and faster model; fine-tuning run resumes after killing the worker.
- [ ] Day 16: Low-rank factorization — SVD at 95% energy on a small transformer keeps outputs close and shrinks the file.
- [ ] Day 17: Knowledge distillation — distilling a small classifier into a half-width student runs end to end with epoch progress in the browser.
- [ ] Day 18: TensorRT and Core ML — everything in the interface's Convert tab is implemented or clearly explained.
- [ ] Day 19: Deploy the low-cost stack — dev site reachable, a CPU job runs on Fargate Spot, docs/COSTS.md shows idle cost near zero.
- [ ] Day 20: GPU jobs and spending controls — GPU job starts a Spot instance that disappears afterwards; GPU quota of zero blocks the next job.
- [ ] Day 21: Dashboard and model library — user with several jobs can compare them, re-run one, delete everything they own.
- [ ] Day 22: Plans and payments — Stripe test card upgrades a user and GPU methods unlock for them.
- [ ] Day 23: CI/CD — a small UI change deploys itself to dev; a release deploys to prod after approval.
- [ ] Day 24: Security and testing — end-to-end tests pass against dev in CI, nothing high-risk remains open.
- [ ] Day 25: Launch — every item in `docs/LAUNCH.md` is ticked.
