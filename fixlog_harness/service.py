from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

LAUNCH_AGENT_LABEL = "com.fixlog.collector"


def default_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def default_log_dir() -> Path:
    return Path.home() / ".fixlog" / "logs"


def resolve_fixlog_bin(value: Path | None = None) -> Path:
    if value is not None:
        return value.expanduser().resolve(strict=False)
    discovered = shutil.which("fixlog")
    if discovered is not None:
        return Path(discovered).resolve(strict=False)
    return Path(sys.argv[0]).expanduser().resolve(strict=False)


def build_launch_agent_plist(*, fixlog_bin: Path, log_dir: Path) -> bytes:
    log_dir = log_dir.expanduser().resolve(strict=False)
    payload = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [str(fixlog_bin), "watch"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(Path.home()),
        "StandardOutPath": str(log_dir / "collector.out.log"),
        "StandardErrorPath": str(log_dir / "collector.err.log"),
    }
    return plistlib.dumps(payload, sort_keys=True)


def render_launch_agent_plist(*, fixlog_bin: Path, log_dir: Path) -> str:
    return build_launch_agent_plist(fixlog_bin=fixlog_bin, log_dir=log_dir).decode(
        "utf-8"
    )


def install_launch_agent(
    *,
    fixlog_bin: Path,
    log_dir: Path | None = None,
    plist_path: Path | None = None,
    start: bool = False,
) -> Path:
    _require_macos()
    log_dir = log_dir or default_log_dir()
    plist_path = plist_path or default_plist_path()
    log_dir.mkdir(parents=True, exist_ok=True)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(
        build_launch_agent_plist(fixlog_bin=fixlog_bin, log_dir=log_dir)
    )
    if start:
        _launchctl_bootstrap(plist_path)
    return plist_path


def uninstall_launch_agent(plist_path: Path | None = None) -> Path:
    _require_macos()
    plist_path = plist_path or default_plist_path()
    _run_launchctl(["bootout", _launch_domain(), str(plist_path)], check=False)
    plist_path.unlink(missing_ok=True)
    return plist_path


def print_launch_agent_status() -> int:
    _require_macos()
    result = _run_launchctl(
        ["print", f"{_launch_domain()}/{LAUNCH_AGENT_LABEL}"],
        check=False,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def _launchctl_bootstrap(plist_path: Path) -> None:
    _run_launchctl(["bootout", _launch_domain(), str(plist_path)], check=False)
    _run_launchctl(["bootstrap", _launch_domain(), str(plist_path)])
    _run_launchctl(["kickstart", "-k", f"{_launch_domain()}/{LAUNCH_AGENT_LABEL}"])


def _run_launchctl(
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *args],
        text=True,
        capture_output=True,
        check=check,
    )


def _launch_domain() -> str:
    return f"gui/{os.getuid()}"


def _require_macos() -> None:
    if sys.platform != "darwin":
        raise RuntimeError("fixlog service install is only supported on macOS")
