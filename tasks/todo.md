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
- [x] Batch 3: hosted install script that installs/runs the lightweight collector without cloning the full repo manually.
- [x] Batch 4: optional background service install via LaunchAgent on macOS.
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

## Batch 3 Review Notes
- Added public `/install.sh`, gated out of dashboard auth so a fresh laptop can fetch the installer before it has any fixlog credentials configured.
- The installer creates `~/.fixlog/collector/.venv`, installs the collector package from `FIXLOG_COLLECTOR_PACKAGE_URL`, symlinks `~/.fixlog/bin/fixlog`, runs `fixlog connect` against the repo where the script was invoked, and runs `fixlog doctor`.
- The dashboard's one-time token command now uses the installer: `curl -fsSL .../install.sh | bash -s -- --token flxdt_...`.
- Added `FIXLOG_COLLECTOR_PACKAGE_URL` to config and docs; default points at the GitHub `main` branch for the pilot.
- Verification completed:
  - `.venv/bin/pytest tests/test_install_script.py tests/test_web_views.py tests/test_production_auth.py tests/test_device_tokens.py tests/harness/test_cli.py -q` passed with 36 tests.
  - `.venv/bin/python -m compileall fixlog fixlog_harness tests` completed successfully.
  - `.venv/bin/pytest -q` passed with 201 tests and 12 skipped.

## Batch 4 Review Notes
- Added `fixlog service install --start`, `fixlog service status`, and `fixlog service uninstall` for macOS LaunchAgent management.
- The LaunchAgent runs the installed `fixlog watch` binary, starts at login/load, keeps the watcher alive, and writes logs to `~/.fixlog/logs/collector.out.log` and `collector.err.log`.
- Added `fixlog service install --dry-run` for inspectable plist output and tests.
- The hosted installer supports `--background`, which installs and starts the LaunchAgent after `fixlog connect` and `fixlog doctor`.
- Verification completed:
  - `.venv/bin/pytest tests/harness/test_service.py tests/test_install_script.py tests/harness/test_cli.py -q` passed with 7 tests.
  - `.venv/bin/python -m compileall fixlog fixlog_harness tests` completed successfully.
  - `.venv/bin/pytest -q` passed with 203 tests and 12 skipped.

## Onboarding Clarity Polish
- [x] Make `/settings/devices` explain the first-time setup without assuming the user already knows the collector architecture.
- [x] Put the setup flow before token creation: create token, run install command inside repo, start capture, use Claude Code.
- [x] Explain the privacy boundary: device tokens can only submit collector events and can be revoked.
- [x] Keep the one-time command visible after token creation, with an explicit `--background` hint.
- [x] Fold token creation and the generated install command into the onboarding steps themselves, Moltbook-style, instead of showing onboarding copy separately from setup action.
- [x] Add unauthenticated login-page onboarding so first-time users see the local install flow before signing in.
- [x] Make direct login default to `/settings/devices`, keeping setup as the first authenticated screen.
- [x] Add public `/agent` view that mirrors the Moltbook pattern: “give your AI this instruction,” pointing at a scrapeable `/skill.md`.
- [x] Add public `/skill.md` with agent-specific setup instructions, install commands, safety boundaries, and success criteria.
- Verification completed:
  - `.venv/bin/pytest tests/test_web_views.py tests/test_production_auth.py tests/test_install_script.py -q` passed with 35 tests.
  - `.venv/bin/python -m compileall fixlog fixlog_harness tests` completed successfully.
  - `.venv/bin/pytest -q` passed with 209 tests and 12 skipped after the public agent setup update.

# Frontend Visual Polish Todo

## Scope
- [x] Use the frontend-app-builder workflow to create a concrete visual direction before coding.
- [x] Keep the current Human, Agent, Settings, login, and detail-page routes truthful to backend-backed data.
- [x] Preserve existing tested copy and onboarding semantics while improving hierarchy, rhythm, and polish.
- [x] Prefer a notebook/discourse product feel over a dense dashboard or marketing landing page.
- [ ] Before any next redesign implementation, audit every visible affordance against existing backend route/data/action support and remove or defer anything unsupported.

## Backend-Truth Gate for Next Pass
- [ ] No feed filter or sort controls unless backed by a real route/query parameter and tests.
- [ ] No recent-items, persona directory, inbox, activity graph, command palette, keyboard shortcut, or session-control UI unless backend data/actions already exist.
- [ ] No fake status counts or workflow claims; counts must come from current route context.
- [ ] Styling-only icons are allowed, but icon buttons or controls must perform an existing action.
- [ ] Any concept-only element must be either omitted from implementation or explicitly labeled as a future design note outside the shipped UI.

## Implementation Sequence
- [x] Extract design tokens for color, typography, spacing, borders, code surfaces, pills, and panels.
- [x] Update the shared shell/header/navigation/search/footer styling.
- [x] Polish feed/session cards, side rails, empty states, detail pages, setup steps, and forms.
- [x] Tighten responsive behavior for tablet and mobile viewports.
- [x] Run focused web-view/auth/install tests, then visual browser verification.

## Review Notes
- Concept reference: `/Users/maanavagrawal/.codex/generated_images/019e524a-9746-77e2-b706-974cb8359207/ig_00d1837d2f37ccbe016a10f8e0416c8196b1ead84c526df846.png`.
- Implemented a paper/notebook visual system: compact icon nav, serif wordmark, subtle ruled background, status rails, sharper code surfaces, stronger pills/persona chips, and setup-step timeline styling.
- Edited only the frontend styling plus a semantic feed-card class hook: `fixlog/web/static/styles.css` and `fixlog/web/templates/partials/feed_list.html`.
- Browser verification used gstack `/browse` against a seeded `/tmp/fixlog-frontend-visual.sqlite3` app on `http://127.0.0.1:8123`.
- Screenshots inspected with `view_image`:
  - `/tmp/fixlog-human-desktop-v2.png`
  - `/tmp/fixlog-settings-desktop-v2.png`
  - `/tmp/fixlog-agent-desktop-v2.png`
  - `/tmp/fixlog-human-mobile-v2.png`
- Fidelity checks:
  - Copy/nav preserved: `fixlog`, `Human`, `Agent`, `Settings`, `Exact error search`, `Agent broadcasts and field notes.`, `Field note`, `Open broadcast`, `Notebook`, `No linked fix yet`.
  - Layout matches the concept direction: compact top nav, right-side search, ruled page head, feed-first app surface, and notebook stats rail.
  - Palette matches the concept direction: true light background with ink text, blue broadcast accents, moss field-note accents, amber warning state, and no purple/dark-dashboard treatment.
  - Component model improved without backend drift: feed cards use rails instead of generic heavy cards; panels remain truthful to current data.
  - Responsive check at 390x844 showed no horizontal overflow or overlapping UI; the side rail stacks below the feed.
- Material mismatches fixed during QA: device setup button no longer stretches across the full panel, and agent instruction/setup commands wrap instead of clipping.
- Verification completed:
  - `.venv/bin/pytest tests/test_web_views.py tests/test_production_auth.py tests/test_install_script.py -q` passed with 35 tests.
  - `.venv/bin/pytest -q` passed with 209 tests and 12 skipped.

# Backend-Truth Frontend Redesign Plan

## Goal
- [ ] Redesign the frontend into a polished, coherent Fixlog product UI without implying backend functionality that does not exist.
- [ ] Keep the product feeling like a local agent notebook/discourse surface, not a dense dashboard, marketing page, or fake command center.
- [ ] Preserve the current route map, tested copy, auth boundaries, and data contracts unless a backend change is explicitly approved first.

## Backend-Backed Surface Inventory
- [ ] Global shell: brand link to `/`, Human tab `/`, Agent setup tab `/agent`, Settings tab `/settings/devices`, exact error search form to `/search/errors`, and logout POST `/logout`.
- [ ] Human feed `/`: read-only combined feed from `build_feed(db, limit=50, offset=0)`, notebook counts for total entries and open questions, HTMX refresh via `/partials/feed-list`.
- [ ] Feed cards: link to existing entry/question detail pages, show kind, status/verification count, relative time, persona/account metadata, and normalized error preview.
- [ ] Agent setup `/agent`: public instruction page linking to `/skill.md`, `/login?next=/settings/devices`, and manual installer command shape.
- [ ] Active sessions `/sessions/active`: read-only aggregate session rows from `build_active_sessions`, with inspect link to `/sessions/{id}/events/view`.
- [ ] Session events `/sessions/{id}/events/view`: read-only event payload list, with existing `limit`, `offset`, and `kind` query support available only if intentionally exposed.
- [ ] Settings `/settings/devices`: create a device token by POSTing device name, display one-time install command, list owned device tokens, revoke active tokens.
- [ ] Login `/login`: account-token sign-in, local install preview, invalid-token error state.
- [ ] Search `/search/errors`: exact normalized-error search with result/empty states; no fuzzy/vector search claims.
- [ ] Entry detail `/entries/{id}`: read-only field note details, reproduction blocks, sandbox spec/result, verification log, edit history, related also-matches/tags where already rendered.
- [ ] Question detail `/questions/{id}`: read-only broadcast details, attempts made, linked entries, duplicate metadata, environment/agent metadata.

## Explicitly Prohibited Unless Backend Is Added First
- [ ] No feed filter, sort dropdown, or saved view UI; feed currently has fixed `limit=50, offset=0` and no feed query params.
- [ ] No fake recent-items sidebar, activity graph, command palette, keyboard shortcut hints, notification badge, inbox, persona directory, assignment, ownership, comments, reactions, or create-entry/question workflow.
- [ ] No session controls such as pause, stop, retry, replay, connect, or live-tail toggles beyond existing navigation/inspection.
- [ ] No search claims beyond exact normalized-error search; do not imply fuzzy, semantic, vector, or cross-language search in visible UI.
- [ ] No fake metrics; counts must come from current route context or existing response fields.
- [ ] No button-like element unless it submits an existing form, follows an existing link, or performs an implemented client-side behavior we explicitly test.

## Approved Visual Redesign Direction
- [ ] Use a quieter product-app composition with clear primary work surfaces: feed, setup flow, session list, detail page, search results.
- [ ] Use visual hierarchy, spacing, typography, borders, state color, icons, and code-surface treatment to add polish without adding product claims.
- [ ] Keep cards/panels at 8px radius or less and avoid nested cards.
- [ ] Replace purely decorative feature-like UI with non-interactive visual structure: section rules, status rails, labels, metadata rows, and code preview framing.
- [ ] Keep the Human and Agent distinction simple: Human is feed/notebook, Agent is setup plus active session navigation.

## Proposed Implementation Slices After Approval
- [ ] Slice 1: Global shell and responsive nav cleanup, including brand, tabs, search, logout, and footer.
- [ ] Slice 2: Human feed and partial feed list, preserving only backend-backed card fields and links.
- [ ] Slice 3: Settings/login/agent setup flows, preserving token privacy and one-time command behavior.
- [ ] Slice 4: Active sessions and session-events pages, keeping them read-only and inspection-focused.
- [ ] Slice 5: Entry/question/search detail surfaces, aligning typography/code/detail-list treatment with the new system.
- [ ] Slice 6: Responsive polish for 390px mobile, tablet, and 1440px desktop.

## Verification Plan
- [ ] Add or update tests only for real route/data/action behavior, not decorative styling.
- [ ] Run `.venv/bin/pytest tests/test_web_views.py tests/test_production_auth.py tests/test_install_script.py -q`.
- [ ] Run full `.venv/bin/pytest -q`.
- [ ] Use gstack `/browse` with seeded data to inspect `/`, `/agent`, `/sessions/active`, `/settings/devices`, `/search/errors`, one entry detail, one question detail, and mobile `/`.
- [ ] Before final, write a backend-truth audit in this section: every visible control maps to an existing route/action, and every visible metric maps to existing data.

## Approval Checkpoint
- [ ] Stop here until the plan is approved.
- [ ] After approval, implement the frontend redesign in the slices above without adding backend functionality or unbacked UI affordances.

# Name-Based Viewer Login Polish

## User Corrections
- [x] Remove the Human-mode CTA from the Agent setup page so `/agent` stays agent-only.
- [x] Make Settings behave predictably for a not-yet-signed-in human viewer.
- [x] Replace the browser-facing API-token login with a human-name sign-in for viewing dashboard information.
- [x] Preserve token-based collector/device auth for agents and write APIs.

## Implementation Plan
- [x] Inspect current web auth, seeded account lookup, login route, middleware, and onboarding templates.
- [x] Add a browser login path that resolves an existing account by `human_name` and creates the same signed web session cookie.
- [x] Update login copy/form to ask for a name, while keeping API bearer tokens for collector/API routes.
- [x] Remove cross-mode Human CTA from `/agent`; keep only agent setup and real active-session navigation.
- [x] Update tests for login-by-name, invalid-name error, settings redirect, and agent page copy.
- [x] Verify with focused tests, full tests, and gstack `/browse` on login, agent, settings, and feed.

## Review Notes
- Root cause: the public Agent page reused human/agent mode-switch language, while the dashboard login route was still browser-facing the account API token field. Settings was protected correctly, but the redirect landed on that token-first form.
- Browser viewer login now resolves one active `Account.human_name` case-insensitively and mints the existing signed web-session cookie. API bearer auth and scoped device-token collector auth are unchanged.
- `/agent` now shows `Open agent skill` and `View active sessions`; it no longer shows `I'm a Human`, `I'm an Agent`, or unauthenticated `Log out`.
- The login screen now asks for `Your name`; invalid names and API-token strings are rejected as viewer names.
- Verification completed:
  - `.venv/bin/pytest tests/test_web_views.py tests/test_production_auth.py tests/test_install_script.py -q` passed with 38 tests.
  - `.venv/bin/pytest -q` passed with 212 tests and 12 skipped.
  - gstack `/browse` on `http://127.0.0.1:8125`: cleared the web-session cookie, confirmed `/settings/devices` redirects to the name form, signed in as `Ada`, confirmed Settings and Human feed render, and checked console errors on Agent, Settings, and Human feed.
  - Screenshots reviewed: `/tmp/fixlog-agent-name-login.png`, `/tmp/fixlog-settings-name-login.png`, `/tmp/fixlog-human-name-login.png`.

# Multi-User Viewer Auth Polish

## User Corrections
- [x] Hide Settings from public navigation until the browser has a viewer session.
- [x] Do not make name-only login the scalable sign-in model.
- [x] Keep the implementation account-backed and data-driven, not hardcoded to the initial pilot people.
- [x] Preserve collector/API bearer-token auth and scoped device-token behavior.

## Implementation Plan
- [x] Add a viewer login check that uses existing account rows and a unique access code instead of hardcoded names.
- [x] Update the login form copy from `Your name` to a dashboard access code flow.
- [x] Hide Settings/search/logout in public chrome until a web-session cookie is present; keep Agent setup publicly accessible.
- [x] Update regression tests for public nav, login success/failure, and API-token/device-token preservation.
- [x] Verify focused tests, full tests, and gstack `/browse` against public Agent, login, Settings, and signed-in feed.

## Review Notes
- Replaced name-only browser auth with `account_from_viewer_access_code`, which resolves against existing account rows and mints the same signed web-session cookie. The code path is data-driven by `accounts`, not hardcoded to any specific people.
- Public chrome now shows only `Human` and `Agent`; `Settings`, exact search, and `Log out` appear after a viewer session cookie exists.
- The login form now asks for `Dashboard access code` and no longer claims names are sufficient identity. Display names still render as feed/detail metadata only.
- Collector/API bearer auth and scoped `flxdt_...` device-token behavior are unchanged.
- Verification completed:
  - `.venv/bin/pytest tests/test_web_views.py tests/test_production_auth.py tests/test_install_script.py -q` passed with 38 tests.
  - `.venv/bin/pytest -q` passed with 212 tests and 12 skipped.
  - gstack `/browse` cleared the web-session cookie, verified public `/agent` hides Settings/search/logout, verified `/settings/devices` redirects to `/login`, signed in with an account-backed access code, and verified signed-in Settings/feed chrome.
  - Screenshots reviewed: `/tmp/fixlog-public-agent-multiuser.png`, `/tmp/fixlog-signed-settings-multiuser.png`, `/tmp/fixlog-signed-human-multiuser.png`.

# Hosted Collector Base URL Fix

## User-Reported Failure
- [x] Reproduce the live installer bug where `/install.sh` embeds `DEFAULT_FIXLOG_BASE_URL=agent-messaging-production.up.railway.app` without `https://`.
- [x] Prevent the installer from writing malformed host-only URLs to `~/.fixlog/config.toml`.
- [x] Make `fixlog doctor` / `fixlog watch` fail clearly before tailing logs if local config still has a malformed URL.
- [x] Preserve local development installs with explicit `http://localhost...` URLs.

## Implementation Plan
- [x] Normalize hosted public URLs used by `/skill.md` and `/install.sh`.
- [x] Add shell-side URL normalization in the installer for host-only default/override values.
- [x] Add harness config validation for `FIXLOG_BASE_URL` / `base_url` from local config.
- [x] Update CLI/install/local-config regression tests.
- [x] Run focused harness/install tests and full pytest.

## Review Notes
- Root cause: the production app had `FIXLOG_PUBLIC_URL=agent-messaging-production.up.railway.app` without a scheme. `/skill.md` still showed HTTPS through its public URL helper, but `/install.sh` bypassed that helper and embedded a host-only `DEFAULT_FIXLOG_BASE_URL`. The installer wrote that bad value into `~/.fixlog/config.toml`, so `fixlog watch` later passed a scheme-less URL to httpx.
- `/install.sh` now uses the same public URL helper as `/skill.md`, and `build_collector_install_script()` normalizes host-only public URLs to `https://...` while preserving localhost as `http://...`.
- The shell installer also repairs host-only `FIXLOG_BASE_URL` / `--url` values before calling `fixlog connect`, which protects old or manually overridden installs.
- `fixlog connect`, `fixlog doctor`, and `fixlog watch` now validate `FIXLOG_BASE_URL` / local `base_url` before network activity; malformed configs fail with `must start with http:// or https://` instead of tailing Claude logs and retrying httpx failures.
- Verification completed:
  - Live reproduction fetched `https://agent-messaging-production.up.railway.app/install.sh` and confirmed the bad `DEFAULT_FIXLOG_BASE_URL=agent-messaging-production.up.railway.app`.
  - `.venv/bin/pytest tests/test_install_script.py tests/harness/test_local_config.py tests/harness/test_cli.py tests/test_production_auth.py -q` passed with 41 tests.
  - `.venv/bin/pytest -q` passed with 227 tests and 12 skipped.
  - Local review server restarted on `http://127.0.0.1:8125` against `/tmp/fixlog-urlfix-review.sqlite3`; its `/install.sh` now embeds `DEFAULT_FIXLOG_BASE_URL=http://127.0.0.1:8125`.
  - `env FIXLOG_BASE_URL=agent-messaging-production.up.railway.app .venv/bin/fixlog doctor` now exits 2 with a clear `must start with http:// or https://` message before any network calls.

# Public Forum and Agent Setup Review

## Implementation Plan
- [x] Keep the Human forum/feed public so people can scroll through the product without signing in.
- [x] Keep rich entry/question detail pages, raw sessions, settings, and exact search behind dashboard auth.
- [x] Keep `/agent` and `/skill.md` public and scrapeable for coding agents.
- [x] Ensure public setup links use `FIXLOG_PUBLIC_URL` in deployed environments instead of trusting arbitrary Host headers, and normalize scheme-less public hostnames to `https://`.
- [x] Make the agent skill self-contained by telling the agent to export a scoped `FIXLOG_DEVICE_TOKEN` before running the installer.
- [x] Run gstack-style adversarial review, patch findings, and verify focused/full tests plus local preview smoke.

## Review Notes
- Codex adversarial review found three issues and all were fixed before push: Host-header fallback in public setup links, unauthenticated rich detail pages, and missing token-export instruction in `/skill.md`. The public URL helper also normalizes Railway-style scheme-less hostnames to `https://...`.
- Public surface after review: `/`, `/partials/feed-list`, `/agent`, `/skill.md`, `/install.sh`, `/login`, `/healthz`, static assets, and collector write endpoints that validate scoped tokens themselves.
- Auth-gated surface after review: `/entries/{id}`, `/questions/{id}`, `/search/errors`, `/sessions/active`, `/sessions/{id}/events/view`, and `/settings/devices` when `FIXLOG_AUTH_REQUIRED=true`.
- Verification completed:
  - `.venv/bin/pytest tests/test_production_auth.py tests/test_web_views.py tests/test_install_script.py -q` passed with 46 tests.
  - `.venv/bin/pytest -q` passed with 220 tests and 12 skipped.
  - Refreshed local preview on `http://127.0.0.1:8099`; `/` and `/agent` returned 200, `/skill.md` returned 200 with the token export command, `/search/errors` and `/settings/devices` redirected to login, and a forged Host request to `/skill.md` returned the expected `FIXLOG_PUBLIC_URL` configuration error.

# Production Session Start 500

## User-Reported Failure
- [x] Investigate `fixlog watch` receiving `500 Internal Server Error` from hosted `POST /sessions/start`.
- [x] Trace collector session-start payload through auth, API route, schema, and database writes.
- [x] Reproduce the server failure locally with a device token or equivalent auth path.
- [x] Patch the root cause with a regression test.
- [x] Run focused tests and full pytest before shipping.

## Review Notes
- Root cause: concurrent or retried `POST /sessions/start` calls for a fresh account/model/harness persona could both observe no persona row and then race to insert the same `agent_personas` identity. The loser raised a database `UNIQUE constraint failed` error, which surfaced as a 500 to `fixlog watch`.
- The session-start route now creates personas through a savepoint-backed get-or-create helper. If another request wins the insert race, the losing request reloads the persona and continues instead of failing the whole request.
- `/sessions/start` is now idempotent for collector retries that include `source_tool` and `source_tool_session_id`: a retry returns the existing Fixlog session instead of creating duplicate sessions for the same Claude session.
- Verification completed:
  - Reproduced the failure before the fix with a real file-backed SQLite app and concurrent device-token `POST /sessions/start` calls.
  - `.venv/bin/pytest tests/test_device_tokens.py -q` passed with 6 tests.
  - `.venv/bin/pytest tests/test_device_tokens.py tests/test_auth.py tests/test_production_auth.py tests/harness/test_watcher_pipeline.py tests/harness/test_cli.py -q` passed with 49 tests.
  - `.venv/bin/pytest -q` passed with 229 tests and 12 skipped.

# Active Session Dashboard Visibility

## User-Reported Failure
- [x] Investigate why collector writes return `200 OK` but nothing appears in the dashboard.
- [x] Confirm the Human forum only shows harvested entries/questions, while live raw events are shown on `/sessions/active`.
- [x] Make live sessions easier to find from the Agent tab after sign-in.
- [x] Add an auto-refreshing active-session partial so a page opened before capture starts updates without a manual reload.
- [x] Add regression tests for active-session polling, signed-in Agent page visibility, and auth gating.

## Review Notes
- Root cause: ingestion was succeeding, but the dashboard read surface was too static and too hidden. The Human forum auto-refreshes, but live raw session events live on `/sessions/active`, and that page did not poll. The Agent tab also stayed setup-focused after login, so successful collector writes could feel invisible.
- `/sessions/active` now renders through a reusable active-session partial and refreshes it every 5 seconds.
- Signed-in `/agent` now shows a live session dashboard panel inline, while public users get a direct sign-in action for live sessions.
- The active-session query now uses `populate_existing=True` so long-lived sessions do not show stale event relationships.
- Superseded by the issue-only dashboard correction below: the dashboard should refresh issue signals, not normal successful collector activity.
- Verification completed:
  - `.venv/bin/pytest tests/test_web_views.py::test_active_sessions_page_returns_expected_substrings tests/test_web_views.py::test_agent_onboarding_page_returns_scrapeable_instruction tests/test_production_auth.py::test_login_cookie_shows_live_sessions_on_agent_page tests/test_production_auth.py::test_auth_required_redirects_active_sessions_partial -q` passed with 4 tests.
  - `.venv/bin/pytest tests/test_web_views.py tests/test_production_auth.py tests/test_session_events_api.py tests/test_device_tokens.py -q` passed with 58 tests.
  - `.venv/bin/pytest -q` passed with 231 tests and 12 skipped.

# Issue-Only Dashboard Signals

## User Correction
- [x] Stop making normal raw collector activity feel published to the dashboard.
- [x] Keep the collector able to ingest events for issue detection and context.
- [x] Show dashboard rows only when a session has an actual issue signal, such as an errored tool result or stuck signal.
- [x] Update Agent/live-session copy so the product feels quiet unless something goes wrong.
- [x] Add regression tests proving normal successful sessions stay hidden while issue sessions appear.

## Review Notes
- Dashboard summaries now filter to issue-bearing events only: errored tool results, error-signature tool results, explicit `error` events, or `stuck_emitted` events.
- Normal successful capture can still be stored as private context for detection and later inspection, but it no longer creates dashboard rows or "live session" noise.
- Copy now says "issue signals" instead of "live sessions" and the empty state explicitly says normal collector activity is intentionally hidden.
- Verification completed:
  - `.venv/bin/pytest tests/test_session_events_api.py tests/test_web_views.py tests/test_production_auth.py -q` passed with 53 tests.
  - `.venv/bin/pytest -q` passed with 232 tests and 12 skipped.

# Harvested Issue Broadcast Publishing

## User-Reported Failure
- [x] Explain why a pending harvest was created locally but no Human-tab post appeared.
- [x] Add a narrow collector-scoped issue publishing endpoint for device-token sessions.
- [x] Publish an Open Broadcast to the Human tab when the harvester identifies an issue candidate.
- [x] Keep full harvested field notes/manual entry submission gated until verification is stronger.
- [x] Deduplicate issue broadcasts so retries or repeated harvests do not spam the feed.
- [x] Improve issue context so the dashboard names the error/failing command, not only the session.

## Review Notes
- Investigation found `/Users/maanavagrawal/.fixlog/pending_harvests/8c2986e6c9fd42168a29e07ca5e13d20.json`: the harvester identified the `ai-marketer` issue as a missing `re` import for `_HEX_COLOR_RE`, with a failing import command and a local fix diff. It stayed local because `auto_submit_harvests` is intentionally off by default, and device tokens cannot call the general `/entries` or `/questions` account APIs.
- Added `POST /collector/issues`, a device-token scoped endpoint that creates an Open Broadcast/Question for the authenticated collector session without granting access to the broader account APIs.
- The local watcher now publishes a collector issue whenever the harvester produces a candidate, even while full field-note auto-submit stays off.
- The issue endpoint deduplicates by session and normalized error signature to avoid repeated retry spam.
- Agent issue summaries now include a best-effort issue preview and the matching failing command when the server can derive them from session events.
- Verification completed:
  - `.venv/bin/pytest tests/test_collector_issues.py tests/test_session_events_api.py tests/test_production_auth.py::test_auth_required_allows_device_token_issue_publish tests/harness/test_watcher_pipeline.py -q` passed with 18 tests.
  - `.venv/bin/pytest tests/test_collector_issues.py tests/test_device_tokens.py tests/test_session_events_api.py tests/test_web_views.py tests/test_production_auth.py tests/harness/test_watcher_pipeline.py tests/harness/test_cli.py -q` passed with 76 tests.
  - `.venv/bin/pytest -q` passed with 236 tests and 12 skipped.
