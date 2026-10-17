"""Trusted, portable launch configuration; never accepted from tool arguments."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re


FAMILIES = {"dop_b": "delta_dopsoft2", "dop_100": "diascreen-dop100"}
PACKAGES = {"dop_b": "universal_hmi", "dop_100": "universal_diascreen_hmi"}


class ConfigurationError(ValueError):
    pass


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ConfigurationError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ConfigurationError("JSON exceeds 8 MiB")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)


def no_links(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ConfigurationError("Links/junctions are not allowed: " + str(part))
    return path.resolve(strict=True)


def relative_name(value):
    """Validate a canonical manifest name without touching the filesystem."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ConfigurationError("Expected a portable relative path")
    candidate = Path(value)
    win = PureWindowsPath(value)
    if candidate.is_absolute() or win.drive or any(p in ("..", ".") for p in value.split("/")):
        raise ConfigurationError("Absolute paths and traversal are forbidden")
    if any(":" in p or p.endswith((" ", ".")) or not p for p in value.split("/")):
        raise ConfigurationError("Nonportable path")
    return candidate.as_posix()


def relative_path(base, value):
    candidate = Path(relative_name(value))
    result = no_links(base / candidate)
    if not result.is_relative_to(base):
        raise ConfigurationError("Path escapes configuration root")
    return result


def tree_files(root):
    root = no_links(root)
    result = {}
    def visit(directory):
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                junction = entry.is_junction() if hasattr(entry, "is_junction") else (hasattr(path, "is_junction") and path.is_junction())
                if entry.is_symlink() or junction:
                    raise ConfigurationError("Links/junctions are not allowed: " + str(path))
                if entry.is_dir(follow_symlinks=False):
                    visit(path)
                elif entry.is_file(follow_symlinks=False):
                    result[path.relative_to(root).as_posix()] = sha256(path)
                else:
                    raise ConfigurationError("Special filesystem entries are not allowed")
    visit(root)
    return dict(sorted(result.items()))


def tree_sha256(root):
    value = hashlib.sha256()
    for name, digest in tree_files(root).items():
        value.update(name.encode("utf-8") + b"\0" + digest.encode("ascii") + b"\0")
    return value.hexdigest()


def _digest(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ConfigurationError("Expected lowercase SHA-256")
    return value


@dataclass(frozen=True)
class BackendConfig:
    family: str
    enabled: bool
    reason: str = ""
    root: Path | None = None
    python: Path | None = None
    python_sha256: str = ""
    workspace: Path | None = None
    profiles: Path | None = None
    state: Path | None = None
    source_manifest: Path | None = None
    source_manifest_sha256: str = ""
    profiles_sha256: str = ""
    allow_write: bool = False
    job_policy: Path | None = None
    job_policy_sha256: str = ""

    def verify_job_policy(self):
        if self.family != "dop_b" or self.job_policy is None:
            raise ConfigurationError("Persistent jobs require a separately pinned trusted DOP-B job policy")
        no_links(self.job_policy)
        if sha256(self.job_policy) != self.job_policy_sha256:
            raise ConfigurationError("Trusted job policy changed")
        data = read_json(self.job_policy)
        if not isinstance(data, dict):
            raise ConfigurationError("Trusted job policy must be an object")
        for key, wanted in (("workspace", self.workspace), ("profiles_root", self.profiles)):
            if not isinstance(data.get(key), str) or not Path(data[key]).is_absolute() or no_links(data[key]) != wanted:
                raise ConfigurationError("Job policy roots do not match the configured backend")
        for key in ("output_root", "reviews_root"):
            if not isinstance(data.get(key), str) or not Path(data[key]).is_absolute() or not no_links(data[key]).is_dir():
                raise ConfigurationError("Job policy requires existing explicit output/review roots")
        return data

    def verify(self):
        if not self.enabled:
            raise ConfigurationError("Backend unavailable: " + self.reason)
        for path in (self.root, self.python, self.workspace, self.profiles, self.state, self.source_manifest):
            no_links(path)
        if sha256(self.python) != self.python_sha256:
            raise ConfigurationError("Python executable hash changed")
        if sha256(self.source_manifest) != self.source_manifest_sha256:
            raise ConfigurationError("Backend source manifest changed")
        manifest = read_json(self.source_manifest)
        if not isinstance(manifest, dict) or set(manifest) != {"files", "package_prefix", "import_roots"}:
            raise ConfigurationError("Invalid source manifest schema")
        package = relative_path(self.root, manifest["package_prefix"])
        if not package.is_dir() or package.name != PACKAGES[self.family]:
            raise ConfigurationError("Manifest must identify the installed family-specific package")
        raw_roots = manifest["import_roots"]
        if not isinstance(raw_roots, list) or not raw_roots:
            raise ConfigurationError("Manifest requires the complete isolated Python import roots")
        import_roots = []
        for name in raw_roots:
            directory = relative_path(self.root, name)
            if not directory.is_dir() or any(directory.is_relative_to(other) or other.is_relative_to(directory) for other in import_roots):
                raise ConfigurationError("Import roots must be disjoint directories")
            import_roots.append(directory)
        def covered(path):
            return any(path.is_relative_to(directory) for directory in import_roots)
        if not covered(package) or not covered(self.python):
            raise ConfigurationError("Import inventory must cover the Python executable and backend package")
        # Python's venv redirect can import a base stdlib outside site-packages.
        # Cover the redirect itself and its target before launching the interpreter.
        for candidate in (self.python.parent / "pyvenv.cfg", self.python.parent.parent / "pyvenv.cfg"):
            if candidate.exists():
                candidate = no_links(candidate)
                if not covered(candidate):
                    raise ConfigurationError("Unpinned Python venv configuration")
                homes = [line.split("=", 1)[1].strip() for line in candidate.read_text(encoding="utf8").splitlines() if "=" in line and line.split("=", 1)[0].strip().lower() == "home"]
                if len(homes) != 1:
                    raise ConfigurationError("Python venv must identify exactly one base home")
                home = Path(homes[0])
                home = no_links(home if home.is_absolute() else candidate.parent / home)
                if not home.is_relative_to(self.root) or not covered(home):
                    raise ConfigurationError("Python base home escapes pinned import roots")
        expected = {}
        if not isinstance(manifest["files"], list) or not manifest["files"]:
            raise ConfigurationError("Source manifest is empty")
        for item in manifest["files"]:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                raise ConfigurationError("Invalid manifest entry")
            # The exact filesystem inventory below verifies existence, file type,
            # all parent directories and links once. Do not resolve every ancestor
            # for every manifest entry (thousands of repeated metadata requests).
            key = relative_name(item["path"])
            if key in expected:
                raise ConfigurationError("Duplicate manifest entry")
            expected[key] = _digest(item["sha256"])
        actual = {}
        for directory in import_roots:
            prefix = directory.relative_to(self.root).as_posix() + "/"
            actual.update({prefix + key: value for key, value in tree_files(directory).items()})
        if actual != expected:
            raise ConfigurationError("Python import inventory changed (including bytecode, hooks and native dependencies)")
        if tree_sha256(self.profiles) != self.profiles_sha256:
            raise ConfigurationError("Profile registry changed")
        profiles = list(self.profiles.glob("*.json"))
        if not profiles:
            raise ConfigurationError("Profile registry is empty")
        for path in profiles:
            data = read_json(path)
            if not isinstance(data, dict) or data.get("family") != FAMILIES[self.family]:
                raise ConfigurationError("Mixed or invalid profile family: " + path.name)

    def profile(self, identifier):
        if not isinstance(identifier, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", identifier) is None:
            raise ConfigurationError("Invalid profile identifier")
        path = relative_path(self.profiles, identifier + ".json")
        data = read_json(path)
        if data.get("family") != FAMILIES[self.family]:
            raise ConfigurationError("Wrong family for selected route")
        return data


@dataclass(frozen=True)
class GatewayConfig:
    backends: dict[str, BackendConfig]

    @classmethod
    def load(cls, path):
        path = no_links(path)
        data = read_json(path)
        if not isinstance(data, dict) or set(data) != {"schema_version", "backends"} or type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ConfigurationError("Unsupported gateway configuration schema")
        if not isinstance(data["backends"], dict) or set(data["backends"]) != set(FAMILIES):
            raise ConfigurationError("Both family entries must be explicit")
        result, roots = {}, []
        for family, item in data["backends"].items():
            if not isinstance(item, dict) or type(item.get("enabled")) is not bool:
                raise ConfigurationError("enabled must be a boolean")
            if not item["enabled"]:
                if set(item) != {"enabled", "reason"} or not isinstance(item["reason"], str) or not item["reason"].strip():
                    raise ConfigurationError("Disabled backend requires a reason")
                result[family] = BackendConfig(family, False, reason=item["reason"])
                continue
            fields = {"enabled", "root", "python", "python_sha256", "workspace", "profiles", "state", "source_manifest", "source_manifest_sha256", "profiles_sha256"}
            optional = {"allow_write"} if family == "dop_100" else {"job_policy", "job_policy_sha256"}
            if not fields.issubset(item) or set(item) - fields - optional:
                raise ConfigurationError("Unknown or missing backend configuration fields")
            args = {key: relative_path(path.parent, item[key]) for key in ("root", "python", "workspace", "profiles", "state", "source_manifest")}
            args.update({key: _digest(item[key]) for key in ("python_sha256", "source_manifest_sha256", "profiles_sha256")})
            if family == "dop_100":
                if type(item.get("allow_write", False)) is not bool:
                    raise ConfigurationError("allow_write must be a trusted boolean")
                args["allow_write"] = item.get("allow_write", False)
            if family == "dop_b" and ("job_policy" in item or "job_policy_sha256" in item):
                if not {"job_policy", "job_policy_sha256"}.issubset(item):
                    raise ConfigurationError("Job policy path and SHA must be supplied together")
                args["job_policy"] = relative_path(path.parent, item["job_policy"])
                args["job_policy_sha256"] = _digest(item["job_policy_sha256"])
            backend = BackendConfig(family, True, **args)
            if not backend.python.is_relative_to(backend.root) or not backend.python.is_file():
                raise ConfigurationError("Python must be a file inside this backend root")
            if backend.source_manifest.is_relative_to(backend.root):
                raise ConfigurationError("Manifest must be outside the pinned backend root")
            for key in ("root", "workspace", "profiles", "state"):
                value = getattr(backend, key)
                if not value.is_dir():
                    raise ConfigurationError("Expected directory: " + key)
                for other in roots:
                    if value.is_relative_to(other) or other.is_relative_to(value):
                        raise ConfigurationError("Backend roots overlap")
                roots.append(value)
            result[family] = backend
        # Trusted configuration and pins cannot live in any mutable workspace/state.
        for backend in result.values():
            if not backend.enabled:
                continue
            for other in result.values():
                if other.enabled:
                    for mutable in (other.workspace, other.state):
                        authority = [path, backend.source_manifest] + ([backend.job_policy] if backend.job_policy is not None else [])
                        if any(item.is_relative_to(mutable) for item in authority):
                            raise ConfigurationError("Authority files overlap mutable state")
        config = cls(result)
        if result["dop_b"].job_policy is not None:
            config.verify_jobs()
        return config

    def verify_jobs(self):
        backend = self.backends["dop_b"]
        data = backend.verify_job_policy()
        extras = [no_links(data[key]) for key in ("output_root", "reviews_root")]
        occupied = [getattr(cfg, key) for cfg in self.backends.values() if cfg.enabled for key in ("root", "workspace", "profiles", "state")]
        for extra in extras:
            if any(extra.is_relative_to(other) or other.is_relative_to(extra) for other in occupied):
                raise ConfigurationError("Job output/review roots overlap another protected backend root")
            occupied.append(extra)
        for cfg in self.backends.values():
            if cfg.enabled:
                for authority in (cfg.source_manifest, backend.job_policy):
                    if any(authority.is_relative_to(extra) for extra in extras):
                        raise ConfigurationError("Job output/review roots contain trusted authority")
        return data
