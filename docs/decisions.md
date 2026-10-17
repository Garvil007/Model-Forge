# Decisions

Architecture and design decisions, recorded as they're made. One entry per decision: what, why, alternatives considered, trade-offs.

## Day 7: Single-table DynamoDB schema

**What**: one table (`modelforge`, on-demand billing) holds User, Model, Dataset, Job, JobEvent
and monthly Usage counter items, plus one GSI (`GSI1`). Every item's base-table partition key
(`PK`) starts with `USER#<userId>` (or, for job events, `USER#<userId>#JOB#<jobId>`) — ownership is
structural, not a filter applied after the fact. A read or write with the wrong `userId` simply
misses: there is no query shape that can return another user's item.

### Access patterns → key design

| # | Access pattern | Table | Key condition |
|---|---|---|---|
| 1 | Get user profile by id | base | `PK=USER#{userId}, SK=PROFILE` |
| 2 | Find user by email (signup dedupe, login) | GSI1 | `GSI1PK=EMAIL#{email}` |
| 3 | Get one model by id | base | `PK=USER#{userId}, SK=MODEL#{modelId}` |
| 4 | List a user's models, newest first | GSI1 | `GSI1PK=USER#{userId}, GSI1SK begins_with "MODEL#"`, `ScanIndexForward=False` |
| 5 | Get one dataset by id | base | `PK=USER#{userId}, SK=DATASET#{datasetId}` |
| 6 | List a user's datasets, newest first | GSI1 | `GSI1PK=USER#{userId}, GSI1SK begins_with "DATASET#"`, descending |
| 7 | Get one job by id | base | `PK=USER#{userId}, SK=JOB#{jobId}` |
| 8 | List a user's jobs, newest first (dashboard/history) | GSI1 | `GSI1PK=USER#{userId}, GSI1SK begins_with "JOB#"`, descending |
| 9 | Update job status/progress/result | base | `UpdateItem` on `PK=USER#{userId}, SK=JOB#{jobId}` |
| 10 | Append a job progress event | base | `PutItem PK=USER#{userId}#JOB#{jobId}, SK=EVENT#{tsMillis}#{seq}` |
| 11 | List a job's events in order | base | `Query PK=USER#{userId}#JOB#{jobId}, SK begins_with "EVENT#"`, ascending |
| 12 | Get/increment this month's usage counter | base | `UpdateItem PK=USER#{userId}, SK=USAGE#{yyyymm}` (atomic `ADD`) |

GSI1 is overloaded across three entity types by giving Model/Dataset/Job the same
`GSI1PK=USER#{userId}` and prefixing `GSI1SK` with the entity tag — one index covers three
"list this user's X, newest first" patterns plus the email lookup (`GSI1PK=EMAIL#{email}`), so no
second GSI is needed. JobEvent and the Usage counter never need a GSI entry: their only access
pattern is "all children of a known parent", which the base table's `PK`/`SK` already satisfies.

### Why `PK` embeds the user id directly, not a post-hoc filter

Considered: key models by their own id (`PK=MODEL#{modelId}`) and check an `ownerId` attribute
after `GetItem`. Rejected — a bug that forgets the check is a cross-tenant data leak, and the
leak is only caught by a test someone remembered to write. Keying every item's partition by the
owning user makes the authorization check unconditional: `GetItem(PK=USER#{wrongUser}, ...)` on
another user's model id returns nothing, by construction, before any application code runs. The
isolation test (`packages/db/tests/test_isolation.py`) proves this directly rather than trusting
a convention.

### TTL

Every Model, Job and JobEvent item carries a `ttl` attribute (epoch seconds); DynamoDB's native
TTL sweep deletes expired items so storage cost doesn't grow unbounded with idle usage — no cron,
no scan-and-delete job. Retention, set in `packages/db/src/modelforge_db/ttl.py`:
JobEvents 14 days (they're a progress stream, not a record), Jobs 90 days, Models 365 days.
User profiles and Usage counters never expire (deleting a signed-in user's account is an explicit
action, not a timeout).

### Secrets: Hugging Face token

The user's optional Hugging Face token is envelope-encrypted with KMS
(`packages/db/src/modelforge_db/encryption.py`) before it's written to the User item — the
plaintext token never touches a DynamoDB item or a log line. `UserRepository` exposes
`set_hf_token`/`get_hf_token`; nothing else in the repository layer can read `hfTokenCiphertext`
directly.

## Day 10: Job message schema, stage reconstruction, and the local Batch stand-in

**What**: the real job-execution path (`POST /api/jobs` → SQS → dispatcher → AWS Batch → worker)
needed several small schema and abstraction decisions that didn't exist yet.

### A separate message schema, with no params embedded

`packages/catalog/src/modelforge_catalog/job_messages.py` is its own schema, not an extension of
`system_jobs.py`'s internal `detect_format`/`import_hf` messages. The SQS message carries only
`job_id, user_id, model_id, operation_id, version` — not the job's `params`. The worker re-reads
params from `JobRepository.get(...)` at dispatch time instead. Alternative considered: embed
params in the message to avoid a DB round-trip. Rejected — if a job is ever edited or retried,
the queued message and the DB row could disagree about what to run; re-reading from the one place
`params` is written keeps there from being two sources of truth for the same job.

### One stage-list function, imported by both the API and the worker

`job_stages.py`'s `stages_for_operation(op, params)` (a port of the frontend mock's
`jobStages.ts`) is imported by `apps/api/app/services.py`'s `serialize_job` (to reconstruct
`JobStage[]` for `GET /api/jobs/{id}` from the raw `JobEvent` rows) and by the worker (to know
which stage labels to emit as it runs). Per CLAUDE.md's "every operation declared once" rule,
this is the one place that list exists in the backend. The frontend's `jobStages.ts` stays a
separate, hand-mirrored copy rather than shared code — it drives the *mock* server's
time-based stage simulation, a different problem (no real events to walk) with no clean way to
unify across the Python/TypeScript boundary without adding a build-time codegen step for what's
a handful of per-technique label lists.

### Cancel needs no new field — `JobRecord.status` is the flag

A `running` job's cancel sets `status="canceled"` immediately in DynamoDB; the worker's
`JobControl.check()` call between stages re-reads that same status and stops if it's no longer
`running`. No separate `cancelRequested` field was needed — the status the API already serializes
to the frontend doubles as the signal the worker polls, so there's exactly one place that can
disagree with itself.

### Two additive fields were the only schema change `JobRecord` needed

`batch_job_id` (so cancel can call `BatchJobClient.terminate_job` on a job already submitted to
Batch) and `retry_count` (so a Spot interruption requeues exactly once before failing). Both
default so existing items deserialize unchanged — no migration needed.

### Local AWS Batch stand-in: in-process, not `docker run`

LocalStack Community has no Batch emulation. `infra/lambda/dispatcher/batch_client.py` defines a
`BatchJobClient` protocol with `RealBatchJobClient` (boto3, prod) and `LocalBatchJobClient`
(dev/test — calls the worker's `handle_job_message` in-process) behind it, selected by
`MF_BATCH_CLIENT`. Considered running the worker via `docker run` against the real built image
instead, which would prove the actual deployable container works, not just the Python code
inside it. Chose in-process for now — faster, no image-build step needed in CI, and it exercises
100% of the real worker logic (S3 I/O, the quantization call, event writes, cleanup) except the
containerization layer itself. A `docker run`-based variant is a documented follow-up for anyone
who wants that stronger guarantee before a real deploy.

### Cancel and Spot interruption share one mechanism, with different triggers

Both are "stop between stages if a flag is set" — a single `JobControl.check()` call the op makes
between each stage, raising `JobCanceledError`/`JobTimeoutError`/`SpotInterruptedError`. What sets
the flag differs: DB status for cancel, a `SIGTERM` handler in prod (Batch sends it ~2 minutes
before a Spot reclaim), and an `MF_SIMULATE_SPOT_INTERRUPTION` env var for local/CI testing since
there's no EC2 metadata endpoint to catch a real interruption outside actual Batch-on-Spot.
Unifying them avoids three separate "check something between stages" code paths inside every
operation that gets written from Day 11 onward — an op author only has to call `control.check()`.
