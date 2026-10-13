# Frontend tooling setup (Day 2)

Every command here runs **inside `apps/web`**, which Day 1 creates. The Day 2 prompt tells Claude Code to do all of this — this file is so you can verify it did, or run it yourself if you prefer.

**Windows note:** the README uses `make shot`, but `make` isn't on Windows by default. Use the npm scripts below instead — they work identically on every platform. If you're in WSL2, either works.

---

## 1. Install everything

```bash
cd apps/web

# Screenshot loop
npm install -D @playwright/test
npx playwright install chromium

# Component workbench
npx storybook@latest init

# Mock backend
npm install -D msw
npx msw init public/ --save

# Token enforcement
npm install -D stylelint stylelint-config-standard
```

`npx storybook@latest init` detects Vite + React and writes `.storybook/` plus example stories. Delete the examples it generates; you're writing your own.

CSS Modules need no install — Vite handles any file named `*.module.css` automatically.

---

## 2. The screenshot script

Create `apps/web/scripts/shot.mjs`:

```js
import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const url = process.argv[2] ?? 'http://localhost:5173';
const name = process.argv[3] ?? 'page';
const widths = [1280, 390];
const themes = ['light', 'dark'];

await mkdir('.screenshots', { recursive: true });
const browser = await chromium.launch();

for (const theme of themes) {
  const ctx = await browser.newContext({ colorScheme: theme });
  const page = await ctx.newPage();
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.waitForTimeout(300);          // let fonts and transitions settle
    const file = `.screenshots/${name}-${theme}-${width}.png`;
    await page.screenshot({ path: file, fullPage: true });
    console.log(file);
  }
  await ctx.close();
}

await browser.close();
```

Add to `apps/web/package.json`:

```json
{
  "scripts": {
    "shot": "node scripts/shot.mjs",
    "storybook": "storybook dev -p 6006",
    "build-storybook": "storybook build",
    "lint:css": "stylelint \"src/**/*.css\""
  }
}
```

### Using it

```bash
# the app, with the dev server already running
npm run shot -- http://localhost:5173/app app

# one Storybook story (get the id from the story's URL)
npm run shot -- "http://localhost:6006/iframe.html?id=ui-button--all-variants" button
```

Each run writes four PNGs into `.screenshots/`: light and dark, 1280px and 390px.

---

## 3. The stylelint rule that enforces tokens

Create `apps/web/.stylelintrc.json`:

```json
{
  "extends": "stylelint-config-standard",
  "rules": {
    "color-no-hex": true,
    "declaration-property-value-disallowed-list": {
      "/^font-size$/": ["/^\\d+px$/"]
    }
  },
  "overrides": [
    {
      "files": ["src/styles/tokens.css"],
      "rules": {
        "color-no-hex": null,
        "declaration-property-value-disallowed-list": null
      }
    }
  ]
}
```

This fails the build if any component file uses a raw hex color or a pixel font size. `tokens.css` is exempt, because that's where the real values live. It's the mechanism that keeps habit 3 from quietly eroding over 25 days.

Wire it into CI by adding `npm run lint:css` to the lint job.

---

## 4. How the screenshot loop actually gets used

This is habit 1, in practice. End any UI prompt with:

```text
Then start the dev server, run:
  npm run shot -- http://localhost:5173/app app
Open the four PNGs in .screenshots/, compare them against docs/ui-prototype.html,
and fix every difference you find. Repeat until they match.
```

Claude Code reads PNGs it has produced, so it can see its own output and correct it. Without this it's writing CSS blind.

Add `.screenshots/` to `.gitignore` (it's already in the Day 0 one). These are working files, not artifacts to commit.

---

## 5. MSW, in one paragraph

`npx msw init public/ --save` writes `public/mockServiceWorker.js`, a service worker that intercepts `fetch` in the browser. Day 4 adds `src/mocks/handlers.ts` defining fake responses for every endpoint, and `src/mocks/browser.ts` to start it when `VITE_USE_MOCKS=true`. For Vitest, a separate `src/mocks/server.ts` uses `setupServer` instead, since there's no browser there.

The point: your components call the real `/api/jobs` through the real `fetch`. On Day 10, when the actual endpoint exists, you change an environment variable and nothing else.

---

## Verify it all works

```bash
cd apps/web
npm run storybook          # opens localhost:6006
npm run dev                # opens localhost:5173, in a second terminal
npm run shot -- http://localhost:5173 home
ls .screenshots            # four PNGs
npm run lint:css           # passes, and fails if you add a hex color to a component
```
