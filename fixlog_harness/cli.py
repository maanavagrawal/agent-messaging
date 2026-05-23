from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

import httpx

from fixlog_harness.client import FixlogClient
from fixlog_harness.config import (
    HarnessSettings,
    get_harness_settings,
    validate_fixlog_base_url,
)
from fixlog_harness.harvester import Harvester, load_pending_harvests
from fixlog_harness.local_config import detect_project_root, write_local_config
from fixlog_harness.service import (
    default_log_dir,
    install_launch_agent,
    print_launch_agent_status,
    render_launch_agent_plist,
    resolve_fixlog_bin,
    uninstall_launch_agent,
)
from fixlog_harness.stuck_detector import StuckDetector
from fixlog_harness.watcher import HarnessPipeline, SessionMapStore, watch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fixlog")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("watch")
    subcommands.add_parser("doctor")
    connect = subcommands.add_parser("connect")
    connect.add_argument("--url", required=True)
    connect.add_argument("--token", required=True)
    connect.add_argument("--project", type=Path)
    service = subcommands.add_parser("service")
    service_subcommands = service.add_subparsers(
        dest="service_command",
        required=True,
    )
    service_install = service_subcommands.add_parser("install")
    service_install.add_argument("--start", action="store_true")
    service_install.add_argument("--dry-run", action="store_true")
    service_install.add_argument("--fixlog-bin", type=Path)
    service_install.add_argument("--log-dir", type=Path)
    service_subcommands.add_parser("uninstall")
    service_subcommands.add_parser("status")
    replay = subcommands.add_parser("replay")
    replay.add_argument("path", type=Path)
    harvest = subcommands.add_parser("harvest")
    harvest_subcommands = harvest.add_subparsers(dest="harvest_command", required=True)
    harvest_subcommands.add_parser("review")
    submit = harvest_subcommands.add_parser("submit")
    submit.add_argument("id")
    discard = harvest_subcommands.add_parser("discard")
    discard.add_argument("id")
    args = parser.parse_args(argv)

    if args.command == "harvest":
        return _harvest_command(args.harvest_command, args.id if hasattr(args, "id") else None)
    if args.command == "connect":
        return _connect(args.url, args.token, args.project)
    if args.command == "service":
        return _service_command(args)

    try:
        settings = get_harness_settings()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.command == "doctor":
        return _doctor(settings)

    pipeline = HarnessPipeline(
        client=FixlogClient(settings),
        session_store=SessionMapStore(settings.session_map_path),
        detector=StuckDetector(),
        harvester=Harvester(settings),
        allowed_projects=settings.allowed_projects,
    )
    if args.command == "replay":
        pipeline.replay_file(args.path)
        return 0
    if args.command == "watch":
        _configure_logging()
        try:
            watch(settings, pipeline)
        except KeyboardInterrupt:
            return 0
        return 0
    return 1


def _harvest_command(command: str, harvest_id: str | None) -> int:
    settings = get_harness_settings()
    pending = load_pending_harvests(settings.pending_harvest_dir)
    if command == "review":
        for candidate in pending:
            print(
                json.dumps(
                    {
                        "id": candidate.id,
                        "project_slug": candidate.project_slug,
                        "error_signature": candidate.error_signature,
                        "failing_command": candidate.failing_command,
                    },
                    sort_keys=True,
                )
            )
        return 0
    selected = next((item for item in pending if item.id == harvest_id), None)
    if selected is None or selected.pending_path is None:
        print(f"pending harvest not found: {harvest_id}")
        return 1
    if command == "discard":
        selected.pending_path.unlink(missing_ok=True)
        print(f"discarded {selected.id}")
        return 0
    if command == "submit":
        FixlogClient(settings).submit_candidate(selected)
        selected.pending_path.unlink(missing_ok=True)
        print(f"submitted {selected.id}")
        return 0
    return 1


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
    )


def _doctor(settings: HarnessSettings) -> int:
    base_url = settings.fixlog_base_url
    token = settings.fixlog_api_token
    projects_dir = settings.claude_projects_dir
    ok = True
    print(f"base_url={base_url}")
    print(f"claude_projects_dir={projects_dir}")
    allowed_projects = getattr(settings, "allowed_projects", [])
    if allowed_projects:
        print(
            "allowed_projects="
            + ",".join(str(path) for path in allowed_projects)
        )
    else:
        print("allowed_projects=all")
    if not token:
        print("auth=missing FIXLOG_API_TOKEN")
        ok = False
    if not projects_dir.exists():
        print("claude_projects_dir_status=missing")
        ok = False
    else:
        print("claude_projects_dir_status=ok")

    try:
        with httpx.Client(base_url=base_url, timeout=10) as client:
            health = client.get("/healthz")
            print(f"healthz={health.status_code}")
            if health.status_code != 200:
                ok = False
            if token:
                auth_check = client.get(
                    "/collector/status",
                    headers={"Authorization": f"Bearer {token}"},
                )
                print(f"auth_check={auth_check.status_code}")
                if auth_check.status_code != 200:
                    ok = False
    except httpx.HTTPError as exc:
        print(f"server=unreachable {exc}")
        ok = False

    return 0 if ok else 1


def _connect(base_url: str, token: str, project: Path | None) -> int:
    try:
        normalized_base_url = validate_fixlog_base_url(base_url)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    project_root = project.expanduser().resolve(strict=False) if project else detect_project_root()
    config_path = write_local_config(
        base_url=normalized_base_url,
        api_token=token,
        project=project_root,
    )
    print(f"connected base_url={normalized_base_url}")
    print(f"allowed_project={project_root}")
    print(f"config={config_path}")
    return 0


def _service_command(args: argparse.Namespace) -> int:
    try:
        if args.service_command == "install":
            fixlog_bin = resolve_fixlog_bin(args.fixlog_bin)
            log_dir = (
                args.log_dir.expanduser().resolve(strict=False)
                if args.log_dir is not None
                else default_log_dir()
            )
            if args.dry_run:
                print(render_launch_agent_plist(fixlog_bin=fixlog_bin, log_dir=log_dir))
                return 0
            plist_path = install_launch_agent(
                fixlog_bin=fixlog_bin,
                log_dir=log_dir,
                start=args.start,
            )
            print(f"service_plist={plist_path}")
            print(f"service_logs={log_dir}")
            if args.start:
                print("service_status=started")
            else:
                print("service_status=installed")
                print("start_hint=fixlog service install --start")
            return 0
        if args.service_command == "uninstall":
            plist_path = uninstall_launch_agent()
            print(f"service_removed={plist_path}")
            return 0
        if args.service_command == "status":
            return print_launch_agent_status()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"launchctl failed with exit_code={exc.returncode}", file=sys.stderr)
        if exc.stdout:
            print(exc.stdout, end="", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, end="", file=sys.stderr)
        return exc.returncode or 1
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
