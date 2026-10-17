# SPDX-License-Identifier: Apache-2.0
"""Optional read-only qualification of explicitly supplied private source hashes.

Run with --manifest, --workspace and --report. The manifest contains a sources
list of {source_id, path, sha256, optional profile}. IDs must be neutral public
labels. Paths are resolved relative to the private manifest, never published.
A profile is inline JSON or a path accompanied by profile_sha256. A supplied
profile must explicitly acknowledge the exact reviewed indexed layout; this
tool never manufactures resource ownership or writes native candidates.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

# Repository-relative discovery, not a host-specific installation path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from universal_diascreen_hmi.errors import AgentError, digest, require
from universal_diascreen_hmi.native import LIMIT, Project, layout_digest, restore_spans
from universal_diascreen_hmi.operations import canonical, compile_changes
from universal_diascreen_hmi.session import profile_check


def _object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "QUAL_JSON", "Duplicate JSON key")
        value[key] = item
    return value


def _local_path(value, base):
    require(isinstance(value, str) and value and "\0" not in value
            and not value.startswith(("\\\\", "//")) and "://" not in value,
            "QUAL_PATH", "An explicit local file path is required")
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    for part in (path, *path.parents):
        require(not part.is_symlink() and not (hasattr(part, "is_junction") and part.is_junction()),
                "QUAL_PATH_LINK", "Linked paths are not qualification inputs or outputs")
    return path.resolve(strict=False)


def _read(path, limit):
    require(path.is_file() and path.stat().st_size <= limit, "QUAL_INPUT", "Input absent or oversized")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "QUAL_INPUT", "Input exceeded the bounded read")
    return raw


def _decode_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_object)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, AgentError):
            raise
        raise AgentError("QUAL_JSON", "Invalid bounded JSON input") from exc


def _json(path):
    return _decode_json(_read(path, 2 * 1024 * 1024))


def _hash(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
            "QUAL_HASH", "A complete lowercase source hash is required")
    return value


def _profile(entry, base):
    supplied = entry["profile"]
    if isinstance(supplied, dict):
        value = supplied
        identity = digest(canonical(value))
        if "profile_sha256" in entry:
            require(identity == _hash(entry["profile_sha256"]), "QUAL_PROFILE_HASH", "Profile hash differs")
    else:
        path = _local_path(supplied, base)
        raw = _read(path, 2 * 1024 * 1024)
        identity = _hash(entry.get("profile_sha256"))
        require(digest(raw) == identity, "QUAL_PROFILE_HASH", "Profile hash differs")
        value = _decode_json(raw)
    require(isinstance(value, dict), "QUAL_PROFILE", "Expected an explicit profile object")
    return value, identity


def _counts(project):
    return {"pages": len(project.pages), "elements": sum(len(page.elements) for page in project.pages),
            "states": sum(len(element.states) for page in project.pages for element in page.elements)}


def qualify_one(entry, base):
    """Return only neutral identity, hashes, counts and bounded result codes."""
    row = {"source_id": entry["source_id"], "sha256": entry["sha256"], "status": "STOP"}
    path = None
    original = None
    try:
        path = _local_path(entry["path"], base)
        original = _read(path, LIMIT)
        require(digest(original) == entry["sha256"], "QUAL_SOURCE_HASH", "Source bytes differ")
        project = Project(original)
        row.update(_counts(project))
        require(project.file.encode(project.file.payload) == original, "QUAL_NOOP", "No-op container changed bytes")
        row["noop_status"] = "BYTE_EXACT"
        require(not project.index.unqualified_records and not project.index.stop_reason.startswith(("unknown_", "unknown_section:")),
                "INDEX_UNQUALIFIED", "Source contains unqualified indexed framing")
        row["indexed_status"] = "KNOWN_PREAMBLE_AND_INDEXED_OWNERS_ONLY"
        if "profile" not in entry:
            row.update(status="PASS_NOOP_ONLY", visual_status="NOT_REQUESTED")
        else:
            profile, profile_sha = _profile(entry, base)
            row["profile_sha256"] = profile_sha
            profile_check(project, profile)
            require(profile.get("reviewed_index_ack") is True
                    and profile.get("indexed_layout_sha256") == layout_digest(project),
                    "INDEX_REVIEW", "Profile must explicitly review the actual indexed layout")
            selected = None
            for page in project.pages:
                for element in page.elements:
                    for state in element.states:
                        color = state.one("FontColor", optional=True)
                        if color is not None:
                            selected = (page, element, state, color)
                            break
                    if selected is not None:
                        break
                if selected is not None:
                    break
            require(selected is not None, "QUAL_NO_VISUAL_OWNER", "No indexed font color owner exists")
            page, element, state, color = selected
            before = project.index.number(state, "FontColor")
            require(0 <= before <= 0xFFFFFF, "QUAL_COLOR", "Existing color is outside the qualified scalar profile")
            operation = {"op": "set_property", "page_id": page.page_id,
                         "element_id": project.index.number(element.section, "nPartsID"),
                         "state_value": project.index.number(state, "Value"), "field": "FontColor",
                         "expected": color.value.decode("ascii"), "value": before ^ 1}
            # All edits are confined to an in-memory candidate. No resource review
            # entries are inferred from textual patterns, section names or contents.
            candidate, steps = compile_changes(original, [operation], profile)
            reread = Project(candidate)
            restored = reread.file.payload
            for step in reversed(steps):
                restored = restore_spans(restored, step["ledger"])
            require(restored == project.file.payload and reread.file.thumbnail == project.file.thumbnail,
                    "QUAL_INVERSE", "Full source payload or thumbnail inverse differs")
            require(_counts(reread) == _counts(project), "QUAL_COUNTS", "A style patch changed owner counts")
            require(candidate != original, "QUAL_NO_CHANGE", "Visual qualification did not change a candidate")
            row.update(status="PASS_OFFLINE_FONT_COLOR_INVERSE", visual_status="IN_MEMORY_INVERSE_PASS",
                       candidate_sha256=digest(candidate))
    except AgentError as exc:
        row.update(status="STOP", code=exc.code)
    except (OSError, ValueError, TypeError, KeyError):
        # Native source values and filesystem exceptions may contain private data.
        row.update(status="STOP", code="QUAL_INPUT_OR_FORMAT")
    if path is not None and original is not None:
        try:
            require(_read(path, LIMIT) == original, "QUAL_SOURCE_DRIFT", "Read-only source changed during qualification")
            row["source_status"] = "BYTE_EXACT_UNCHANGED"
        except (AgentError, OSError):
            row.update(status="STOP", code="QUAL_SOURCE_DRIFT", source_status="CHANGED_OR_UNAVAILABLE")
    return row


def qualify_manifest(manifest_path):
    path = _local_path(str(manifest_path), Path.cwd())
    value = _json(path)
    entries = value.get("sources") if isinstance(value, dict) else value
    require(isinstance(entries, list) and 1 <= len(entries) <= 256,
            "QUAL_MANIFEST", "Manifest must contain 1..256 explicit sources")
    identities = set()
    for entry in entries:
        require(isinstance(entry, dict) and {"source_id", "path", "sha256"} <= set(entry)
                and set(entry) <= {"source_id", "path", "sha256", "profile", "profile_sha256"},
                "QUAL_MANIFEST", "Unexpected or incomplete source manifest fields")
        identity = entry["source_id"]
        require(isinstance(identity, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", identity)
                and identity not in identities, "QUAL_ID", "Unique neutral source IDs are required")
        identities.add(identity)
        _hash(entry["sha256"])
    rows = [qualify_one(entry, path.parent) for entry in entries]
    return {"schema_version": 1, "status": "PASS" if all(row["status"].startswith("PASS_") for row in rows) else "STOP",
            "source_count": len(rows), "sources": rows, "vendor_compile": "NOT_RUN",
            "native_pixels": "NOT_RUN", "panel_runtime": "NOT_RUN", "physical": "NOT_RUN"}


def run(manifest_path, workspace, report_path):
    workspace = _local_path(str(workspace), Path.cwd())
    require(workspace.is_dir(), "QUAL_WORKSPACE", "Task workspace must already exist")
    report_path = _local_path(str(report_path), workspace)
    require(report_path.is_relative_to(workspace) and report_path.parent.is_dir() and not report_path.exists(),
            "QUAL_REPORT", "Report must be a new file below the explicit task workspace")
    result = qualify_manifest(manifest_path)
    raw = (json.dumps(result, ensure_ascii=True, indent=2) + "\n").encode("ascii")
    # O_EXCL prevents overwriting even if another process creates the file after validation.
    descriptor = os.open(report_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only optional private source qualification; no native candidates are saved.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--report", required=True)
    arguments = parser.parse_args(argv)
    try:
        result = run(arguments.manifest, arguments.workspace, arguments.report)
    except AgentError as exc:
        print(json.dumps({"status": "STOP", "code": exc.code}))
        return 2
    except Exception:
        print(json.dumps({"status": "STOP", "code": "QUAL_INPUT_OR_INTERNAL"}))
        return 2
    print(json.dumps({"status": result["status"], "source_count": result["source_count"]}))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
