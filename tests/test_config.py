import copy
import json
from pathlib import Path
import tempfile
import unittest

from delta_hmi.config import ConfigurationError, GatewayConfig, PACKAGES, read_json, sha256, tree_files, tree_sha256


def make_config(base, families=("dop_b", "dop_100")):
    entries = {}
    for family in ("dop_b", "dop_100"):
        if family not in families:
            entries[family] = {"enabled": False, "reason": "No qualified backend installed"}
            continue
        root = base / family / "backend"
        package = root / "runtime" / "site-packages" / PACKAGES[family]
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("# fixture\n", encoding="utf8")
        python = root / "runtime/python"
        python.write_bytes(b"fixture interpreter")
        for kind in ("workspace", "profiles", "state"):
            (base / family / kind).mkdir()
        (base / family / "profiles" / "sample.json").write_text(json.dumps({"id": "sample", "family": {"dop_b": "delta_dopsoft2", "dop_100": "delta_diascreen"}[family]}), encoding="utf8")
        manifest = base / family / "source.json"
        manifest.write_text(json.dumps({"package_prefix": "runtime/site-packages/" + PACKAGES[family], "import_roots": ["runtime"], "files": [{"path": "runtime/" + name, "sha256": digest} for name, digest in tree_files(root / "runtime").items()]}), encoding="utf8")
        entries[family] = {"enabled": True, "root": f"{family}/backend", "python": f"{family}/backend/runtime/python", "python_sha256": sha256(python), "workspace": f"{family}/workspace", "profiles": f"{family}/profiles", "state": f"{family}/state", "source_manifest": f"{family}/source.json", "source_manifest_sha256": sha256(manifest), "profiles_sha256": tree_sha256(base / family / "profiles")}
    data = {"schema_version": 1, "backends": entries}
    path = base / "config.json"
    path.write_text(json.dumps(data), encoding="utf8")
    return path, data


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.path, self.data = make_config(self.base)

    def write(self):
        self.path.write_text(json.dumps(self.data), encoding="utf8")

    def test_separate_profiles_verify(self):
        config = GatewayConfig.load(self.path)
        for backend in config.backends.values():
            backend.verify()
            self.assertEqual(backend.profile("sample")["id"], "sample")

    def test_disabled_explicit(self):
        self.data["backends"]["dop_100"] = {"enabled": False, "reason": "Unavailable"}
        self.write()
        config = GatewayConfig.load(self.path)
        self.assertFalse(config.backends["dop_100"].enabled)

    def test_changed_source(self):
        config = GatewayConfig.load(self.path)
        (config.backends["dop_b"].root / "runtime/site-packages/universal_hmi/__init__.py").write_text("changed")
        with self.assertRaises(ConfigurationError):
            config.backends["dop_b"].verify()

    def test_added_source(self):
        config = GatewayConfig.load(self.path)
        (config.backends["dop_b"].root / "runtime/site-packages/universal_hmi/inject.py").write_text("pass")
        with self.assertRaises(ConfigurationError):
            config.backends["dop_b"].verify()

    def test_same_source_size_and_mtime_poisoned_pyc_rejected(self):
        import importlib.util
        import marshal
        import struct
        config = GatewayConfig.load(self.path)
        cfg = config.backends["dop_b"]
        source = cfg.root / "runtime/site-packages/universal_hmi/__init__.py"
        pyc = Path(importlib.util.cache_from_source(str(source)))
        pyc.parent.mkdir()
        source_stat = source.stat()
        code = compile("raise RuntimeError('poisoned bytecode')", str(source), "exec")
        pyc.write_bytes(importlib.util.MAGIC_NUMBER + struct.pack("<III", 0, int(source_stat.st_mtime), source_stat.st_size) + marshal.dumps(code))
        self.assertEqual(source.stat().st_size, source_stat.st_size)
        self.assertEqual(source.stat().st_mtime_ns, source_stat.st_mtime_ns)
        with self.assertRaisesRegex(ConfigurationError, "import inventory"):
            cfg.verify()

    def test_sitecustomize_pth_and_dependency_injection_rejected(self):
        cfg = GatewayConfig.load(self.path).backends["dop_b"]
        for name in ("sitecustomize.py", "extra.pth", "dependency.pyd", "stdlib.py"):
            with self.subTest(name=name):
                path = cfg.root / "runtime/site-packages" / name
                path.write_text("# foreign import hook", encoding="utf8")
                with self.assertRaisesRegex(ConfigurationError, "import inventory"):
                    cfg.verify()
                path.unlink()
        cfg.verify()

    def test_existing_bytecode_pinned_and_modified_bytecode_rejected(self):
        cfg = GatewayConfig.load(self.path).backends["dop_b"]
        pyc = cfg.root / "runtime/site-packages/universal_hmi/__pycache__/example.pyc"
        pyc.parent.mkdir()
        pyc.write_bytes(b"original")
        manifest = read_json(cfg.source_manifest)
        manifest["files"].append({"path": pyc.relative_to(cfg.root).as_posix(), "sha256": sha256(pyc)})
        cfg.source_manifest.write_text(json.dumps(manifest))
        self.data["backends"]["dop_b"]["source_manifest_sha256"] = sha256(cfg.source_manifest)
        self.write()
        cfg = GatewayConfig.load(self.path).backends["dop_b"]
        cfg.verify()
        pyc.write_bytes(b"modified")
        with self.assertRaisesRegex(ConfigurationError, "import inventory"):
            cfg.verify()

    def test_import_roots_cannot_omit_interpreter_or_overlap(self):
        cfg = GatewayConfig.load(self.path).backends["dop_b"]
        manifest = read_json(cfg.source_manifest)
        for roots in (["runtime/site-packages"], ["runtime", "runtime/site-packages"]):
            with self.subTest(roots=roots):
                manifest["import_roots"] = roots
                cfg.source_manifest.write_text(json.dumps(manifest))
                self.data["backends"]["dop_b"]["source_manifest_sha256"] = sha256(cfg.source_manifest)
                self.write()
                with self.assertRaises(ConfigurationError):
                    GatewayConfig.load(self.path).backends["dop_b"].verify()

    def test_manifest_traversal_absolute_stream_and_noncanonical_names_rejected(self):
        cfg = GatewayConfig.load(self.path).backends["dop_b"]
        baseline = read_json(cfg.source_manifest)
        for name in ("../outside", "runtime/../python", "runtime//python", "runtime/./python", "/absolute", "C:/absolute", "runtime\\python", "runtime/python:stream"):
            with self.subTest(name=name):
                manifest = copy.deepcopy(baseline)
                manifest["files"][0]["path"] = name
                cfg.source_manifest.write_text(json.dumps(manifest))
                self.data["backends"]["dop_b"]["source_manifest_sha256"] = sha256(cfg.source_manifest)
                self.write()
                with self.assertRaises(ConfigurationError):
                    GatewayConfig.load(self.path).backends["dop_b"].verify()

    def test_manifest_nonfile_and_outside_import_root_rejected(self):
        cfg = GatewayConfig.load(self.path).backends["dop_b"]
        baseline = read_json(cfg.source_manifest)
        for name in ("runtime/site-packages", "runtime/missing.py", "outside_import.py"):
            with self.subTest(name=name):
                manifest = copy.deepcopy(baseline)
                manifest["files"].append({"path": name, "sha256": "0" * 64})
                cfg.source_manifest.write_text(json.dumps(manifest))
                self.data["backends"]["dop_b"]["source_manifest_sha256"] = sha256(cfg.source_manifest)
                self.write()
                with self.assertRaisesRegex(ConfigurationError, "import inventory"):
                    GatewayConfig.load(self.path).backends["dop_b"].verify()

    def test_pinned_venv_cannot_redirect_to_external_base(self):
        cfg = GatewayConfig.load(self.path).backends["dop_b"]
        redirect = cfg.root / "runtime/pyvenv.cfg"
        redirect.write_text("home = " + str(self.base))
        manifest = read_json(cfg.source_manifest)
        manifest["files"].append({"path": "runtime/pyvenv.cfg", "sha256": sha256(redirect)})
        cfg.source_manifest.write_text(json.dumps(manifest))
        self.data["backends"]["dop_b"]["source_manifest_sha256"] = sha256(cfg.source_manifest)
        self.write()
        with self.assertRaisesRegex(ConfigurationError, "base home"):
            GatewayConfig.load(self.path).backends["dop_b"].verify()

    def test_python_changed(self):
        config = GatewayConfig.load(self.path)
        config.backends["dop_b"].python.write_bytes(b"different")
        with self.assertRaises(ConfigurationError):
            config.backends["dop_b"].verify()

    def test_profile_changed(self):
        config = GatewayConfig.load(self.path)
        (config.backends["dop_b"].profiles / "sample.json").write_text("{}")
        with self.assertRaises(ConfigurationError):
            config.backends["dop_b"].verify()

    def test_mixed_profile_even_when_pinned(self):
        path = self.base / "dop_b/profiles/other.json"
        path.write_text(json.dumps({"family": "delta_diascreen"}))
        self.data["backends"]["dop_b"]["profiles_sha256"] = tree_sha256(path.parent)
        self.write()
        with self.assertRaises(ConfigurationError):
            GatewayConfig.load(self.path).backends["dop_b"].verify()

    def test_shared_and_nested_roots_rejected(self):
        for field, value in (("workspace", "dop_b/workspace"), ("state", "dop_b/backend/runtime")):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data["backends"]["dop_100"][field] = value
                self.path.write_text(json.dumps(data))
                with self.assertRaises(ConfigurationError):
                    GatewayConfig.load(self.path)

    def test_portable_paths_and_fixed_schema(self):
        for value in ("../dop_b/backend", "C:/arbitrary", "/absolute", "dop_b\\backend", "dop_b/backend:stream"):
            with self.subTest(value=value):
                data = copy.deepcopy(self.data)
                data["backends"]["dop_b"]["root"] = value
                self.path.write_text(json.dumps(data))
                with self.assertRaises((ConfigurationError, FileNotFoundError)):
                    GatewayConfig.load(self.path)
        self.data["backends"]["dop_b"]["command"] = "arbitrary"
        self.write()
        with self.assertRaises(ConfigurationError):
            GatewayConfig.load(self.path)

    def test_manifest_authority_mutable_rejected(self):
        destination = self.base / "dop_b/workspace/source.json"
        destination.write_bytes((self.base / "dop_b/source.json").read_bytes())
        self.data["backends"]["dop_b"]["source_manifest"] = "dop_b/workspace/source.json"
        self.write()
        with self.assertRaises(ConfigurationError):
            GatewayConfig.load(self.path)

    def test_duplicate_keys_rejected(self):
        self.path.write_text('{"schema_version":1,"schema_version":1,"backends":{}}')
        with self.assertRaises(ConfigurationError):
            read_json(self.path)

    def test_profile_traversal_denied(self):
        cfg = GatewayConfig.load(self.path).backends["dop_b"]
        for identifier in ("../sample", "x/y", "x\\y", "", None):
            with self.assertRaises(ConfigurationError):
                cfg.profile(identifier)

    def test_symlink_ancestor_rejected(self):
        from unittest.mock import patch
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(ConfigurationError):
                GatewayConfig.load(self.path)

    def test_manifest_empty_or_changed_rejected(self):
        cfg = GatewayConfig.load(self.path).backends["dop_b"]
        cfg.source_manifest.write_text('{}')
        with self.assertRaises(ConfigurationError):
            cfg.verify()

    def test_missing_family_and_boolean_version_rejected(self):
        self.data["schema_version"] = True
        self.write()
        with self.assertRaises(ConfigurationError):
            GatewayConfig.load(self.path)
        self.data["schema_version"] = 1
        del self.data["backends"]["dop_100"]
        self.write()
        with self.assertRaises(ConfigurationError):
            GatewayConfig.load(self.path)

    def test_relocation_preserves_config(self):
        import shutil
        relocated = self.base / "moved"
        relocated.mkdir()
        for name in ("dop_b", "dop_100"):
            shutil.copytree(self.base / name, relocated / name)
        shutil.copy2(self.path, relocated / "config.json")
        for backend in GatewayConfig.load(relocated / "config.json").backends.values():
            backend.verify()


if __name__ == "__main__":
    unittest.main()
