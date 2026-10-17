"""Offline repository/session checks. These checks do not prove comprehension."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

CONTROL_PLANE = ("AGENTS.md", "SYSTEM_PROMPT.md", "INDEX.md")
TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40,64}\Z")


class GuardError(ValueError):
    pass


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if result.returncode:
        raise GuardError(f"git {' '.join(args[:2])}: {result.stderr.decode('utf-8', errors='replace').strip()}")
    return result.stdout


def repo_root(path: str | Path) -> Path:
    root = Path(path).resolve()
    actual = Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if root != actual:
        raise GuardError("--root must identify the repository root")
    return root


def policy_epoch(root: Path) -> str:
    digest = hashlib.sha256()
    for relative in CONTROL_PLANE:
        try:
            raw = (root / relative).read_bytes()
        except OSError as exc:
            raise GuardError(f"Missing control-plane file: {relative}") from exc
        digest.update(relative.encode("utf-8") + b"\0" + raw + b"\0")
    return digest.hexdigest()


def head(root: Path) -> str:
    return git(root, "rev-parse", "HEAD").decode().strip()


def verify_bootstrap(root: Path) -> dict:
    current = head(root)
    for relative in CONTROL_PLANE:
        path = root / relative
        if path.is_symlink() or path.resolve() != root / relative:
            raise GuardError(f"Control-plane symlink/junction is forbidden: {relative}")
        committed = git(root, "show", f"HEAD:{relative}")
        if path.read_bytes() != committed:
            raise GuardError(f"Control-plane bytes differ from HEAD: {relative}")
        if git(root, "status", "--porcelain", "--", relative).strip():
            raise GuardError(f"Control plane is not clean/committed: {relative}")
    return {"repo_head": current, "policy_epoch": policy_epoch(root), "bootstrap": "VERIFIED"}


def normalize_path(value: str, *, scope: bool = False) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise GuardError("Paths must be nonempty strings without NUL")
    value = value.replace("\\", "/")
    directory = scope and value.endswith("/")
    candidate = value[:-1] if directory else value
    if candidate.startswith("/") or re.match(r"^[A-Za-z]:", candidate):
        raise GuardError(f"Absolute paths are not scopes: {value}")
    parts = candidate.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise GuardError(f"Noncanonical or traversing path: {value}")
    if any(part.endswith((".", " ")) for part in parts):
        raise GuardError(f"Windows trailing-dot/space aliases are forbidden: {value}")
    if any(any(char in '<>:"|?*' or ord(char) < 32 for char in part) for part in parts):
        raise GuardError(f"Drive/alternate-stream or nonportable path is forbidden: {value}")
    reserved = {"con", "prn", "aux", "nul", "conin$", "conout$"}
    reserved.update(f"{kind}{digit}" for kind in ("com", "lpt") for digit in "123456789¹²³")
    if any(part.split(".")[0].casefold() in reserved for part in parts):
        raise GuardError(f"Windows device paths are forbidden: {value}")
    if PurePosixPath(candidate).is_absolute():
        raise GuardError(f"Absolute path: {value}")
    return candidate + ("/" if directory else "")


def contained(root: Path, value: str) -> tuple[str, str]:
    relative = normalize_path(value)
    path = root / relative
    try:
        resolved = path.resolve().relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError) as exc:
        raise GuardError(f"Path escapes repository or has a symlink cycle: {relative}") from exc
    if resolved == ".":
        raise GuardError("Repository-wide paths are forbidden")
    for candidate in (relative, resolved):
        if candidate.split("/")[0].casefold() == ".git":
            raise GuardError("Git internals are not task scope")
    return relative, resolved


def matches(relative: str, scope: str) -> bool:
    # The target workspace is Windows: protect case aliases on every host.
    relative, scope = relative.casefold(), scope.casefold()
    return relative.startswith(scope) if scope.endswith("/") else relative == scope


def scopes(data: dict, field: str) -> list[str]:
    values = data.get(field)
    if not isinstance(values, list) or (field == "allowed_write" and not values):
        raise GuardError(f"{field} must be a list of paths")
    normalized = [normalize_path(value, scope=True) for value in values]
    if len({value.casefold() for value in normalized}) != len(normalized):
        raise GuardError(f"Duplicate case aliases in {field}")
    return normalized


def read_json(path: Path) -> tuple[dict, bytes]:
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GuardError(f"Cannot read JSON: {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise GuardError(f"JSON must be an object: {path.name}")
    return data, raw


def ancestor(root: Path, older: str, newer: str) -> bool:
    result = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", older, newer], capture_output=True)
    return result.returncode == 0


def session(root: Path, envelope_path: Path, checkpoint_path: Path, task_id: str | None = None,
            *, allow_advanced_head: bool = False) -> tuple[dict, dict, dict]:
    state = verify_bootstrap(root)
    for path in (envelope_path, checkpoint_path):
        try:
            path.resolve().relative_to(root)
        except ValueError as exc:
            raise GuardError("Session artifacts must remain inside this repository") from exc
    envelope, raw = read_json(envelope_path)
    checkpoint, _ = read_json(checkpoint_path)
    identifier = envelope.get("task_id")
    if not isinstance(identifier, str) or not TASK_ID.fullmatch(identifier):
        raise GuardError("Invalid task_id")
    if task_id is not None and task_id != identifier:
        raise GuardError("Requested task_id differs from envelope")
    if checkpoint.get("task_id") != identifier:
        raise GuardError("Checkpoint task_id differs from envelope")
    baseline = envelope.get("baseline")
    if not isinstance(baseline, str) or not COMMIT.fullmatch(baseline):
        raise GuardError("Envelope baseline must be an immutable full commit SHA")
    if not ancestor(root, baseline, state["repo_head"]):
        raise GuardError("Envelope baseline is not an ancestor of current HEAD")
    for document in (envelope, checkpoint):
        epoch = document.get("policy_epoch")
        if not isinstance(epoch, str) or not SHA256.fullmatch(epoch) or epoch != state["policy_epoch"]:
            raise GuardError("Policy epoch mismatch; reread control plane and renew authorized state")
    if checkpoint.get("envelope_sha256") != hashlib.sha256(raw).hexdigest():
        raise GuardError("Envelope raw-byte SHA differs from checkpoint")
    sequence = checkpoint.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise GuardError("Checkpoint sequence must be a nonnegative integer")
    previous_head = checkpoint.get("repo_head")
    if not isinstance(previous_head, str) or not COMMIT.fullmatch(previous_head):
        raise GuardError("Checkpoint repo_head must be a full commit SHA")
    if previous_head != state["repo_head"]:
        if not allow_advanced_head or not ancestor(root, previous_head, state["repo_head"]):
            raise GuardError("Checkpoint HEAD differs from current HEAD; orchestrator snapshot required")
    scopes(envelope, "allowed_write")
    protected = scopes(envelope, "protected")
    if not all(any(matches(path, item) for item in protected) for path in CONTROL_PLANE):
        raise GuardError("Envelope must protect all control-plane files")
    owners = envelope.get("scope_owners", {})
    if not isinstance(owners, dict):
        raise GuardError("scope_owners must be an object")
    for owner, values in owners.items():
        if not isinstance(owner, str) or not owner:
            raise GuardError("Invalid scope owner")
        scopes({"allowed_write": values}, "allowed_write")
    state.update(task_id=identifier, envelope_sha256=hashlib.sha256(raw).hexdigest(), sequence=sequence)
    return envelope, checkpoint, state


def authorize(root: Path, envelope: dict, paths: list[str], owner: str | None = None) -> list[str]:
    allowed, protected = scopes(envelope, "allowed_write"), scopes(envelope, "protected")
    owned = None
    if owner is not None:
        owners = envelope.get("scope_owners", {})
        if owner not in owners:
            raise GuardError(f"Unknown scope owner: {owner}")
        owned = scopes({"allowed_write": owners[owner]}, "allowed_write")
    if not paths:
        raise GuardError("An action needs exact repository-relative paths")
    result = []
    for value in paths:
        relative, resolved = contained(root, value)
        for candidate in (relative, resolved):
            if any(matches(candidate, item) for item in protected):
                raise GuardError(f"Protected path: {relative}")
            if not any(matches(candidate, item) for item in allowed):
                raise GuardError(f"Path outside allowed_write: {relative}")
            if owned is not None and not any(matches(candidate, item) for item in owned):
                raise GuardError(f"Path outside owner scope ({owner}): {relative}")
        result.append(relative)
    if len({item.casefold() for item in result}) != len(result):
        raise GuardError("Action paths contain duplicate case aliases")
    return result
