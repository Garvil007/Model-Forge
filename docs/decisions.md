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
