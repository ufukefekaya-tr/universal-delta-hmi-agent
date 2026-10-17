#!/usr/bin/env python3
"""Validate read/resume/edit/commit state; snapshot emits JSON and never writes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _governance import GuardError, TASK_ID, authorize, git, repo_root, session


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS)
    common.add_argument("--task-id", default=argparse.SUPPRESS)
    common.add_argument("--envelope", default=argparse.SUPPRESS)
    common.add_argument("--checkpoint", default=argparse.SUPPRESS)
    result = argparse.ArgumentParser(description=__doc__, parents=[common])
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("resume", parents=[common], help="Verify checkpoint against current HEAD")
    action = sub.add_parser("action", parents=[common], help="Verify an exact edit or atomic commit scope")
    action.add_argument("--kind", choices=("edit", "commit"), required=True)
    action.add_argument("--paths", nargs="+", required=True)
    action.add_argument("--owner", help="Enforce the envelope's exclusive writer scope; required for commit")
    sub.add_parser("snapshot", parents=[common], help="Emit next checkpoint; orchestrator alone persists it")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = repo_root(getattr(args, "root", Path(__file__).resolve().parents[1]))
        task_id = getattr(args, "task_id", None)
        if task_id is not None and not TASK_ID.fullmatch(task_id):
            raise GuardError("Invalid task_id")
        if task_id is None and not hasattr(args, "envelope"):
            raise GuardError("Supply --task-id or an explicit --envelope and --checkpoint")
        state_dir = root / ".agent-state" / (task_id or "")
        envelope_path = Path(getattr(args, "envelope", state_dir / "TASK_ENVELOPE.json"))
        checkpoint_path = Path(getattr(args, "checkpoint", state_dir / "SESSION_CHECKPOINT.json"))
        if not envelope_path.is_absolute():
            envelope_path = root / envelope_path
        if not checkpoint_path.is_absolute():
            checkpoint_path = root / checkpoint_path
        envelope, checkpoint, state = session(root, envelope_path, checkpoint_path, task_id,
                                              allow_advanced_head=args.command == "snapshot")
        if args.command == "action":
            paths = authorize(root, envelope, args.paths, args.owner if args.kind == "edit" else None)
            if args.kind == "commit":
                if args.owner is None or args.owner != envelope.get("commit_owner"):
                    raise GuardError("Commit requires the envelope's commit_owner lease")
                # A root commit owner may integrate other writers' files, so its exclusive
                # edit scope is not the integration commit scope.
                paths = authorize(root, envelope, args.paths)
                staged = git(root, "diff", "--cached", "--name-only", "--no-renames", "-z").decode("utf-8").split("\0")
                staged = [item for item in staged if item]
                if not staged or {item.casefold() for item in staged} != {item.casefold() for item in paths}:
                    raise GuardError("Staged paths must equal the exact requested commit paths")
                authorize(root, envelope, staged)
            state.update(action=args.kind, paths=paths, owner=args.owner, gate="PASS")
        elif args.command == "snapshot":
            output = dict(checkpoint)
            output.update(task_id=state["task_id"], policy_epoch=state["policy_epoch"],
                          envelope_sha256=state["envelope_sha256"], repo_head=state["repo_head"],
                          sequence=checkpoint["sequence"] + 1)
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0
        else:
            state.update(gate="PASS", ack="RESUME_ACK")
        state["limitation"] = "Metadata/path verification only; no claim of policy reading or comprehension."
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    except (GuardError, OSError) as exc:
        print(f"SESSION_GUARD_FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
