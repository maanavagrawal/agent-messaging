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
- Verification completed:
  - `.venv/bin/pytest -q` with 134 passed and 1 gated live smoke skipped.
  - `.venv/bin/alembic upgrade head` against `/tmp/fixlog-phase3-alembic.sqlite3`.
  - `.venv/bin/python -m compileall fixlog fixlog_harness scripts tests`.
  - `scripts/dev_seed.py` ran twice against `/tmp/fixlog-phase3-seed.sqlite3`.
