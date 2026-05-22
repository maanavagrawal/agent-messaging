from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import httpx

from fixlog_harness.client import FixlogClient
from fixlog_harness.config import HarnessSettings, get_harness_settings
from fixlog_harness.harvester import Harvester, load_pending_harvests
from fixlog_harness.local_config import detect_project_root, write_local_config
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

    settings = get_harness_settings()
    if args.command == "harvest":
        return _harvest_command(args.harvest_command, args.id if hasattr(args, "id") else None)
    if args.command == "connect":
        return _connect(args.url, args.token, args.project)
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
    project_root = project.expanduser().resolve(strict=False) if project else detect_project_root()
    config_path = write_local_config(
        base_url=base_url.rstrip("/"),
        api_token=token,
        project=project_root,
    )
    print(f"connected base_url={base_url.rstrip('/')}")
    print(f"allowed_project={project_root}")
    print(f"config={config_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
