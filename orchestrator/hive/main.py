from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .controller import HiveController
from .protocol import JobMode, JobRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hive Codex orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a boss-mode job")
    run_parser.add_argument("--repo", default=".", help="Repository root")
    run_parser.add_argument("--job", required=True, help="Boss prompt")
    run_parser.add_argument(
        "--acceptance",
        action="append",
        default=[],
        help="Explicit acceptance criterion; repeat for multiple values",
    )
    run_parser.add_argument(
        "--mode",
        choices=[mode.value for mode in JobMode],
        default=JobMode.AUTO.value,
        help="auto uses Agents SDK when configured; dry-run only emits artifacts",
    )
    return parser


async def async_main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command != "run":
        parser.error(f"Unsupported command: {args.command}")

    repo_root = Path(args.repo).resolve()
    controller = HiveController(repo_root)
    record = await controller.run_job(
        JobRequest(
            boss_prompt=args.job,
            repo_path=str(repo_root),
            acceptance=args.acceptance,
            mode=JobMode(args.mode),
        )
    )

    summary = {
        "job_id": record.job_id,
        "status": record.status.value,
        "run_dir": record.artifacts.run_dir,
        "delivery_path": record.artifacts.delivery,
        "runtime_notes": record.runtime_notes,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def entrypoint() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    entrypoint()

