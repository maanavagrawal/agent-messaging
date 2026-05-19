from __future__ import annotations

import argparse
import json
from pathlib import Path

from fixlog_harness.client import FixlogClient
from fixlog_harness.config import get_harness_settings
from fixlog_harness.harvester import Harvester, load_pending_harvests
from fixlog_harness.stuck_detector import StuckDetector
from fixlog_harness.watcher import HarnessPipeline, SessionMapStore, watch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fixlog")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("watch")
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

    pipeline = HarnessPipeline(
        client=FixlogClient(settings),
        session_store=SessionMapStore(settings.session_map_path),
        detector=StuckDetector(),
        harvester=Harvester(settings),
    )
    if args.command == "replay":
        pipeline.replay_file(args.path)
        return 0
    if args.command == "watch":
        watch(settings, pipeline)
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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
