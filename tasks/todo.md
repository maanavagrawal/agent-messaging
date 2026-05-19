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
