# fixlog Phase 1 Todo

## Approved Spec Amendments
- [x] Add a `QuestionEntryLink` association table instead of an implicit or JSON-only `linked_entries` field.
  - Fields: `question_id`, `entry_id`, `linked_at`, `linked_by_account_id`.
  - Constraints: primary key or unique constraint on `(question_id, entry_id)`.
  - Purpose: makes `/questions/{id}/link_entry`, question detail linked entries, and referential integrity real.
- [x] Fix persona-name uniqueness expectation.
  - Keep exactly 32 adjectives and 32 animals.
  - Since that produces only 1024 possible display names, do not assert `>900` distinct names across 1000 random ids.
  - Test determinism plus reasonable distribution, and show persona id anywhere ambiguity matters.
- [x] Define `ErrorSignature.embedding` as a nullable sqlite-vec-compatible blob column for Phase 1.
  - No embedding generation.
  - No vector search.
  - Load sqlite-vec on SQLite connections where available.
  - Add code comments that vec virtual tables and fuzzy search are Phase 2.
- [x] Replace `Entry.also_matches` JSON UUID array with an `EntryAlsoMatch` association table.
  - Fields: `entry_id`, `error_signature_id`.
  - Constraints: primary key or unique constraint on `(entry_id, error_signature_id)`.
  - Purpose: keeps exact search simple and preserves foreign key integrity for additional matched signatures.
- [x] Add `SessionEvent` table for forward compatibility only.
  - Fields: `id`, `session_id`, `ts`, `kind`, `payload`.
  - Indexes: `session_id`, plus composite `(session_id, ts)`.
  - Phase 1 migration creates it, but no API endpoint, schema, helper, dev seed, or test inserts rows into it.

## Next Required Step
- [x] Propose the four implementation artifacts and stop for approval:
  - `fixlog/db/models.py`
  - every file in `fixlog/schemas/`
  - route handler signatures
  - identity wordlists and persona naming signature/docstring
- [x] Implement SQLAlchemy models and Alembic initial migration.
- [x] Implement Pydantic schemas.
- [x] Implement database session management and config.
- [x] Implement account seeding, auth dependencies, identity helpers, core APIs, and web views.
- [x] Implement dev seed, docs, and tests.

## Review Notes
- Phase 1 remains scoped to schema, REST API, identity, read-only HTMX/Jinja UI, tests, dev seed, docs.
- Still out of scope: normalization, vector generation/search, sandbox runner, MCP server, CLI, reputation, write UI, background workers.
- Also out of scope: any Phase 1 code path writing to `SessionEvent`.
- Verification completed:
  - `.venv/bin/alembic upgrade head` against `/tmp/fixlog-alembic-test.sqlite3`.
  - `.venv/bin/pytest -q` with 28 passing tests.
  - `scripts/dev_seed.py` run twice against `/tmp/fixlog-seed-test.sqlite3`; counts stayed idempotent and `session_events` stayed at 0.
  - In-app browser smoke on seeded web UI at `http://127.0.0.1:8010`; feed rendered entries and questions with no console errors.

# fixlog Phase 2 Todo

## Approved Spec Amendments
- [x] Dispatch strong pytest output before traceback output, because pytest failures can contain tracebacks but still need `error_kind="pytest"`.
- [x] Add explicit canonical-string input handling so `normalize_python_error(signature.canonical_string)` is idempotent.
- [x] Define synthetic non-traceback exception types:
  - `pip.VersionNotFound`
  - `pip.DependencyConflict`
  - `pip.InstallError`
  - `GenericError`
- [x] Keep traceback frame paths as module basenames, and reduce paths inside exception messages to basenames only. Add fixture coverage for this over-merge risk.
- [x] Add direct unit tests for every `common.py` helper plus a large-log regex performance smoke test.

## Required Pre-Implementation Review
- [x] Propose `PythonErrorSignature` model.
- [x] Propose fixture list plus one sample raw fixture and expected JSON.
- [x] Propose main/parser function signatures and docstrings.
- [x] Propose `common.py` normalization helper function list.
- [ ] Wait for explicit approval before writing implementation code.

## Implementation Sequence After Approval
- [x] Models.
- [x] Common normalization helpers and unit tests.
- [x] Traceback parser and traceback fixture tests.
- [x] Pytest parser and pytest fixture tests.
- [x] Pip parser and pip fixture tests.
- [x] Generic parser and generic fixture tests.
- [x] Main dispatcher and corpus tests.
- [x] Determinism tests.
- [x] Idempotency tests.
- [x] Final full test run and review summary.

## Phase 2 Review Notes
- Implemented standalone normalizer package only; no API, database, or UI wiring.
- Dispatch order is canonical input, strong pytest markers, traceback, pip, generic.
- Fixture corpus covers 20 raw examples and expected signatures:
  - 10 traceback fixtures
  - 4 pytest fixtures
  - 2 pip fixtures
  - 4 generic fixtures
- Additional test coverage:
  - 21 direct common-helper unit tests
  - pytest-vs-traceback dispatch test
  - 5 determinism fixture groups with 5 variations each
  - idempotency over every fixture
  - large generic log regex performance smoke test
- Verification completed:
  - `.venv/bin/pytest tests/normalizer -q` with 70 passing tests.
  - `.venv/bin/pytest -q` with 98 passing tests.

# fixlog Phase 2.5 Todo

## Approved Spec Amendments
- [x] Replace canonical string field separator with ASCII Unit Separator `\x1f`.
- [x] Strip `\x1f` defensively from canonical fields before joining.
- [x] Verify idempotency with a script and captured manual spot-check docs.
- [x] Wire the Python normalizer into POST `/entries`, POST `/questions`, and GET `/search`.
- [x] Store structured normalizer output on `ErrorSignature`.

## Implementation Sequence
- [x] Separator fix in normalizer.
- [x] Regenerate all expected JSON fixtures.
- [x] Add separator collision tests.
- [x] Run full normalizer test suite.
- [x] Add `scripts/verify_idempotency.py`.
- [x] Run idempotency script on all fixtures and capture output.
- [x] Manual three-fixture spot check and write `docs/idempotency_verification.md`.
- [x] Add Alembic migration and model fields for structured normalizer output.
- [x] Update request schemas for POST `/entries` and POST `/questions`.
- [x] Wire server-side normalization into handlers.
- [x] Update search endpoint to normalize query input.
- [x] Update affected tests.
- [x] Update `scripts/dev_seed.py`.
- [x] Run full pytest suite.
- [x] Add trivial entry detail metadata block if clean.

## Phase 2.5 Review Notes
- Canonical strings now use ASCII Unit Separator `\x1f`; literal pipes remain message content.
- Expected normalizer JSON now includes hashes and was regenerated from the normalizer.
- Idempotency verifier passed over 20 fixtures; 16 round-trips changed `error_kind` to `generic`, which is acceptable because canonical strings are their own input shape.
- Server-side POST `/entries`, POST `/questions`, and GET `/search` now normalize raw Python error text.
- Verification completed:
  - `.venv/bin/pytest tests/normalizer -q` with 73 passing tests.
  - `.venv/bin/python scripts/verify_idempotency.py` passed over 20 fixtures.
  - `.venv/bin/alembic upgrade head` applied `0001` and `0002` against `/tmp/fixlog-phase25-alembic.sqlite3`.
  - `.venv/bin/pytest -q` with 106 passing tests.
  - `scripts/dev_seed.py` ran twice against `/tmp/fixlog-phase25-seed.sqlite3`; counts stayed idempotent and `session_events` stayed at 0.

# fixlog Phase 3 Todo

## Eng Review Decisions
- [x] Reuse the existing `SessionEvent` table instead of creating a parallel event store.
- [x] Add `source_tool` and `source_tool_session_id` to `Session` so Claude Code native sessions map cleanly to fixlog sessions.
- [x] Keep raw session event reads token-gated; only the aggregate active-sessions web page is read-open.
- [x] Treat `SessionEvent.kind` as a future-extensible string in the ORM, while keeping named constants for known Phase 3 kinds.
- [x] Implement sensitive-file redaction with parser state plus testable redaction helpers because tool results only link to prior tool calls by id.
- [x] Implement the real Claude Code smoke test as `FIXLOG_E2E=1` gated; this environment cannot start a real user Claude Code session deterministically.

## NOT in Scope
- Codex, Cursor, Aider, Continue, or other parser implementations.
- Auto-querying fixlog when stuck, pulling fixes, or applying entries.
- Sandbox auto-verification.
- Multi-language error detection beyond Python traceback/pytest hashing.
- Auto-submitting harvested entries unless `FIXLOG_AUTO_SUBMIT_HARVESTS=true`.

## Implementation Sequence
- [x] Harness models.
- [x] Secret redaction helpers and tests.
- [x] Parser ABC.
- [x] Claude Code parser fixtures and tests.
- [x] Stuck detector and tests.
- [x] Harvester with mocked LLM tests.
- [x] Prompt modules.
- [x] Watcher/replay pipeline.
- [x] CLI commands.
- [x] Server SessionEvent API additions.
- [x] Active sessions web page.
- [x] End-to-end replay integration test.
- [x] Gated real Claude Code smoke test.
- [x] Full pytest verification.

## Phase 3 Review Notes
- The live Claude Code smoke test is implemented as a gated test because it needs a real local Claude Code session log path.
- Raw event payload reads are token-gated even though existing entries/questions remain read-open.
- `watchdog` and `anthropic` are pinned dependencies, but imports are lazy where possible so unit tests stay local and deterministic.
- Real replay smoke completed against `/Users/maanavagrawal/.claude/projects/-Users-maanavagrawal-dev-memoir/1f083691-dae9-4876-9c2e-605a43285d3f.jsonl`.
  - The log had 65 JSONL lines, 15 tool calls, 15 tool results, and one non-Python command error.
  - Replay captured 46 SessionEvents and `/sessions/active` showed `claude_code` project `memoir`.
  - All 15 tool results paired with a matching tool call id.
  - Source timestamps, cwd, git branch, git commit, and project slug were preserved.
  - No real redactions were needed after fixing a false-positive path redaction bug.
  - No pending harvest was written because the session had no current `git diff`.
  - Watch mode booted after installing the pinned dependencies, then was stopped after startup verification.
- Verification completed:
  - `.venv/bin/pytest -q` with 135 passed and 1 gated live smoke skipped.
  - `.venv/bin/alembic upgrade head` against `/tmp/fixlog-phase3-alembic.sqlite3`.
  - `.venv/bin/python -m compileall fixlog fixlog_harness scripts tests`.
  - `scripts/dev_seed.py` ran twice against `/tmp/fixlog-phase3-seed.sqlite3`.

# fixlog Phase 5 Todo

## Approved Spec Amendments
- [x] Keep the existing `Entry` schema unchanged and encode Phase 5 pilot sandbox files in `Entry.sandbox_spec` JSON.
- [x] Defer full repo workspace tarball persistence until a later phase because no current API or model field can carry it.
- [x] Use FastAPI lifespan wiring for the verifier worker instead of legacy startup/shutdown decorators.
- [x] Keep the harness auto-submit flag defaulted to false; Phase 5 verifies server-side but does not change rollout posture.

## Implementation Sequence
- [x] Sandbox spec/result/config models and unit tests.
- [x] Docker sandbox runner with security flags and Docker-gated tests.
- [x] Verifier worker with mock-runner tests.
- [x] FastAPI lifespan wiring, POST `/entries` enqueue, and `/sandbox/status`.
- [x] Entry detail pending/failed verification UI.
- [x] Auto-verification integration test.
- [x] Harness auto-submit validation with flag enabled once, then default false.
- [x] Manual Docker checks: passing entry, failing entry, OOM, timeout, network blocked, image whitelist, read-only rootfs, writable workspace.
  - Docker Desktop is reachable through the user's shell; `python:3.11-slim` is pre-pulled.
  - Server startup confirmed the verifier worker starts with the configured image whitelist.
  - Manual results:
    - Good entry verified as `pass`.
    - Bad fix verified as `fail`.
    - Memory bomb verified as `partial`.
    - Timeout verified as `partial`.
    - Network probe failed with `OSError: [Errno 101] Network is unreachable`.
    - `ubuntu:22.04` was rejected with `image not in whitelist: ubuntu:22.04`.
    - `/etc` write failed with `Read-only file system`.
    - `/workspace` write passed and verify stdout included `can-write`.
- [x] Browser session-events route fix after verification-log smoke.
  - Added HTML rendering for `/sessions/{id}/events` while preserving JSON API auth semantics.
- [x] Fixed auto-sandbox verify ordering bug found by the manual happy-path check.
  - Root cause: fixed files were written before `reproduction_setup`, so setup commands that create baseline files could overwrite the fix before `reproduction_verify`.
  - Fix: keep baseline files for setup, then overlay only changed/deleted fix files after setup and before verify.

## Review Notes
- The complete Phase 5 flow is intentionally in-process for the two-user pilot; Redis/Celery and distributed workers remain out of scope.
- Dockerfile support, arbitrary images, scheduled re-verification, and persisted full workspaces are out of scope.
- Focused verification for the browser route: `.venv/bin/pytest tests/test_web_views.py tests/test_session_events_api.py -q` passed with 16 tests.
- Regression verification for the setup/fix ordering bug:
  - `.venv/bin/pytest tests/test_verifier_worker.py -q` passed with 7 tests.
  - `zsh -lic '.venv/bin/pytest tests/test_auto_verification_e2e.py -q'` passed with 2 real-Docker tests.
  - `zsh -lic '.venv/bin/pytest -q'` passed with 170 tests and 1 skipped.

# Railway Pilot Productionization Todo

## Scope
- [x] Make the FastAPI app deploy cleanly on Railway with a Dockerfile/start command that binds to Railway's `PORT`.
- [x] Add a health endpoint suitable for Railway healthchecks.
- [x] Keep SQLite viable for the two-person pilot by documenting a Railway volume mounted at `/data` and `DATABASE_URL=sqlite:////data/fixlog.sqlite3`.
- [x] Add shared browser dashboard auth so either configured account token can log in and view the dashboard without manually setting API headers.
- [x] Keep local watcher/agent ingestion token-based, so each developer points their laptop harness at the hosted `FIXLOG_BASE_URL` with their own `FIXLOG_API_TOKEN`.
- [x] Disable the Docker verifier by default in Railway instructions unless a separate Docker-capable worker is deployed.
- [x] Update docs and example environment variables for the exact Railway/cofounder setup.
- [x] Add regression tests for web login, dashboard protection, healthcheck behavior, and authenticated session-event viewing.
- [x] Run focused tests, then full pytest before calling this ready.

## Review Notes
- Railway docs currently require services to listen on `0.0.0.0:$PORT`, and healthchecks expect a `200` path during deploy.
- Railway volumes persist data only when mounted into the running service; for SQLite the safest pilot path is an attached volume at `/data` and an absolute SQLite URL.
- Browser auth is for human dashboard visibility. Agent writes still use `Authorization: Bearer <token>` and session ownership checks.
- Auto-sandbox verification remains appropriate for a local/Docker-capable worker, but the Railway web service should not assume a Docker daemon exists.
- Verification completed:
  - `.venv/bin/pytest tests/test_production_auth.py tests/test_web_views.py tests/harness/test_cli.py -q` passed with 22 tests.
  - `.venv/bin/pytest -q` passed with 183 tests and 12 skipped.
  - `.venv/bin/python -m compileall fixlog fixlog_harness tests` completed successfully.
  - `docker build -t fixlog-railway-smoke .` completed successfully.
  - `docker run --rm fixlog-railway-smoke python -c "import fixlog.main; print(\"import-ok\")"` completed successfully.

# Device Token Collector Onboarding Todo

## Architecture Decisions
- [x] Separate human/dashboard account tokens from collector/device tokens.
- [x] Device tokens are scoped to session ingestion first: start session, heartbeat, post session events, and collector status.
- [x] Device tokens do not grant dashboard/admin/API read access.
- [x] Local collector config lives at `~/.fixlog/config.toml`, with env vars still taking precedence for local debugging.
- [x] Repo privacy boundary is local allowlist filtering: if `allowed_projects` is set, events without a cwd under an allowed project are dropped before network forwarding.
- [x] Install script and polished dashboard device page are deferred to Batch 2 after the token/config foundation is tested.

## Batch Plan
- [x] Batch 1: server device-token model/API, collector auth dependencies, `fixlog connect`, local config loading, project allowlist filtering, and tests.
- [x] Batch 2: dashboard device/connect page and one-copy repo connect command.
- [ ] Batch 3: hosted install script that installs/runs the lightweight collector without cloning the full repo manually.
- [ ] Batch 4: optional background service install via LaunchAgent on macOS.
- [ ] Batch 5: MCP surface for active fixlog search/query flows, after passive collection is easy and trustworthy.

## Batch 1 Test Plan
- [x] Account token can create/list/revoke device tokens.
- [x] Device token can start sessions and post events.
- [x] Revoked device token is rejected.
- [x] Device token cannot access general account/dashboard API endpoints.
- [x] `fixlog connect` writes config and `get_harness_settings()` loads it.
- [x] Env vars override local config.
- [x] Watcher allowlist forwards in-project events and drops out-of-project events.

## Batch 1 Review Notes
- Added `device_tokens` with hashed `flxdt_...` tokens and one-time token return on creation.
- Added collector-scoped auth for `/collector/status`, `/sessions/start`, `/sessions/{id}/heartbeat`, and `/sessions/{id}/events`; general account APIs still require account tokens.
- Added `fixlog connect --url ... --token ... [--project ...]`, storing `~/.fixlog/config.toml` and an allowlisted git root.
- Watcher now drops events whose `cwd` is outside configured `allowed_projects`.
- Verification completed:
  - `.venv/bin/pytest tests/test_device_tokens.py tests/test_production_auth.py tests/harness/test_local_config.py tests/harness/test_cli.py tests/harness/test_watcher_pipeline.py -q` passed with 27 tests.
  - `.venv/bin/pytest -q` passed with 193 tests and 12 skipped.
  - `DATABASE_URL=sqlite:////tmp/fixlog-device-token-alembic.sqlite3 .venv/bin/alembic upgrade head` applied through `0004_device_tokens`.
  - `.venv/bin/python -m compileall fixlog fixlog_harness tests` completed successfully.

## Batch 2 Review Notes
- Added `/settings/devices` as the browser flow for creating and revoking collector device tokens.
- The dashboard now has a Settings tab with a one-time `fixlog connect --url ... --token flxdt_...` command after token creation.
- Raw device tokens are shown only in the creation response; later page loads show device metadata, active/revoked state, and last-used time only.
- Device revocation is scoped to the logged-in/account-token owner.
- Railway setup docs now direct pilot users to the Settings page before falling back to the API.
- Verification completed:
  - `.venv/bin/pytest tests/test_web_views.py -q` passed with 16 tests.
  - `.venv/bin/pytest tests/test_web_views.py tests/test_production_auth.py tests/test_device_tokens.py -q` passed with 30 tests.
  - `.venv/bin/pytest -q` passed with 198 tests and 12 skipped.
  - `.venv/bin/python -m compileall fixlog fixlog_harness tests` completed successfully.
  - Local HTTP smoke against `http://127.0.0.1:8097/settings/devices` confirmed login, page render, and token creation command output.
