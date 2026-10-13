# Progress

Update at the end of every day. Check items off as "Done when" criteria pass.

- [x] Day 0: Accounts and setup — files exist, CLAUDE.md matches how you want to work.
- [x] Day 1: Monorepo, shared catalog and local stack — `make api` and `make web` verified live
      (health check / dev server both respond); `make test` and `make lint` pass end to end;
      catalog test proves parity with the prototype. `make up` (LocalStack via docker compose)
      is written and reviewed but unverified live — Docker Desktop's daemon wasn't running in
      this environment, so `docker compose up` itself hasn't actually been exercised yet.
- [ ] Day 2: Design tokens, primitives and the screenshot loop — Storybook shows every primitive in both themes, screenshots match the prototype, stylelint rejects a hardcoded color.
- [ ] Day 3: The catalog-driven core — selecting a technique/method with params behaves exactly like the prototype; adding a fake param to catalog JSON shows up with no code change.
- [ ] Day 4: Model panel, uploads and the mock backend — "upload" a 2 GB fake file with progress/resume, detected details shown, every dev-panel failure scenario renders sensibly.
- [ ] Day 5: Running a job, progress and results — every dev-panel scenario runs and the UI is never confusing, blank or stuck.
- [ ] Day 6: App shell, routes, auth screens and accessibility — full app clickable end to end with no backend, axe zero violations, Playwright suite passes in CI.
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
