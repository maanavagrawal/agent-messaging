# Idempotency Verification

Generated during Phase 2.5 after switching canonical strings to the ASCII Unit
Separator (`\x1f`) format.

## Full Fixture Run

```text
fixtures verified: 20
error_kind changes on round-trip: 16
- pip/dependency_conflict.txt: pip -> generic
- pip/version_not_found.txt: pip -> generic
- pytest/assertion_dict_mismatch.txt: pytest -> generic
- pytest/assertion_string_diff.txt: pytest -> generic
- pytest/fixture_error.txt: pytest -> generic
- pytest/parametrized_failure.txt: pytest -> generic
- traceback/attribute_error.txt: traceback -> generic
- traceback/chained_exception.txt: traceback -> generic
- traceback/deep_traceback_100_frames.txt: traceback -> generic
- traceback/django_does_not_exist.txt: traceback -> generic
- traceback/import_error.txt: traceback -> generic
- traceback/keyerror_session_id.txt: traceback -> generic
- traceback/psycopg_undefined_column.txt: traceback -> generic
- traceback/recursion_error.txt: traceback -> generic
- traceback/type_error_nonetype.txt: traceback -> generic
- traceback/valueerror_in_init.txt: traceback -> generic
idempotency verification passed
```

## Manual Spot Check

Command:

```bash
.venv/bin/python scripts/verify_idempotency.py --verbose --only traceback/psycopg_undefined_column.txt --only pytest/assertion_dict_mismatch.txt --only generic/json_error_response.txt
```

Output:

```text
--- generic/json_error_response.txt ---
raw:
{"error":"invalid_request","request_id":"550e8400-e29b-41d4-a716-446655440000","created_at":"2026-05-19T04:13:54Z","path":"/home/danny/proj/app.py"}
result1.canonical_string:
GenericError\x1f{"error":"invalid_request","request_id":"<UUID>","created_at":"<TS>","path":"app.py"}\x1f<none>::<none>\x1f<none>
result2.canonical_string:
GenericError\x1f{"error":"invalid_request","request_id":"<UUID>","created_at":"<TS>","path":"app.py"}\x1f<none>::<none>\x1f<none>

--- pytest/assertion_dict_mismatch.txt ---
raw:
FAILED tests/test_api.py::test_create_user - AssertionError: assert 'user_name' in {'username': 'alice'}
result1.canonical_string:
AssertionError\x1fassert 'user_name' in {'username': 'alice'}\x1ftest_api::test_create_user\x1ftest_api::test_create_user
result2.canonical_string:
AssertionError\x1fassert 'user_name' in {'username': 'alice'}\x1ftest_api::test_create_user\x1ftest_api::test_create_user

--- traceback/psycopg_undefined_column.txt ---
raw:
Traceback (most recent call last):
  File "/home/danny/proj/app.py", line 42, in handle_request
    user = db.get_user(user_id)
  File "/home/danny/proj/db.py", line 18, in get_user
    return self._conn.execute(query, (user_id,)).fetchone()
psycopg2.errors.UndefinedColumn: column "user_name" does not exist
LINE 1: SELECT user_name FROM users WHERE id = 42
               ^
result1.canonical_string:
psycopg2.errors.UndefinedColumn\x1fcolumn "user_name" does not exist LINE 1: SELECT user_name FROM users WHERE id = <N>\x1fdb::get_user\x1fapp::handle_request>db::get_user
result2.canonical_string:
psycopg2.errors.UndefinedColumn\x1fcolumn "user_name" does not exist LINE 1: SELECT user_name FROM users WHERE id = <N>\x1fdb::get_user\x1fapp::handle_request>db::get_user
fixtures verified: 3
error_kind changes on round-trip: 2
- pytest/assertion_dict_mismatch.txt: pytest -> generic
- traceback/psycopg_undefined_column.txt: traceback -> generic
idempotency verification passed
```

## Judgment

The `error_kind` transitions are acceptable. Raw traceback, pytest, and pip
fixtures are classified by their original input shape. Canonical strings are a
different input shape, and the canonical parser currently reports that
round-trip input as `generic`. The fields that define the lookup identity
round-trip exactly: `canonical_string`, `hash`, `exception_type`, and
`exception_message`.
