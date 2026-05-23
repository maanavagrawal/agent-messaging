from __future__ import annotations


def build_agent_skill_markdown(*, public_url: str) -> str:
    public_url = public_url.rstrip("/")
    return f"""# Fixlog Agent Setup Skill

You are helping a human connect this local coding repo to Fixlog.

## Goal

Install the Fixlog local collector in the current repo so Claude Code session
events from this repo appear in the Fixlog dashboard.

## What you need

- A Fixlog device token that starts with `flxdt_`.
- If the human has not provided one, ask them to open `{public_url}/settings/devices`,
  create a setup command, and paste only the `flxdt_...` token back to you.

Do not ask for the human dashboard token. You only need a device token.

## Install

From the repo the human wants watched, set the token and run the installer:

```bash
export FIXLOG_DEVICE_TOKEN='<paste-flxdt-device-token-here>'
curl -fsSL {public_url}/install.sh | bash -s -- --token "$FIXLOG_DEVICE_TOKEN"
```

If the human wants background capture on macOS, add `--background`:

```bash
export FIXLOG_DEVICE_TOKEN='<paste-flxdt-device-token-here>'
curl -fsSL {public_url}/install.sh | bash -s -- --token "$FIXLOG_DEVICE_TOKEN" --background
```

## Verify

Run:

```bash
~/.fixlog/bin/fixlog doctor
```

Then start live capture unless `--background` was used:

```bash
~/.fixlog/bin/fixlog watch
```

## Safety

- Do not modify repo source files.
- Do not print or store secrets beyond the local `~/.fixlog/config.toml` written by the installer.
- The collector allowlists the current repo and redacts sensitive values before forwarding events.
- If setup fails, report the failing command and stderr to the human.

## Success criteria

Tell the human to open `{public_url}/sessions/active` and confirm a new
`claude_code` session appears after they use Claude Code in this repo.
"""
