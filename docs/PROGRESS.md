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
- [ ] Day 7: Data layer on DynamoDB — repository tests pass against LocalStack, access patterns documented.
- [ ] Day 8: Login with Cognito — sign up, confirm by email, log in, reach /app; unauthenticated API call returns 401; no day 6 screen needed changing.
- [ ] Day 9: Uploads straight to S3 — 2 GB file uploads from browser against LocalStack, correct detected format, no model bytes through the API.
- [ ] Day 10: Jobs, queues and progress — job runs queued → running → succeeded with live stages in the real UI; killing the worker mid-job causes a retry.
- [ ] Day 11: Worker images and the first quantization methods — every method in this batch passes a round-trip test, real output size near the catalog estimate.
- [ ] Day 12: INT8 static and real accuracy — INT8 static run on a real small classifier reports believable accuracy before and after.
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
