# SPDX-License-Identifier: Apache-2.0
"""Freeze a public text manifest and build a byte-reproducible portable ZIP.

Run ``python -B tools/release.py --output .agent-state/release/package.zip``
with an existing output directory, or supply an explicit existing --workspace.
The first build creates reports/FILE_MANIFEST.json exclusively. Later builds
and --check require that frozen file to match the current public membership.
An intentional new release needs a separately reviewed new manifest baseline.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from universal_diascreen_hmi.errors import AgentError


ROOT_FILES = ("AGENTS.md", "SYSTEM_PROMPT.md", "INDEX.md", "README.md",
              "LICENSE", "NOTICE.md", "pyproject.toml", "SOURCE_MANIFEST.json",
              "INTEGRATION.json")
PUBLIC_DIRS = ("src", "docs", "tests", "profiles", "examples", "tools", "reports")
TEXT_SUFFIXES = frozenset((".py", ".md", ".json"))
EXCLUDED_DIRS = frozenset((".agent-state", ".git", ".venv", "venv", "__pycache__",
                           ".pytest_cache"))
MANIFEST_NAME = "reports/FILE_MANIFEST.json"
CYCLE_EXCLUSIONS = frozenset((MANIFEST_NAME, "reports/RELEASE.json"))
FIXED_WINDOWS_PATH = re.compile(r"[A-Za-z]:[\\/]")
UNC_PATH = re.compile(r"(?<![\w" + ":/])" + "/{2,}" + r'''[^/\s"'<>]+/[^/\s"'<>]+''')
HTTP_PROTOCOL = re.compile(r"https?://", re.IGNORECASE)
WINDOWS_RESERVED = frozenset(("con", "prn", "aux", "nul", "clock$", "conin$", "conout$",
                             *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))))
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
ZIP_MODE = (stat.S_IFREG | 0o644) << 16


def require(condition, code, message):
    if not condition:
        raise AgentError(code, message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _plain(path):
    """Reject symlinks and Windows junction/reparse points without following."""
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode)
            and not getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
            "RELEASE_SYMLINK", "Public paths and output ancestors must not be links")
    return info


def _ancestors_plain(path):
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            _plain(item)


def _relative_name(name):
    require(isinstance(name, str) and name and "\\" not in name and ":" not in name
            and all(ord(c) >= 32 for c in name), "RELEASE_MANIFEST", "Invalid portable member name")
    p = PurePosixPath(name)
    require(not p.is_absolute() and str(p) == name and all(x not in (".", "..", "") for x in p.parts),
            "RELEASE_MANIFEST", "Invalid portable member name")
    require(all(not any(c in part for c in '<>"|?*') and part == part.rstrip(" .")
                and not any(piece.endswith(" ") for piece in part.split("."))
                and part.split(".")[0].casefold() not in WINDOWS_RESERVED for part in p.parts),
            "RELEASE_MANIFEST", "Member name is not portable to Windows")
    return p


def _selected_name(name):
    p = _relative_name(name)
    return name in ROOT_FILES or (len(p.parts) > 1 and p.parts[0] in PUBLIC_DIRS
            and not any(x.casefold() in EXCLUDED_DIRS for x in p.parts[:-1])
            and p.suffix in TEXT_SUFFIXES and name not in CYCLE_EXCLUSIONS)


def check_text(data, markers=()):
    require(b"\0" not in data, "RELEASE_BINARY", "Only public UTF-8 text may be released")
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        raise AgentError("RELEASE_BINARY", "Only public UTF-8 text may be released") from None
    location_text = HTTP_PROTOCOL.sub("", text)
    require(not FIXED_WINDOWS_PATH.search(location_text)
            and not UNC_PATH.search(location_text.replace(chr(92), "/")),
            "RELEASE_PRIVACY", "Fixed computer paths are forbidden")
    folded = text.casefold()
    require(not any(marker.casefold() in folded for marker in markers),
            "RELEASE_PRIVACY", "A caller-supplied private marker was found")


def collect_public(root, markers=()):
    """Read a strict allowlist snapshot; never read or rewrite private assets."""
    root = Path(os.path.abspath(root))
    _ancestors_plain(root)
    require(root.is_dir(), "RELEASE_ROOT", "A public source directory is required")
    files = {}

    def add(path):
        info = _plain(path)
        require(stat.S_ISREG(info.st_mode), "RELEASE_FILE", "Public members must be regular files")
        name = path.relative_to(root).as_posix()
        require(_selected_name(name), "RELEASE_EXTENSION", "Unexpected file in a public directory")
        data = path.read_bytes()
        check_text(data, markers)
        files[name] = data

    def walk(directory):
        require(stat.S_ISDIR(_plain(directory).st_mode), "RELEASE_FILE", "Public roots must be directories")
        for path in sorted(directory.iterdir(), key=lambda p: p.name):
            name = path.relative_to(root).as_posix()
            if path.name.casefold() in EXCLUDED_DIRS:
                continue
            info = _plain(path)
            if stat.S_ISDIR(info.st_mode):
                walk(path)
            elif name not in CYCLE_EXCLUSIONS:
                add(path)

    for name in ROOT_FILES:
        require((root / name).exists(), "RELEASE_MISSING", "A required public root file is missing")
        add(root / name)
    for name in PUBLIC_DIRS:
        require((root / name).exists(), "RELEASE_MISSING", "A required public directory is missing")
        walk(root / name)
    names = list(files)
    require(len({name.casefold() for name in names}) == len(names),
            "RELEASE_COLLISION", "Public member names must be portable across case-insensitive systems")
    return dict(sorted(files.items()))


def make_manifest(files):
    return {"schema_version": 1, "entries": [
        {"path": name, "size": len(data), "sha256": sha256(data)} for name, data in sorted(files.items())]}


def parse_manifest(data):
    check_text(data)
    try:
        manifest = json.loads(data)
    except (ValueError, UnicodeError):
        raise AgentError("RELEASE_MANIFEST", "Invalid public file manifest") from None
    require(type(manifest) is dict and set(manifest) == {"schema_version", "entries"}
            and type(manifest["schema_version"]) is int and manifest["schema_version"] == 1
            and type(manifest["entries"]) is list,
            "RELEASE_MANIFEST", "Unsupported public file manifest")
    names = []
    for row in manifest["entries"]:
        require(type(row) is dict and set(row) == {"path", "size", "sha256"},
                "RELEASE_MANIFEST", "Invalid file manifest entry")
        require(_selected_name(row["path"]) and type(row["size"]) is int and row["size"] >= 0
                and isinstance(row["sha256"], str) and SHA256.fullmatch(row["sha256"]),
                "RELEASE_MANIFEST", "Invalid file manifest entry")
        names.append(row["path"])
    require(names == sorted(names) and len(set(n.casefold() for n in names)) == len(names)
            and set(ROOT_FILES) <= set(names)
            and data == canonical(manifest), "RELEASE_MANIFEST", "Manifest must be unique, sorted and canonical")
    return manifest


def check_manifest(root, markers=()):
    root = Path(root)
    path = root / MANIFEST_NAME
    require(path.exists(), "RELEASE_MANIFEST_MISSING", "Freeze a public manifest before checking")
    _ancestors_plain(path)
    data = path.read_bytes()
    check_text(data, markers)
    manifest = parse_manifest(data)
    files = collect_public(root, markers)
    require(manifest == make_manifest(files), "RELEASE_DRIFT", "Public membership or file bytes changed since freeze")
    return files, data


def _freeze(root, files, markers):
    path = Path(root) / MANIFEST_NAME
    _ancestors_plain(path.parent)
    data = canonical(make_manifest(files))
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError:
        current, data = check_manifest(root, markers)
        require(current == files, "RELEASE_DRIFT", "Public files changed during release freeze")
    return data


def load_markers(path, root):
    if path is None:
        return ()
    path = Path(os.path.abspath(path))
    _ancestors_plain(path)
    require(path.is_file(), "RELEASE_MARKERS", "A private marker text file is required")
    root = Path(root).resolve()
    try:
        name = path.relative_to(root).as_posix()
    except ValueError:
        name = None
    if name is not None:
        p = PurePosixPath(name)
        # A local marker list belongs only in an ignored private directory.
        require(p.parts[0] in (".agent-state", "private"), "RELEASE_MARKERS",
                "Private marker input must be outside the public payload")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError:
        raise AgentError("RELEASE_MARKERS", "Private markers must be UTF-8 text") from None
    require("\0" not in text, "RELEASE_MARKERS", "Private markers must be UTF-8 text")
    return tuple(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))


def output_path(root, output, workspace=None):
    root = Path(os.path.abspath(root))
    boundary = Path(os.path.abspath(workspace)) if workspace is not None else root / ".agent-state"
    target = Path(output)
    if not target.is_absolute():
        target = root / target
    target = Path(os.path.abspath(target))
    _ancestors_plain(boundary)
    _ancestors_plain(target)
    require(boundary.is_dir() and target.parent.is_dir(), "RELEASE_OUTPUT", "Existing output workspace and parent are required")
    require(target != boundary and target.is_relative_to(boundary), "RELEASE_OUTPUT", "Archive must remain inside its output workspace")
    require(target.suffix == ".zip" and not target.exists(), "RELEASE_OUTPUT", "A new ZIP output is required")
    require(not any(target.is_relative_to(root / name) for name in PUBLIC_DIRS)
            and target not in (root / name for name in ROOT_FILES),
            "RELEASE_OUTPUT", "Archive must stay outside the public file tree")
    return target


def _zip_bytes(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo(name, ZIP_DATE)
            info.create_system = 3
            info.external_attr = ZIP_MODE
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, data)
    return stream.getvalue()


def validate_archive(path, manifest_data, markers=()):
    """Validate every member against an independently supplied frozen manifest."""
    manifest = parse_manifest(manifest_data)
    check_text(manifest_data, markers)
    expected = {row["path"]: row for row in manifest["entries"]}
    expected[MANIFEST_NAME] = {"size": len(manifest_data), "sha256": sha256(manifest_data)}
    raw = Path(path).read_bytes()
    verified = {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            require(len(names) == len(set(names)) and set(names) == set(expected),
                    "RELEASE_ARCHIVE", "Archive membership does not match its frozen manifest")
            require(names == sorted(names) and archive.comment == b"", "RELEASE_ARCHIVE", "Archive metadata is not deterministic")
            for info in infos:
                _relative_name(info.filename)
                row = expected[info.filename]
                require(info.file_size == row["size"] and not info.is_dir()
                        and info.compress_type == zipfile.ZIP_STORED and info.date_time == ZIP_DATE
                        and info.create_system == 3 and info.external_attr == ZIP_MODE
                        and not info.extra and not info.comment and not info.flag_bits & 1,
                        "RELEASE_ARCHIVE", "Archive member metadata does not match release policy")
                data = archive.read(info)
                require(sha256(data) == row["sha256"], "RELEASE_ARCHIVE", "Archive member bytes do not match manifest")
                check_text(data, markers)
                verified[info.filename] = data
    except (zipfile.BadZipFile, RuntimeError, EOFError, NotImplementedError):
        raise AgentError("RELEASE_ARCHIVE", "Unreadable or unsupported release archive") from None
    require(raw == _zip_bytes(verified), "RELEASE_ARCHIVE", "Archive contains noncanonical or unreferenced bytes")
    return {"status": "VERIFIED", "files": len(expected)}


def build_release(root, output, *, workspace=None, markers=()):
    target = output_path(root, output, workspace)
    files = collect_public(root, markers)
    manifest_data = _freeze(root, files, markers)
    members = dict(files, **{MANIFEST_NAME: manifest_data})
    created_identity = None
    try:
        with target.open("xb") as stream:
            info = os.fstat(stream.fileno())
            created_identity = (info.st_dev, info.st_ino)
            stream.write(_zip_bytes(members))
        current, frozen = check_manifest(root, markers)
        require(current == files and frozen == manifest_data, "RELEASE_DRIFT", "Public files changed while packaging")
        validate_archive(target, manifest_data, markers)
        return {"status": "VERIFIED", "archive_sha256": sha256(target.read_bytes()),
                "files": len(members), "manifest_sha256": sha256(manifest_data)}
    except BaseException:
        if created_identity is not None and target.exists() and not target.is_symlink():
            info = target.lstat()
            if (info.st_dev, info.st_ino) == created_identity:
                target.unlink()
        raise


class PublicArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise AgentError("RELEASE_ARGUMENTS", "Invalid release arguments")


def main(argv=None):
    parser = PublicArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--output", help="New ZIP output inside the selected workspace")
    choice.add_argument("--check", action="store_true", help="Check the frozen public manifest without writing")
    parser.add_argument("--workspace", help="Explicit existing caller-owned output workspace")
    parser.add_argument("--private-markers", help="Optional ignored local UTF-8 private marker list")
    try:
        args = parser.parse_args(argv)
        markers = load_markers(args.private_markers, ROOT)
        if args.check:
            files, manifest = check_manifest(ROOT, markers)
            result = {"status": "VERIFIED", "files": len(files) + 1, "manifest_sha256": sha256(manifest)}
        else:
            result = build_release(ROOT, args.output, workspace=args.workspace, markers=markers)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (AgentError, OSError) as error:
        # Public diagnostics contain no caller location, marker, or source text.
        code = error.code if isinstance(error, AgentError) else "RELEASE_IO"
        print(json.dumps({"status": "STOP", "code": code}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
