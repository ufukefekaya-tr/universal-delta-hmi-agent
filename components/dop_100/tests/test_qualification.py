# SPDX-License-Identifier: Apache-2.0
"""Original neutral observed-preamble fixtures and private-runner boundaries."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from universal_diascreen_hmi.errors import AgentError, digest
from universal_diascreen_hmi.native import Project, layout_digest
from universal_diascreen_hmi.operations import compile_changes
from tests.fixtures import native, payload, profile, wide, wrap


_TOOL_PATH = Path(__file__).resolve().parents[1] / "tools" / "private_qualification.py"
_SPEC = importlib.util.spec_from_file_location("neutral_private_qualification", _TOOL_PATH)
qualification = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(qualification)


def with_preamble(extra):
    body = payload()
    first_screen = Project(native()).pages[0].section.start
    return wrap(body[:first_screen] + extra + body[first_screen:])


def counted(key, blob):
    return key + b"=" + str(len(blob)).encode("ascii") + b"\r\n" + blob + b"\r\n"


def observed_preamble():
    hidden = b"encoded-like\r\n[Screen]\r\nID=707\r\n[Element]\r\nnPartsID=999\r\n"
    lua = b'<?xml version="1.0"?><Root><![CDATA[\r\n[Screen]\r\nID=808\r\n]]></Root>'
    return (b"[Ethernet]\r\n" + counted(b"EipDTBase64Len", hidden)
            + b"[Multi-Language]\r\n" + wide("wCSVLogTitleLen000_00", "Çığ İğne")
            + b"[LOG]\r\n" + wide("wLogTitleLen000_00", "Günlük")
            + b"[LuaData]\r\n" + counted(b"<EXTENT>LuaXmlFileLen", lua))


class QualificationTests(unittest.TestCase):
    def test_observed_preamble_frames_do_not_create_fake_owners(self):
        data = with_preamble(observed_preamble())
        project = Project(data)
        self.assertEqual([page.page_id for page in project.pages], [1, 2])
        self.assertEqual((sum(len(page.elements) for page in project.pages),
                          sum(len(e.states) for page in project.pages for e in page.elements)), (4, 7))
        self.assertFalse(project.index.unqualified_records)
        ethernet = next(section for section in project.index.sections if section.name == "Ethernet")
        self.assertIn(b"ID=707", ethernet.one("EipDTBase64Len").blob(project.file.payload))
        language = next(section for section in project.index.sections if section.name == "Multi-Language")
        self.assertEqual(language.one("wCSVLogTitleLen000_00").text(project.file.payload), "Çığ İğne")
        log = next(section for section in project.index.sections if section.name == "LOG")
        self.assertEqual(log.one("wLogTitleLen000_00").text(project.file.payload), "Günlük")
        lua = next(section for section in project.index.sections if section.name == "LuaData")
        self.assertIn(b"ID=808", lua.one("LuaXmlFileLen").blob(project.file.payload))
        self.assertEqual(project.file.encode(project.file.payload), data)

    def test_known_preamble_font_patch_preserves_all_framed_owners(self):
        data = with_preamble(observed_preamble())
        q = Project(data)
        contract = profile()
        contract["indexed_layout_sha256"] = layout_digest(q)
        candidate, steps = compile_changes(data, [{"op": "set_property", "page_id": 1,
            "element_id": 10, "state_value": 0, "field": "FontColor", "value": 0x123456}], contract)
        reread = Project(candidate)
        self.assertEqual([p.page_id for p in reread.pages], [1, 2])
        for name in ("Ethernet", "Multi-Language", "LOG", "LuaData"):
            before = next(s for s in q.index.sections if s.name == name)
            after = next(s for s in reread.index.sections if s.name == name)
            self.assertEqual(q.file.payload[before.start:before.end], reread.file.payload[after.start:after.end])
        self.assertEqual(len(steps[0]["ledger"]), 1)

    def test_future_length_frame_does_not_grant_fake_screen_ownership(self):
        fake = b"[Screen]\r\nID=606\r\n[AuxKeyElement]\r\n"
        data = with_preamble(b"[Ethernet]\r\n" + counted(b"FutureOpaqueLen", fake))
        q = Project(data)
        self.assertEqual(q.pages, [])
        self.assertTrue(q.index.stop_reason.startswith("unknown_frame:"))
        self.assertEqual(q.file.encode(q.file.payload), data)
        contract = profile()
        contract["indexed_layout_sha256"] = layout_digest(q)
        with self.assertRaises(AgentError):
            compile_changes(data, [{"op": "set_property", "page_id": 606,
                "element_id": 1, "state_value": 0, "field": "FontColor", "value": 0}], contract)

    def test_malformed_known_preamble_lengths_and_terminators_stop(self):
        samples = [b"[Application]\r\n[Ethernet]\r\nEipDTBase64Len=99\r\nx",
                   b"[Application]\r\n[LuaData]\r\n<EXTENT>LuaXmlFileLen=5\r\nabc\r\n",
                   b"[Application]\r\n[Multi-Language]\r\nwCSVLogTitleLen000_00=3\r\na\0\0\r\n"]
        for body in samples:
            with self.subTest(body=body[:40]), self.assertRaises(AgentError):
                Project(wrap(body))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "task"
        self.workspace.mkdir()
        self.source = self.root / "source.dpa"
        self.source.write_bytes(native())
        self.manifest = self.root / "manifest.json"

    def tearDown(self):
        self.temporary.cleanup()

    def write_manifest(self, **updates):
        entry = {"source_id": "sample-01", "path": "source.dpa", "sha256": digest(self.source.read_bytes())}
        entry.update(updates)
        self.manifest.write_text(json.dumps({"sources": [entry]}), encoding="utf-8")

    def test_optional_noop_report_is_new_only_and_contains_no_private_path(self):
        self.write_manifest()
        before = self.source.read_bytes()
        result = qualification.run(self.manifest, self.workspace, "report.json")
        row = result["sources"][0]
        self.assertEqual(row["status"], "PASS_NOOP_ONLY")
        self.assertEqual((row["pages"], row["elements"], row["states"]), (2, 4, 7))
        self.assertEqual(self.source.read_bytes(), before)
        public = (self.workspace / "report.json").read_text()
        self.assertNotIn(str(self.root), public)
        self.assertNotIn("Main.Start", public)
        with self.assertRaises(AgentError):
            qualification.run(self.manifest, self.workspace, "report.json")

    def test_explicit_reviewed_profile_exercises_in_memory_full_inverse(self):
        self.write_manifest(profile=profile())
        before = self.source.read_bytes()
        result = qualification.run(self.manifest, self.workspace, "visual.json")
        self.assertEqual(result["sources"][0]["status"], "PASS_OFFLINE_FONT_COLOR_INVERSE")
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.workspace.iterdir()), ["visual.json"])

    def test_missing_or_stale_layout_review_does_not_autoqualify(self):
        for update in ({"reviewed_index_ack": False}, {"indexed_layout_sha256": "0" * 64}):
            contract = profile()
            contract.update(update)
            self.write_manifest(profile=contract)
            result = qualification.qualify_manifest(self.manifest)
            self.assertEqual(result["sources"][0]["code"], "INDEX_REVIEW")
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_source_hash_mismatch_and_format_failure_do_not_leak_exceptions(self):
        self.write_manifest(sha256="0" * 64)
        row = qualification.qualify_manifest(self.manifest)["sources"][0]
        self.assertEqual(row["code"], "QUAL_SOURCE_HASH")
        self.source.write_bytes(b"private malformed file label")
        self.write_manifest()
        row = qualification.qualify_manifest(self.manifest)["sources"][0]
        self.assertEqual(row["status"], "STOP")
        text = json.dumps(row)
        self.assertNotIn("private malformed", text)
        self.assertNotIn(str(self.source), text)

    def test_profile_file_hash_required_and_checked(self):
        profile_path = self.root / "profile.json"
        profile_path.write_text(json.dumps(profile()), encoding="utf-8")
        self.write_manifest(profile="profile.json", profile_sha256=digest(profile_path.read_bytes()))
        self.assertEqual(qualification.qualify_manifest(self.manifest)["status"], "PASS")
        self.write_manifest(profile="profile.json", profile_sha256="0" * 64)
        self.assertEqual(qualification.qualify_manifest(self.manifest)["sources"][0]["code"], "QUAL_PROFILE_HASH")

    def test_report_escape_source_overwrite_and_duplicate_ids_rejected(self):
        self.write_manifest()
        with self.assertRaises(AgentError):
            qualification.run(self.manifest, self.workspace, "../escaped.json")
        with self.assertRaises(AgentError):
            qualification.run(self.manifest, self.workspace, self.source)
        value = json.loads(self.manifest.read_text())
        value["sources"].append(value["sources"][0].copy())
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(AgentError):
            qualification.qualify_manifest(self.manifest)

    def test_all_sources_are_read_after_an_earlier_source_failure(self):
        self.write_manifest(sha256="0" * 64)
        document = json.loads(self.manifest.read_text())
        document["sources"].append({"source_id": "sample-02", "path": "source.dpa",
                                    "sha256": digest(self.source.read_bytes())})
        self.manifest.write_text(json.dumps(document), encoding="utf-8")
        result = qualification.qualify_manifest(self.manifest)
        self.assertEqual(result["source_count"], 2)
        self.assertEqual([row["status"] for row in result["sources"]], ["STOP", "PASS_NOOP_ONLY"])

    def test_real_optional_cli_emits_only_neutral_json_summary(self):
        self.write_manifest()
        before = self.source.read_bytes()
        completed = subprocess.run([sys.executable, "-B", str(_TOOL_PATH), "--manifest", str(self.manifest),
            "--workspace", str(self.workspace), "--report", "cli-report.json"],
            capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {"status": "PASS", "source_count": 1})
        self.assertNotIn(str(self.root), completed.stdout)
        self.assertEqual(self.source.read_bytes(), before)

    def test_unpublishable_source_id_and_duplicate_json_fields_stop(self):
        self.write_manifest(source_id="private/path label")
        with self.assertRaises(AgentError):
            qualification.qualify_manifest(self.manifest)
        self.manifest.write_text('{"sources": [], "sources": []}', encoding="utf-8")
        with self.assertRaises(AgentError):
            qualification.qualify_manifest(self.manifest)


if __name__ == "__main__":
    unittest.main()
