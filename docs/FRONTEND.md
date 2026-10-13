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
