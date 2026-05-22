# fixlog

fixlog stores verified error-fix pairs for AI coding agents. Each entry includes
a canonical error signature, diagnosis, fix diff, runnable reproduction commands,
and a sandbox spec. Phase 1 builds the foundational plumbing: schema, REST
API, identity, and a read-only HTMX/Jinja web feed. Phase 2 adds a standalone
Python error signature normalizer. Phase 3 adds a Claude Code log-watcher
harness that replays or tails session logs into redacted SessionEvents.

## Phase 1 Includes

- FastAPI app serving REST API and web UI from one process.
- SQLite storage with SQLAlchemy 2.0 models and Alembic migration.
- sqlite-vec dependency and nullable embedding column for future vector search.
- Token-gated writes with open read access.
- Account, AgentPersona, Session identity flow.
- Entries, questions, verifications, confirm/reject, feed, and normalized exact-match search.
- Read-only web pages for feed, entry detail, and question detail.
- Idempotent dev seed script.

## Phase 2 Includes

- Pure Python normalizer at `fixlog.normalizer.normalize_python_error`.
- Pydantic `PythonErrorSignature` model with deterministic canonical strings
  and `sha256(canonical_string)[:16]` hashes.
- Canonical strings use ASCII Unit Separator (`\x1f`) between fields.
- Parsers for standard tracebacks, pytest output, pip errors, and generic logs.
- A fixture-driven normalizer corpus plus determinism, idempotency, and regex
  performance tests.
- POST `/entries`, POST `/questions`, and GET `/search` normalize raw Python
  error text server-side.

## Phase 3 Includes

- `fixlog_harness` package with normalized event models, parser ABC, and a
  Claude Code JSONL parser.
- Mandatory redaction before parsed events leave the parser.
- Replay/watch pipeline that maps Claude sessions to fixlog sessions and posts
  redacted events to `POST /sessions/{session_id}/events`.
- Stuck detection for repeated errors and thrashing.
- Harvest extraction that writes pending candidate entries for manual review.
- `fixlog replay`, `fixlog watch`, and `fixlog harvest ...` CLI commands.
- Active sessions page at `/sessions/active`.

## Not Implemented

- Embedding generation or vector search.
- Codex/Cursor/Aider/Continue parsers.
- Auto-querying, pulling, or applying fixes.
- MCP server.
- Confidence scoring, reputation enforcement, rate limiting.
- Public signup or multi-user auth beyond shared bearer tokens.

## Setup

Use Python 3.11 or newer.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` and replace both account tokens with long random values.

Required environment variables:

- `DATABASE_URL`
- `FIXLOG_PUBLIC_URL`
- `FIXLOG_ACCOUNT_1_TOKEN`
- `FIXLOG_ACCOUNT_1_NAME`
- `FIXLOG_ACCOUNT_2_TOKEN`
- `FIXLOG_ACCOUNT_2_NAME`
- `FIXLOG_AUTH_REQUIRED`
- `FIXLOG_WEB_SECRET_KEY`
- `FIXLOG_WEB_COOKIE_SECURE`
- `FIXLOG_COLLECTOR_PACKAGE_URL`, optional Git/pip URL for the collector installer

Harness environment variables:

- `FIXLOG_BASE_URL`
- `FIXLOG_API_TOKEN`
- `FIXLOG_CONFIG_PATH`, default `~/.fixlog/config.toml`
- `FIXLOG_CLAUDE_PROJECTS_DIR`
- `FIXLOG_ALLOWED_PROJECTS`, JSON list of repo roots to forward, default all
- `FIXLOG_SESSION_MAP_PATH`
- `FIXLOG_PENDING_HARVEST_DIR`
- `ANTHROPIC_API_KEY` for harvest prompt generation
- `FIXLOG_AUTO_SUBMIT_HARVESTS`, default `false`

Sandbox environment variables:

- `FIXLOG_SANDBOX_ALLOWED_IMAGES`
- `FIXLOG_SANDBOX_QUEUE_SIZE`
- `FIXLOG_SANDBOX_TIMEOUT_S`
- `FIXLOG_SANDBOX_MEMORY_MB`
- `FIXLOG_VERIFIER_ENABLED`, default `true`

## Database

Run the initial migration:

```bash
alembic upgrade head
```

The app seeds the two configured accounts on startup. Missing account env vars
raise a clear startup error.

## Run The Server

```bash
uvicorn fixlog.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

Healthcheck:

```bash
curl http://127.0.0.1:8000/healthz
```

## Railway Pilot Deploy

Railway runs the server/dashboard. Each developer still runs `fixlog watch`
locally because Claude Code logs live on their laptop.

Create a Railway service from this repo. The included `Dockerfile` and
`railway.json` run migrations and start Uvicorn on Railway's `$PORT`.

For a two-person SQLite pilot, attach a Railway volume mounted at `/data`, then
set:

```bash
DATABASE_URL=sqlite:////data/fixlog.sqlite3
FIXLOG_PUBLIC_URL=https://<your-railway-domain>
FIXLOG_ACCOUNT_1_NAME=Maanav
FIXLOG_ACCOUNT_1_TOKEN=<long random token for you>
FIXLOG_ACCOUNT_2_NAME=<cofounder name>
FIXLOG_ACCOUNT_2_TOKEN=<long random token for cofounder>
FIXLOG_AUTH_REQUIRED=true
FIXLOG_WEB_SECRET_KEY=<long random cookie signing secret>
FIXLOG_WEB_COOKIE_SECURE=true
FIXLOG_COLLECTOR_PACKAGE_URL=git+https://github.com/maanavagrawal/agent-messaging.git@main
FIXLOG_VERIFIER_ENABLED=false
```

Keep `FIXLOG_VERIFIER_ENABLED=false` on the Railway web service unless you add a
separate Docker-capable verifier worker. Railway is a good home for the API/UI,
but the sandbox runner needs access to a Docker daemon and should not assume one
exists inside the hosted web container.

After deploy, open the Railway URL and sign in with either configured account
token. Both tokens can view the shared dashboard. Agent writes are still
account-scoped through bearer auth.

Create a collector token from the dashboard:

1. Open `https://<your-railway-domain>/settings/devices`.
2. Sign in with your account token if prompted.
3. Create a device token.
4. Copy the one-time install command and run it from the repo you want to
   watch. The installer creates `~/.fixlog/collector/.venv`, installs the
   `fixlog` CLI, writes `~/.fixlog/config.toml`, and allowlists the current
   repo.

For scripts or recovery, the same token can be created through the API:

```bash
curl -X POST https://<your-railway-domain>/device-tokens \
  -H "Authorization: Bearer <FIXLOG_ACCOUNT_1_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Maanav MacBook Pro"}'
```

The response includes a one-time `flxdt_...` token. Store that in the local
collector with `fixlog connect`; device tokens are scoped to session ingestion
and cannot access general account APIs.

Local watcher setup for you:

```bash
cd /path/to/repo-you-want-to-watch
curl -fsSL https://<your-railway-domain>/install.sh | bash -s -- --token <flxdt-device-token>
~/.fixlog/bin/fixlog watch
```

Local watcher setup for your cofounder:

```bash
cd /path/to/repo-your-cofounder-wants-to-watch
curl -fsSL https://<your-railway-domain>/install.sh | bash -s -- --token <cofounder-flxdt-device-token>
~/.fixlog/bin/fixlog watch
```

On macOS, install the watcher as a background LaunchAgent after connecting:

```bash
~/.fixlog/bin/fixlog service install --start
~/.fixlog/bin/fixlog service status
```

Or do it during install:

```bash
curl -fsSL https://<your-railway-domain>/install.sh | bash -s -- --token <flxdt-device-token> --background
```

`fixlog connect` writes `~/.fixlog/config.toml`, detects the current git root,
and adds that repo to the local allowlist. The watcher still tails Claude Code's
global `~/.claude/projects` logs, but only forwards events whose `cwd` is under
an allowlisted repo. `fixlog doctor` checks the hosted health endpoint, token
auth, local Claude projects path, and configured allowlist before the watcher
starts.

## Start A Session

```bash
curl -X POST http://127.0.0.1:8000/sessions/start \
  -H "Authorization: Bearer $FIXLOG_ACCOUNT_1_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_name":"claude-sonnet-4-5","harness_name":"codex"}'
```

Use the returned `session_id` as `X-Fixlog-Session-Id` for write endpoints that
require a session.

## Dev Seed

Against a fresh database:

```bash
python scripts/dev_seed.py
```

The seed is idempotent. It creates:

- 2 accounts from env vars
- 4 personas
- 10 entries
- 5 questions
- 2 linked questions
- 8 verifications
- 2 ordinary edits and 1 supersession edit

## Tests

```bash
pytest
```

The tests use isolated temporary SQLite databases and FastAPI dependency
overrides, so they do not touch your local `fixlog.sqlite3`.

## Harness

Replay a Claude Code session log:

```bash
fixlog replay ~/.claude/projects/<project-slug>/<session-uuid>.jsonl
```

Watch recently modified Claude Code logs:

```bash
fixlog watch
```

Review pending harvests:

```bash
fixlog harvest review
fixlog harvest submit <id>
fixlog harvest discard <id>
```

Auto-submit is off by default. Keep it off until sandbox verification exists.

## API Notes

`GET /entries/{id}` and `GET /questions/{id}` use content negotiation:
browsers requesting `text/html` get server-rendered pages, and API clients
requesting JSON get JSON responses.
