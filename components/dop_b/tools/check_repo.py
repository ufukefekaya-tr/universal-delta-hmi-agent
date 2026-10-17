#!/usr/bin/env python3
"""Check committed bootstrap or repository documentation/template integrity."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from _governance import GuardError, contained, read_json, repo_root, verify_bootstrap

ROLE_NAMES = ("ANALYST", "ARCHITECT", "DESIGNER", "PROGRAMMER", "VERIFIER", "TENTH_MAN",
              "AESTHETIC_FIRST", "AESTHETIC_SECOND", "KAIZEN")


def check_repository(root: Path) -> dict:
    state = verify_bootstrap(root)
    required = ["docs/WORKFLOW.md", "docs/GOALS.md", "docs/SUPPORT_MATRIX.md", "docs/ARCHITECTURE.md",
                "docs/EVIDENCE.md", "docs/NEW_PROJECT.md", "docs/HUMAN_HANDOFF.md", "docs/DESIGN.md",
                "prompts/START_NEW_PROJECT.md", "prompts/roles/README.md", "templates/README.md",
                "kaizen/README.md", "projects/README.md"]
    required.extend(f"prompts/roles/{name}.md" for name in ROLE_NAMES)
    for relative in required:
        contained(root, relative)
        if not (root / relative).is_file() or not (root / relative).read_text(encoding="utf-8").strip():
            raise GuardError(f"Missing/empty repository document: {relative}")
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", (root / "INDEX.md").read_text(encoding="utf-8"))
    for target in links:
        relative = target.split("#", 1)[0]
        if not relative or "://" in relative:
            continue
        contained(root, relative)
        if not (root / relative).exists():
            raise GuardError(f"Broken INDEX link: {relative}")
    templates = list((root / "templates").glob("*.json"))
    if len(templates) < 6:
        raise GuardError("Expected substantive profile/design/approval/evidence/review JSON templates")
    for path in templates:
        contained(root, path.relative_to(root).as_posix())
        value, _ = read_json(path)
        if not value:
            raise GuardError(f"Empty JSON template: {path.name}")
    state.update(documents_checked=len(required), index_links_checked=len(links), json_templates_checked=len(templates))
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--verify-bootstrap", action="store_true")
    parser.add_argument("--policy-epoch", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = repo_root(args.root)
        state = verify_bootstrap(root) if args.verify_bootstrap or args.policy_epoch else check_repository(root)
        if args.json:
            print(json.dumps(state, ensure_ascii=False, indent=2))
        elif args.policy_epoch and not args.verify_bootstrap:
            print(state["policy_epoch"])
        else:
            print(f"BOOTSTRAP_VERIFIED HEAD={state['repo_head']}")
            if args.policy_epoch:
                print(f"POLICY_EPOCH={state['policy_epoch']}")
            if "documents_checked" in state:
                print(f"REPO_VERIFIED documents={state['documents_checked']} templates={state['json_templates_checked']}")
        return 0
    except (GuardError, OSError) as exc:
        print(f"CHECK_REPO_FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
