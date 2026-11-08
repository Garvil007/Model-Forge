// Basic load smoke test for the ModelForge API — k6 (https://k6.io), a single static binary
// with no new Node/Python deps to install.
//
// Scope is intentionally narrow: only unauthenticated, read-only, low-risk endpoints that
// don't trigger real compute or cost money.
//   - GET /health   static liveness check
//   - GET /catalog  reads packages/catalog, no user data, no model/job work
//
// Do NOT point this at endpoints under apps/api/app/routers/uploads.py, models.py, jobs.py,
// or datasets.py — those create real jobs that workers pick up and run on real (billed)
// compute. This script never touches them.
//
// Load profile — deliberately small, this is a smoke/availability check, not a stress test:
//   - ramp 0 -> 5 VUs over 15s
//   - hold 5 VUs for 1m (5 VUs * 1 request/sec each ≈ 5 RPS sustained)
//   - ramp 5 -> 0 VUs over 15s
// 5 RPS against two trivial, cache-friendly Lambda routes is well within a single Lambda's
// concurrency and won't meaningfully affect cost or other users of a shared dev environment.
// Bump `stages` below if you need more signal, but keep it modest — this script is meant to
// be run ad hoc / on demand, not as a continuous load generator.
//
// Run manually:
//   MF_API_URL=https://dev-api.example.com k6 run scripts/load/api-smoke.js
// or:
//   make load-test MF_API_URL=https://dev-api.example.com

import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.MF_API_URL;
if (!BASE_URL) {
  throw new Error("MF_API_URL env var is required, e.g. https://dev-api.example.com");
}

export const options = {
  stages: [
    { duration: "15s", target: 5 }, // ramp up
    { duration: "1m", target: 5 }, // hold — ~5 RPS sustained
    { duration: "15s", target: 0 }, // ramp down
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"], // fail the run if >1% of requests error
    http_req_duration: ["p(95)<1000"], // 95th percentile under 1s
  },
};

export default function () {
  const health = http.get(`${BASE_URL}/health`);
  check(health, {
    "GET /health is 200": (r) => r.status === 200,
  });

  const catalog = http.get(`${BASE_URL}/catalog`);
  check(catalog, {
    "GET /catalog is 200": (r) => r.status === 200,
  });

  sleep(1);
}
