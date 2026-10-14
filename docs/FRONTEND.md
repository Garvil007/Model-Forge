# Frontend

Reference for `apps/web`'s design-token system, UI primitives, theming and tooling. Visual source
of truth is `docs/ui-prototype.html`; every value below traces back to it.

## Tokens (`src/styles/tokens.css`)

CSS custom properties on `:root`. No component may hardcode a hex color or a raw px font-size or
spacing value — `stylelint` enforces this (see below).

- **Color**: `--paper`, `--panel`, `--ink`, `--muted`, `--line`, `--soft`, `--accent`,
  `--on-accent`, `--lossless`, `--near`, `--lossy`, `--notice-bg`, `--error-bg`, `--b-ok`,
  `--b-near`, `--b-lossy`. Redefined for dark mode twice: under
  `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }` for the
  `system` choice, and under `:root[data-theme="dark"]` for an explicit choice.
- **Spacing**: `--space-0` (1px) through `--space-10` (40px), covering every gap/padding value
  used in the prototype plus the 1–2px micro-offsets used by visually-hidden inputs and the
  Toggle's switch knob.
- **Radii**: `--radius-sm` (6px), `--radius-md` (8px), `--radius-lg` (10px), `--radius-pill`.
- **Field widths**: `--field-max-width` (440px, the prototype's `.field select` etc. cap),
  `--field-range-width` (360px, the prototype's `.params .range` cap).
- **Type**: `--font-family`, `--font-size-xs` through `--font-size-xl`, plus
  `--font-size-headline`/`--font-size-display` (the prototype's `clamp()` headline sizes),
  `--line-height-tight/snug/base`, `--font-weight-regular/medium/semibold/bold`.
- **Focus**: `--focus-ring` / `--focus-ring-offset`, matching the prototype's
  `:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }` exactly.

## Theming (`src/ui/theme`)

`ThemeProvider` exposes `{ choice, setChoice }` via `useTheme()`, where `choice` is
`'light' | 'dark' | 'system'`.

- `system` removes `data-theme` from `<html>`, letting the `prefers-color-scheme` media query in
  tokens.css drive colors.
- `light` / `dark` set `data-theme` explicitly, overriding the media query.
- The choice persists to `localStorage` under the key `modelforge.theme`, read/written through
  `theme-storage.ts`; both operations are wrapped in `try/catch` since storage access can throw in
  private browsing or when disabled.
- `ThemeToggle` is the header control — a three-way `radiogroup` (Light / Dark / System).

## Primitives (`src/ui/<Name>/`)

Each primitive is a folder with `Component.tsx`, `Component.module.css`, `Component.test.tsx` and
`Component.stories.tsx`. CSS Modules only — no UI framework, no Tailwind.

| Component | Variants / notes |
| --- | --- |
| `Button` | `primary` (prototype `.run`), `secondary`, `link` (prototype `.link`); `disabled`; `loading` renders an inline `Spinner` and sets `aria-busy`. |
| `Chip` | Prototype `.chip` — sample-model picker buttons. |
| `Panel` | Prototype `.panel` — the two-column layout's section containers. |
| `Tabs` | Prototype `.tabs`. Roving `tabIndex`; `ArrowLeft`/`ArrowRight` move focus and selection, `Home`/`End` jump to the ends. |
| `Badge` | `lossless` / `near-lossless` / `lossy`, colors from `.badge.*`. |
| `Select`, `TextInput`, `NumberInput` | Prototype `.field select` / `.params input[type=text|number]` look; optional `help` renders a `<small>`. |
| `Range` | Slider + live `<output>` readout, prototype `.params .range`. Accepts `unit` (e.g. `%`). |
| `Toggle` | Switch control (`role="switch"`) built from token colors — the prototype only has a bare checkbox (`.params .check`), so this is a new, consistent component rather than a direct lift. |
| `FileInput` | Two exports: `DropZone` (prototype `.drop`, drag-over state) and `FileInput` (prototype `.params input[type=file]`, supports `required`). |
| `Spinner` | The prototype's `.active .dot` spin animation, extracted as a standalone indicator; respects `prefers-reduced-motion`. |
| `Notice` | `info` (new — soft/line, no prototype equivalent), `warning` (prototype `.notice`), `error` (prototype `.error`). Error renders `role="alert"`, others `role="status"`. |
| `Skeleton` | Loading placeholder, not in the prototype; pulse animation respects `prefers-reduced-motion`. |
| `Tooltip` | Minimal accessible tooltip, not in the prototype; shows on focus/hover, `role="tooltip"`. |

All interactive primitives are fully keyboard-operable and inherit the global
`:focus-visible` ring from tokens.css.

## Stylelint

`stylelint.config.js` extends `stylelint-config-standard` and adds:

- `color-no-hex: true` — no raw hex colors outside `tokens.css`.
- `declaration-property-value-disallowed-list` on `font-size`, `width`, `height`, `padding`,
  `margin`, `gap`, `border-radius`, `top`/`left`/`right`/`bottom` — rejects any literal `px` value
  in those properties. `tokens.css` itself is exempted (it's where the literals live).

Run via `npm run lint:css --prefix apps/web`, which `npm run lint` (and so `make lint`) calls
alongside ESLint.

## Storybook

`apps/web/.storybook/` (Storybook 10 — the prototype plan called for Storybook 8, but the
repo's Vite 8 toolchain only has `@storybook/react-vite` peer support from Storybook 10 onward, so
the project was scaffolded on the current stable line instead). A story per primitive covers every
variant/state listed above. The toolbar's "Theme" control (light/dark) applies `data-theme` to the
preview document via a decorator in `preview.tsx`; the viewport addon ships `Desktop 1280` and
`Mobile 390` presets matching the screenshot widths below.

Run with `make storybook` (`npm run storybook --prefix apps/web`, port 6006).

## Screenshots

- `make shot PAGE=<url>` — screenshots one URL at 1280px and 390px, in both themes (by toggling
  `data-theme` directly on the loaded page), into `apps/web/.screenshots/`.
- `make shot-stories` — builds Storybook, serves the static output locally, and screenshots every
  story at both widths and in both themes (via Storybook's `?globals=theme:<light|dark>` query
  param) into the same directory. Filenames encode story id, width and theme, e.g.
  `ui-button--primary-1280-dark.png`.

Both scripts live in `apps/web/scripts/` and use Playwright (Chromium).

## Catalog feature (`src/features/catalog/`)

The operation-picking UI is driven entirely by `packages/catalog`'s exported `catalog.json` — no
catalog data is hand-maintained in the frontend.

- **Types** (`generated/`): `make types` runs `python -m modelforge_catalog.export` to write
  `catalog.json` + `catalog.schema.json` into `generated/`, then `json2ts` (json-schema-to-typescript,
  `npm run generate:types --prefix apps/web`) turns `catalog.schema.json` into
  `generated/catalog.types.ts` (`Catalog`/`Technique`/`Operation`/`Param`/...). Re-run `make types`
  whenever `packages/catalog`'s dataclasses change shape; `catalog.json`/`catalog.schema.json` are
  regenerated data, `catalog.types.ts` is generated code — none of the three is hand-edited.
- **`types.ts`**: loads `generated/catalog.json` as `CATALOG` and exposes `getTechniques()`,
  `getMethods()`/`getConverts()`/`getMethodsForTechnique()`, `getOperationById()`,
  `defaultParamValues()`, plus the `ModelInfo`/`ParamValues` types (mirrors
  `packages/catalog/.../models.py`'s `ModelInfo`, which the catalog export deliberately omits).
- **`availability.ts`**: `checkAvailability(op, model)` — pure port of the prototype's rules
  (GGUF lock, source format, model family, required bit width, target-equals-source) — and
  `sortByAvailability()` (available first, stable order). Table-driven test covers every
  catalog operation against a sample model per format/family.
- **`paramVisibility.ts`**: `isParamShown`/`visibleParams`/`missingRequiredLabels` — evaluates a
  param's `showIf`/`onlyFor` and reports which required, visible params still need a value.
- **`sizeEstimateFormulas.ts`**: one estimator per operation id, a direct TS port of the
  prototype's `size`/`ratio` closures (also mirrored server-side in `methods.py`/`converts.py`,
  which deliberately don't ship their Python callables to the frontend). `estimateOutputBytes()`
  returns `null` when the size can't be known yet (e.g. a custom distillation student).
- **`paramsReducer.ts`**: one `useReducer` keyed by operation id (`ParamsState`), so switching
  methods and switching back preserves what the user typed; defaults are filled in lazily via
  `ensure-defaults` the first time an operation's values are read.
- **Components**: `TechniqueTable` (the four-column comparison table doubling as a keyboard
  radio group — arrow keys move focus, Space/Enter selects; stacks below 640px with "How:"/
  "Impact:" labels), `MethodList`/`MethodRow` (sorts available methods above unavailable ones,
  shows the disabled reason instead of metadata), `MethodParams` (schema-driven: dispatches
  `param.type` to `Select`/`Range`/`Toggle`/`NumberInput`/`TextInput`/`FileInput`, falls back to
  `param.default`, filters by `showIf`/`onlyFor` — adding a param to the catalog needs no frontend
  change), `SizeEstimate` (debounces param changes via `useDebouncedValue` before recomputing).

Every module above has a Vitest + Testing Library test and every component has a Storybook story
(including empty/all-disabled states); `npm run shot-stories` screenshots them in both themes at
1280/390 alongside the rest of `src/ui`.

## Mock backend (`src/mocks/`)

MSW (`msw@3`) serves the entire planned API surface so `src/features` can be built against a
realistic backend before `apps/api` has routes. `src/mocks/browser.ts` (`setupWorker`) runs in dev
when `VITE_USE_MOCKS=true` (see `main.tsx`'s `enableMocking()`, and `apps/web/.env`, which defaults
it on since there's no real API yet); `src/mocks/server.ts` (`setupServer`) runs in every Vitest
test via `src/test/setup.ts`.

- **`handlers.ts`**: `GET /api/catalog` (serves `features/catalog/generated/catalog.json`
  directly — one source of truth), `POST /api/uploads` + `PUT /api/uploads/:id/parts/:n` +
  `POST /api/uploads/:id/complete` (S3-style multipart), `POST /api/models/import-hf`,
  `GET /api/models[/:id]`, `POST /api/jobs`, `GET /api/jobs[/:id]`, `POST /api/jobs/:id/cancel`.
  Jobs simulate a generic three-stage run (`db.ts`'s `JOB_STAGE_LABELS`) derived from elapsed time,
  not the catalog's real per-method stages — full job fidelity is Day 5's job.
- **`db.ts`**: in-memory `Map`s for models/uploads/jobs, reset after every test (`resetDb()`,
  called from `test/setup.ts`'s `afterEach`).
- **`scenarios.ts`** + **`ScenarioPanel.tsx`**: dev-only toggles (slow network, a specific upload
  part number failing its first two attempts, job failure, quota exceeded, expired session),
  persisted to `sessionStorage`, rendered on the home page only when `VITE_USE_MOCKS=true`.
- **`data.ts`**: Hugging Face repo fixtures for `import-hf`, reusing
  `features/model/sampleModels.ts` so the sample buttons and the mock import never drift.

## API layer (`src/api/`)

- **`types.ts`**: hand-written DTOs (`ApiModel`, `ApiJob`, `CreateUploadResponse`, ...) — what the
  mocks serve and the real API should eventually match, not the other way around.
- **`client.ts`**: `apiClient.get`/`post`/`putRaw`, a typed `ApiError` (status + code + message),
  an `setAuthToken()` hook for the eventual Cognito integration (Day 8), and abort-signal support.
- **`queryClient.ts`**: `createQueryClient()` — no retry on 4xx, exponential backoff (capped 30s)
  otherwise; used by `main.tsx` in place of a bare `new QueryClient()`.
- **`hooks.ts`**: `useCatalog`, `useModels`, `useModel`, `useImportHf`, `useJob` (polls every 400ms
  while `queued`/`running`), `useCreateJob`, `useCancelJob`.

## Model feature (`src/features/model/`)

The "Your model" panel (`ModelPanel`) — upload a file, pick a sample, or import from Hugging Face.

- **`detectFormat.ts`**: `detectModel()`, a TS port of the prototype's `fromFile()` — extension to
  format, filename heuristics for family/YOLO, rejects unsupported extensions
  (`UnsupportedFormatError`) and oversized files (`OversizedFileError`, 5 GB cap) before any
  request goes out.
- **`sampleModels.ts`**: the prototype's `SAMPLES`, typed as `DetectedModel` — reused by both the
  dropzone's sample chips and `mocks/data.ts`'s Hugging Face fixtures.
- **`useFileUpload.ts`**: drives the multipart flow (`POST /uploads` → per-part `PUT` with up to 4
  attempts and exponential backoff → `POST /uploads/:id/complete`) and reports progress/speed/ETA;
  `pause`/`resume`/`cancel` via refs polled between parts.
- **Components**: `ModelDropzone` (drag/drop + click + sample chips, built on `ui/FileInput`'s
  `DropZone`), `DetectedDetails` (properties list, model-type override, validation-data input,
  GGUF notice), `UploadProgress` (bar, speed, ETA, pause/resume/cancel), `HfImportForm` (repo id
  format validation, optional token, gated-repo error), `ModelPanel` (orchestrates all of the
  above: a 400ms "checking" state, a retryable error state, and a `beforeunload` warning while an
  upload is in flight).

Tests cover the upload happy path, a part that fails twice then succeeds, a rejected file
extension, an oversized-file detection failure, the sample buttons, and the Hugging Face form's
validation/success/gated-repo paths — all against the real MSW handlers, not mocked fetch calls.
Storybook stories exist for every component's states; the full prototype screenshot-diff matrix
(both themes, both widths) wasn't run for this feature — see `docs/PROGRESS.md`'s Day 4 entry.

## App shell, routing and auth (`src/app/`, `src/auth/`, `src/routes/`)

The app has no prototype equivalent of its own — `docs/ui-prototype.html` is a single tool page.
Everything below is new UX built on the same tokens/primitives, not a port.

### Routing (`src/App.tsx`, `src/main.tsx`)

`react-router-dom` v7 with `<BrowserRouter>`. Every route component is `React.lazy`-loaded and
wrapped in one `<Suspense fallback={<PageSkeleton />}>` around the whole `<Routes>` tree, so a
route-chunk fetch shows the skeleton instead of a blank page. All routes nest under one
`<Route element={<AppShell />}>` so header/footer/skip-link are never duplicated per page.

| Path | Component | Guarded |
| --- | --- | --- |
| `/` | `routes/LandingPage` | no |
| `/app` | `routes/ToolPage` | yes |
| `/login` | `routes/auth/LoginPage` | no |
| `/signup` | `routes/auth/SignupPage` | no |
| `/verify` | `routes/auth/VerifyPage` | no |
| `/forgot-password` | `routes/auth/ForgotPasswordPage` | no |
| `/dashboard` | `routes/DashboardPage` | yes |
| `/settings` | `routes/SettingsPage` | yes |
| `/pricing` | `routes/PricingPage` | no |
| `*` | `routes/NotFoundPage` | no |

Provider nesting in `main.tsx`: `ErrorBoundary` → `QueryClientProvider` → `ThemeProvider` →
`ToastProvider` → `BrowserRouter` → `AuthProvider` → `App`. `ToastProvider` sits outside the
router/`AuthProvider` so a toast (e.g. session-expired) survives a redirect; `ErrorBoundary` sits
outermost so it can catch an error from any provider below it.

### App shell (`src/app/`)

- **`AppShell`**: skip-to-content link (focusable via `transform: translateY` rather than a raw
  negative-px offset, per the stylelint `declaration-property-value-disallowed-list` rule),
  `Header`, `<main id="main-content">` wrapping `<Outlet />` (keyed by `location.pathname` for a
  `prefers-reduced-motion`-respecting fade between pages), `Footer`.
- **`Header/Header`**: logo (`Link` to `/`), primary nav (`Tool`/`Pricing`, hidden below 640px),
  `ThemeToggle` (existing Day 2 component), `Header/AccountMenu`.
- **`Header/AccountMenu`**: a plain "Log in" link when signed out; a `role="menu"` dropdown
  (click-outside and Escape close it) with Dashboard/Settings/Log out when signed in.
- **`Footer`**: copyright + Pricing/Support links.
- **`ErrorBoundary`**: class component, catches render errors anywhere below it in the tree and
  renders a "Something went wrong" panel with a reload button and a collapsed technical-details
  `<details>`, instead of a blank white screen.
- **`PageSkeleton`**: the `Suspense` fallback, built from the Day 2 `Skeleton` primitive.

### Toasts (`src/ui/toast/`)

A new `ui/` primitive, not a prototype port: `ToastProvider` (`useState` + per-toast
`setTimeout`), `useToast()` → `{ toasts, showToast, dismissToast }`, `ToastViewport` (fixed
bottom-right stack, `aria-live="polite"`, `role="alert"` for the `error` variant only). Used for
the session-expired notice and a couple of auth confirmations (password reset, resent code).

### Auth (`src/auth/`)

- **`provider.ts`**: the single swap point named in the spec — exports `authProvider: AuthProvider`
  (the interface in `types.ts`) backed today by `mockAuthProvider.ts`
  (`localStorage`-backed users/session, a fixed `123456` confirmation code, ~400ms simulated
  latency). Swapping in Cognito later means rewriting `createMockAuthProvider()`'s call site in
  `provider.ts`, not touching any screen.
- **`AuthContext`/`useAuth`/`AuthProvider`**: a thin React-context wrapper over `authProvider`
  exposing `user`, `isLoading`, and one method per `AuthProvider` operation, plus `expireSession()`
  (clears the user and shows the session-expired toast — not wired to a real 401 yet since there's
  no real API, but ready for Day 8).
- **`RouteGuard`**: redirects to `/login` with `state: { from: location }` when `!user`;
  `LoginPage` reads that state to return the user to where they were.
- **`passwordStrength.ts`**: pure `scorePassword`/`passwordStrengthLabel`/`isPasswordValid` —
  the signup form's strength hint.
- **`GoogleButton`**: "Continue with Google" — calls the mock provider's `signInWithGoogle()`
  (returns a fixed demo user) and a success callback.

### Auth screens (`src/routes/auth/`)

- **`AuthLayout`**: shared `Panel` + heading + `<form noValidate>` + optional footer chrome, reused
  by all four screens so "one Panel, consistent field spacing" doesn't get rewritten four times.
- **`LoginPage`**: email/password, inline validation before any network call, a form-level
  `Notice` for `AuthApiError`, `GoogleButton`, links to sign up / forgot password.
- **`SignupPage`**: email/password/confirm, live strength hint (`passwordStrengthLabel`),
  mismatch/length validation, navigates to `/verify?email=...` on success.
- **`VerifyPage`**: reads `email` from the query string, 6-digit code input, "Resend code" (shows
  a toast), navigates to `/app` on success.
- **`ForgotPasswordPage`**: two internal stages (`request` → `reset`) in one component — email
  first, then code + new password — so "forgot and reset password" is one route per the spec,
  not two.

### Other routes (`src/routes/`)

- **`LandingPage`**: hero, the catalog's `TechniqueTable` reused as-is (same component, same
  tokens, live `useState` selection — no new styles per the spec), a static supported-formats chip
  row, a three-step "how it works", two CTAs.
- **`ToolPage`**: the former `HomePage` body (`ModelPanel` + dev-only `ScenarioPanel`) plus the new
  `features/catalog/OperationPanel` once a model has a real backend id.
- **`features/catalog/OperationPanel`** (new, not a page): the piece that was missing to make the
  tool usable end to end — Compress/Convert tabs, `TechniqueTable` on Compress,
  `MethodList`/`MethodParams`/`SizeEstimate`/`JobRunner` for whichever operation is selected. Takes
  `model: ApiModel`, so it only renders once a model has a real id (an uploaded file or a Hugging
  Face import); a picked sample has no backend id, so `ToolPage` shows an info `Notice` instead
  ("Sample models are for browsing methods only — upload a file or import from Hugging Face to run
  a job") — a deliberate scope cut, not an oversight, since wiring samples to a fake backend id
  would risk a job the user can never actually re-fetch by id.
- **`DashboardPage`** / **`SettingsPage`**: empty-state shells ("No models yet" → link to `/app`;
  settings shows the signed-in email) — Day 21/22's job to fill in.
- **`PricingPage`**: three static plan cards.
- **`NotFoundPage`**: heading + link home, the `*` route.

### Accessibility and performance

- `make shot`/`node scripts/shot-authed.mjs` screenshot every new route (public routes via the
  former; `/app`, `/dashboard`, `/settings` via the latter, which seeds a mock session into
  `localStorage` before navigating) at 1280/390 in both themes — spot-checked, no issues beyond
  one header-link wrap fixed below.
- `e2e/a11y.spec.ts` (`npx playwright test e2e/a11y.spec.ts`) runs `@axe-core/playwright` against
  every public route (both themes) plus `/app`/`/dashboard`/`/settings` signed in — **zero
  violations**, verified by an actual run, not just written and assumed green. Getting there
  required two real fixes, not configuration: (1) axe was catching the `Suspense` fallback
  (`PageSkeleton`, no `<main>`/`<h1>`) because routes are lazy — the spec now waits for the
  `Header`'s implicit `banner` landmark before analyzing; (2) `tokens.css` never styled bare `<a>`
  tags, so plain links (footer, 404, auth-screen "Log in"/"Sign up") kept the browser default blue
  (`#0000ee`), which fails contrast on the dark panel background (1.73:1 vs. the 4.5:1 minimum) —
  fixed with one `a { color: var(--accent); }` rule.
- `lighthouserc.cjs` (`npm run lhci` / `make lhci`) runs Lighthouse CI against `/`, `/pricing`,
  `/login` with `performance >= 0.9` and `accessibility === 1` as hard (`error`-level) assertions.
  A real run scored 1.0/1.0 on both categories for all three URLs.
- `e2e/flows.spec.ts` (`npm run test:e2e` / `make e2e`) covers, against the real MSW mocks (not a
  second mock layer): sign up → verify → land on `/app` → log out → log back in; upload a model →
  pick INT8 dynamic → run → see the result → click download; start a job → cancel it mid-run. All
  three pass against a real Chromium run.
