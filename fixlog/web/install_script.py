from __future__ import annotations

import shlex


def build_collector_install_script(*, base_url: str, package_url: str) -> str:
    base_url_literal = shlex.quote(base_url.rstrip("/"))
    package_url_literal = shlex.quote(package_url)
    return f"""#!/usr/bin/env bash
set -euo pipefail

DEFAULT_FIXLOG_BASE_URL={base_url_literal}
DEFAULT_FIXLOG_PACKAGE_URL={package_url_literal}

FIXLOG_BASE_URL="${{FIXLOG_BASE_URL:-$DEFAULT_FIXLOG_BASE_URL}}"
FIXLOG_PACKAGE_URL="${{FIXLOG_PACKAGE_URL:-$DEFAULT_FIXLOG_PACKAGE_URL}}"
FIXLOG_INSTALL_DIR="${{FIXLOG_INSTALL_DIR:-$HOME/.fixlog/collector}}"
FIXLOG_BIN_DIR="${{FIXLOG_BIN_DIR:-$HOME/.fixlog/bin}}"
TOKEN=""
PROJECT="$PWD"
RUN_DOCTOR=1
INSTALL_SERVICE=0

usage() {{
  cat <<'USAGE'
Usage:
  curl -fsSL https://your-fixlog.example/install.sh | bash -s -- --token flxdt_...

Options:
  --token <token>          Required device token from the fixlog dashboard.
  --url <url>              Override the fixlog server URL embedded in the script.
  --project <path>         Repo root to allowlist. Defaults to the current directory.
  --install-dir <path>     Collector install directory. Defaults to ~/.fixlog/collector.
  --background             Install and start a macOS LaunchAgent after connecting.
  --skip-doctor            Skip the post-install connectivity check.
  -h, --help               Show this help.
USAGE
}}

need_value() {{
  if [ "$#" -lt 2 ] || [ -z "${{2:-}}" ]; then
    echo "missing value for $1" >&2
    usage >&2
    exit 2
  fi
}}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --token)
      need_value "$@"
      TOKEN="$2"
      shift 2
      ;;
    --url)
      need_value "$@"
      FIXLOG_BASE_URL="${{2%/}}"
      shift 2
      ;;
    --project)
      need_value "$@"
      PROJECT="$2"
      shift 2
      ;;
    --install-dir)
      need_value "$@"
      FIXLOG_INSTALL_DIR="$2"
      shift 2
      ;;
    --background)
      INSTALL_SERVICE=1
      shift
      ;;
    --skip-doctor)
      RUN_DOCTOR=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "$TOKEN" ]; then
  echo "error: --token is required" >&2
  usage >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required to install the fixlog collector" >&2
  exit 1
fi

mkdir -p "$FIXLOG_INSTALL_DIR" "$FIXLOG_BIN_DIR" "$HOME/.fixlog"
python3 -m venv "$FIXLOG_INSTALL_DIR/.venv"
"$FIXLOG_INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
"$FIXLOG_INSTALL_DIR/.venv/bin/python" -m pip install --upgrade "$FIXLOG_PACKAGE_URL"
ln -sf "$FIXLOG_INSTALL_DIR/.venv/bin/fixlog" "$FIXLOG_BIN_DIR/fixlog"

"$FIXLOG_BIN_DIR/fixlog" connect \\
  --url "$FIXLOG_BASE_URL" \\
  --token "$TOKEN" \\
  --project "$PROJECT"

if [ "$RUN_DOCTOR" = "1" ]; then
  "$FIXLOG_BIN_DIR/fixlog" doctor
fi

if [ "$INSTALL_SERVICE" = "1" ]; then
  "$FIXLOG_BIN_DIR/fixlog" service install --start
fi

cat <<DONE

fixlog collector installed and connected.

Run this from any terminal to start live capture:
  $FIXLOG_BIN_DIR/fixlog watch

Optional background service:
  $FIXLOG_BIN_DIR/fixlog service install --start

Optional PATH setup:
  export PATH="$FIXLOG_BIN_DIR:$PATH"

DONE
"""
