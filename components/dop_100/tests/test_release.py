# SPDX-License-Identifier: Apache-2.0
"""Neutral release membership, deterministic bytes and privacy refusal tests."""
import importlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from universal_diascreen_hmi.errors import AgentError


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("public_release", ROOT / "tools/release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.area = Path(scratch.name)
        self.root = self.area / "source"
        self.root.mkdir()
        self.output = self.area / "outputs"
        self.output.mkdir()
        for name in release.ROOT_FILES:
            (self.root / name).write_text("Neutral public fixture\n", encoding="utf-8")
        for name in release.PUBLIC_DIRS:
            directory = self.root / name
            directory.mkdir()
            (directory / "neutral.json").write_text('{"scope":"synthetic"}\n', encoding="utf-8")
        (self.root / ".agent-state").mkdir()

    def build(self, name="package.zip"):
        return release.build_release(self.root, self.output / name, workspace=self.output)

    def refused(self, operation, code):
        with self.assertRaises(AgentError) as error:
            operation()
        self.assertEqual(error.exception.code, code)

    def test_deterministic_rebuild_outside_public_tree_and_every_member(self):
        first = self.build("first.zip")
        manifest = (self.root / release.MANIFEST_NAME).read_bytes()
        second = self.build("second.zip")
        self.assertEqual(first, second)
        self.assertEqual((self.output / "first.zip").read_bytes(), (self.output / "second.zip").read_bytes())
        files, frozen = release.check_manifest(self.root)
        self.assertEqual(frozen, manifest)
        self.assertEqual(first["files"], len(files) + 1)
        with zipfile.ZipFile(self.output / "first.zip") as archive:
            self.assertEqual(set(archive.namelist()), set(files) | {release.MANIFEST_NAME})
            for name, data in files.items():
                self.assertEqual(archive.read(name), data)
            self.assertEqual(archive.read(release.MANIFEST_NAME), manifest)
        self.assertEqual(release.validate_archive(self.output / "first.zip", manifest)["status"], "VERIFIED")

    def test_manifest_extra_missing_and_changed_public_files_fail(self):
        for variant in ("extra", "missing", "changed"):
            with self.subTest(variant=variant):
                source = self.root / "docs/neutral.json"
                original = source.read_bytes()
                manifest_path = self.root / release.MANIFEST_NAME
                if not manifest_path.exists():
                    self.build()
                if variant == "extra":
                    (self.root / "docs/extra.md").write_text("Extra\n", encoding="utf-8")
                elif variant == "missing":
                    source.unlink()
                else:
                    source.write_bytes(original + b"changed\n")
                self.refused(lambda: release.check_manifest(self.root), "RELEASE_DRIFT")
                self.refused(lambda: self.build(variant + ".zip"), "RELEASE_DRIFT")
                self.assertFalse((self.output / (variant + ".zip")).exists())
                (self.root / "docs/extra.md").unlink(missing_ok=True)
                source.write_bytes(original)

    def test_unknown_native_extensions_and_binary_text_refused(self):
        for suffix in (".dpa", ".dps", ".cin", ".bmp", ".zip", ".exe", ".txt"):
            extra = self.root / "examples" / ("asset" + suffix)
            extra.write_bytes(b"opaque")
            self.refused(lambda: release.collect_public(self.root), "RELEASE_EXTENSION")
            extra.unlink()
        candidate = self.root / "examples/neutral.json"
        for data in (b"\x00binary", b"\xff"):
            candidate.write_bytes(data)
            self.refused(lambda: release.collect_public(self.root), "RELEASE_BINARY")

    def test_links_refused_and_ignored_runtime_trees_not_read(self):
        ignored = self.root / "tests/__pycache__"
        ignored.mkdir()
        (ignored / "opaque.pyc").write_bytes(b"\0opaque")
        (self.root / ".agent-state/source.dpa").write_bytes(b"private native bytes")
        self.assertFalse(any("__pycache__" in name or ".agent-state" in name
                             for name in release.collect_public(self.root)))
        link = self.root / "docs/linked.md"
        try:
            link.symlink_to(self.root / "README.md")
        except (OSError, NotImplementedError):
            self.skipTest("Host does not permit a neutral symbolic link")
        self.refused(lambda: release.collect_public(self.root), "RELEASE_SYMLINK")

    def test_reparse_attribute_is_rejected_without_host_link_privilege(self):
        metadata = SimpleNamespace(st_mode=release.stat.S_IFREG, st_file_attributes=0x400)
        with patch.object(Path, "lstat", return_value=metadata):
            self.refused(lambda: release._plain(self.root / "neutral.md"), "RELEASE_SYMLINK")

    def test_output_is_new_only_bounded_and_never_enters_public_tree(self):
        target = self.output / "existing.zip"
        target.write_bytes(b"keep")
        self.refused(lambda: self.build("existing.zip"), "RELEASE_OUTPUT")
        self.assertEqual(target.read_bytes(), b"keep")
        self.assertFalse((self.root / release.MANIFEST_NAME).exists())
        self.refused(lambda: release.build_release(self.root, self.area / "escape.zip", workspace=self.output), "RELEASE_OUTPUT")
        self.refused(lambda: release.build_release(self.root, self.root / "reports/public.zip", workspace=self.root), "RELEASE_OUTPUT")
        default = self.root / ".agent-state/default.zip"
        release.build_release(self.root, default)
        self.assertTrue(default.exists())

    def test_archive_extra_missing_changed_duplicate_or_manifest_bytes_fail(self):
        self.build()
        manifest = (self.root / release.MANIFEST_NAME).read_bytes()
        with zipfile.ZipFile(self.output / "package.zip") as archive:
            original = [(info, archive.read(info)) for info in archive.infolist()]
        for variant in ("extra", "missing", "changed", "duplicate", "manifest"):
            target = self.output / (variant + ".zip")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(target, "w") as archive:
                    for index, (info, data) in enumerate(original):
                        if variant == "missing" and index == 0:
                            continue
                        if variant == "changed" and index == 0:
                            data = bytes([data[0] ^ 1]) + data[1:]
                        if variant == "manifest" and info.filename == release.MANIFEST_NAME:
                            data = data.replace(b'"size": ', b'"size": 0', 1)
                        archive.writestr(info, data)
                    if variant in ("extra", "duplicate"):
                        name = "docs/unexpected.md" if variant == "extra" else original[0][0].filename
                        info = zipfile.ZipInfo(name, release.ZIP_DATE)
                        info.create_system = 3
                        info.external_attr = release.ZIP_MODE
                        archive.writestr(info, b"extra")
            with self.subTest(variant=variant):
                self.refused(lambda: release.validate_archive(target, manifest), "RELEASE_ARCHIVE")
        original_bytes = (self.output / "package.zip").read_bytes()
        for variant, data in (("prefix", b"unlisted native bytes" + original_bytes),
                              ("trailer", original_bytes + b"unlisted native bytes")):
            target = self.output / (variant + ".zip")
            target.write_bytes(data)
            self.refused(lambda: release.validate_archive(target, manifest), "RELEASE_ARCHIVE")

    def test_manifest_is_canonical_safe_and_excludes_cycle_reports(self):
        (self.root / "reports/RELEASE.json").write_text('{"archive":"pending"}\n', encoding="utf-8")
        self.build()
        path = self.root / release.MANIFEST_NAME
        data = path.read_bytes()
        document = json.loads(data)
        names = {row["path"] for row in document["entries"]}
        self.assertFalse(names & release.CYCLE_EXCLUSIONS)
        self.assertEqual(data, release.canonical(document))
        for name in ("../escape.md", "/absolute.md", "docs//double.md", "docs/../escape.md", release.MANIFEST_NAME):
            changed = json.loads(data)
            changed["entries"][0]["path"] = name
            self.refused(lambda: release.parse_manifest(release.canonical(changed)), "RELEASE_MANIFEST")
        self.refused(lambda: release.parse_manifest(data + b"\n"), "RELEASE_MANIFEST")
        document["schema_version"] = True
        self.refused(lambda: release.parse_manifest(release.canonical(document)), "RELEASE_MANIFEST")
        self.refused(lambda: release.parse_manifest(release.canonical({"schema_version": 1, "entries": []})), "RELEASE_MANIFEST")

    def test_windows_reserved_and_aliased_member_names_refused(self):
        for name in ("docs/CON.md", "docs/LpT1.json", "docs/name .json", "docs/sub./a.md",
                     "docs/end /a.md", "docs/wild?.md", "docs/aux/note.md"):
            with self.subTest(name=name):
                self.refused(lambda: release._relative_name(name), "RELEASE_MANIFEST")

    def test_privacy_markers_case_insensitive_and_public_diagnostics_sanitized(self):
        marker = "SYNTHETIC_" + "PRIVATE_SENTINEL"
        marker_path = self.root / ".agent-state/markers.list"
        marker_path.write_text(marker + "\n", encoding="utf-8")
        markers = release.load_markers(marker_path, self.root)
        source = self.root / "docs/neutral.json"
        source.write_text(marker.lower(), encoding="utf-8")
        self.refused(lambda: release.collect_public(self.root, markers), "RELEASE_PRIVACY")
        fixed = "Q" + ":/" + "neutral-location"
        source.write_text(fixed, encoding="utf-8")
        self.refused(lambda: release.collect_public(self.root), "RELEASE_PRIVACY")
        for value in ("prefix" + fixed, chr(92) * 2 + "neutral-host" + chr(92) + "share" + chr(92) + "file",
                      "https://example.org/?local=" + fixed):
            self.refused(lambda: release.check_text(value.encode("utf-8")), "RELEASE_PRIVACY")
        release.check_text(b"https://example.org/docs and a logical sha256 identity")
        self.refused(lambda: release.load_markers(source, self.root), "RELEASE_MARKERS")
        old_root = release.ROOT
        try:
            release.ROOT = self.root
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = release.main(["--output", str(self.output / "new.zip"), "--workspace", str(self.output)])
            self.assertEqual(status, 2)
            self.assertEqual(json.loads(stdout.getvalue()), {"status": "STOP", "code": "RELEASE_PRIVACY"})
            self.assertNotIn(str(self.root), stdout.getvalue())
            self.assertNotIn(marker, stdout.getvalue())
            self.assertNotIn(fixed, stdout.getvalue())
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = release.main(["--unknown", str(marker_path)])
            self.assertEqual(status, 2)
            self.assertEqual(json.loads(stdout.getvalue()), {"status": "STOP", "code": "RELEASE_ARGUMENTS"})
            self.assertNotIn(str(marker_path), stdout.getvalue())
        finally:
            release.ROOT = old_root

    def test_cli_check_is_read_only_and_success_receipt_has_hashes_counts_only(self):
        old_root = release.ROOT
        try:
            release.ROOT = self.root
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = release.main(["--output", str(self.output / "cli.zip"), "--workspace", str(self.output)])
            receipt = json.loads(stdout.getvalue())
            self.assertEqual(status, 0)
            self.assertEqual(set(receipt), {"status", "files", "archive_sha256", "manifest_sha256"})
            before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(release.main(["--check"]), 0)
            self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
            self.assertEqual(json.loads(stdout.getvalue())["manifest_sha256"], receipt["manifest_sha256"])
        finally:
            release.ROOT = old_root

    def test_release_sources_pass_their_own_privacy_policy(self):
        for name in ("tools/release.py", "tests/test_release.py"):
            release.check_text((ROOT / name).read_bytes())

    def test_current_inventory_and_public_privacy(self):
        files = release.collect_public(ROOT)
        self.assertIn("tools/release.py", files)
        self.assertIn("tests/test_release.py", files)
        matrix = json.loads(files["docs/SUPPORT_MATRIX.json"])
        self.assertEqual({row["id"] for row in matrix["features"]},
                         {f"D{i:02d}" for i in range(1, 45)} | {f"U{i:02d}" for i in range(1, 10)})
        self.assertEqual(len(matrix["features"]), 53)
        legacy = matrix["legacy_tools"]
        self.assertEqual(len(legacy), 22)
        self.assertEqual(sum(row["status"] == "INTENTIONALLY_EXCLUDED" for row in legacy), 4)
        self.assertEqual(sum(row["status"] != "INTENTIONALLY_EXCLUDED" for row in legacy), 18)
        self.assertEqual(len({row["legacy_name"] for row in legacy}), 22)
        regressions = matrix["required_regressions"]
        self.assertEqual({row["id"] for row in regressions}, {f"R{i:02d}" for i in range(1, 22)})
        self.assertEqual(len(regressions), 21)
        self.assertEqual(len(matrix["excluded_save_options"]), 2)
        sources = json.loads(files["SOURCE_MANIFEST.json"])["sources"]
        source_ids = {row["source_id"] for row in sources}
        self.assertEqual(len(source_ids), len(sources))
        for row in sources:
            self.assertRegex(row["sha256"], r"^[0-9a-f]{64}$")
            self.assertFalse(set(row) & {"path", "local_path", "ip"})
        for row in matrix["features"]:
            self.assertTrue(row["source_refs"])
            self.assertLessEqual(set(row["source_refs"]), source_ids)
        for row in matrix["native_history"]:
            self.assertIn(row["source_id"], source_ids)
        self.assertLessEqual(set(matrix["inventory_sources"]), source_ids)
        targets = {name for row in matrix["features"] + regressions for name in row["planned_tests"]}
        catalog = [row["test_name"] for row in matrix["test_catalog"]]
        self.assertEqual(len(catalog), len(set(catalog)))
        self.assertLessEqual(targets, set(catalog))
        for target in set(catalog):
            module_name, class_name, method_name = target.split(".")
            self.assertRegex(module_name, r"^test_[a-z_]+$")
            module = importlib.import_module("tests." + module_name)
            case = getattr(module, class_name)
            self.assertTrue(issubclass(case, unittest.TestCase), target)
            self.assertTrue(callable(getattr(case, method_name, None)), target)
        for name, data in files.items():
            self.assertTrue(release._selected_name(name), name)
            self.assertNotIn(".agent-state", name.split("/"))
            release.check_text(data)


if __name__ == "__main__":
    unittest.main()
