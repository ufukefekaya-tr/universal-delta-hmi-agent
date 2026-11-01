"""Reject missing, unauthorized and corrupted neutral forward-test evidence."""
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("behavior_evidence", ROOT / "tools/check_behavioral_evidence.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class BehavioralEvidenceTests(unittest.TestCase):
    def fixture(self, root):
        wrap = lambda body: b"SYNTHETIC" + gzip.compress(bytes(x ^ 100 for x in bytes(range(41)) + body), mtime=0)
        b = root / "dop_b/workspace"
        d = root / "dop_100/workspace"
        b.mkdir(parents=True)
        d.mkdir(parents=True)
        fixture_spec = importlib.util.spec_from_file_location("original_dia_fixtures", ROOT / "components/dop_100/tests/fixtures.py")
        fixture = importlib.util.module_from_spec(fixture_spec)
        fixture_spec.loader.exec_module(fixture)
        from universal_diascreen_hmi.native import NativeFile
        (b / "switch.dps").write_bytes(wrap(b"SubType=1\r\nUnknown=preserve\r\n"))
        body = b"[Application]\r\n" + mod.caption("START") + mod.caption("START ON") + b"Unknown=preserve"
        (d / "switch.dpa").write_bytes(fixture.wrap(body))
        (d / "existing-effect.dpa").write_bytes(wrap(b"Already saved"))
        identities = {family: {p.name: {"sha256": mod.digest(p.read_bytes()), "mtime_ns": p.stat().st_mtime_ns} for p in folder.iterdir()} for family, folder in (("dop_b", b), ("dop_100", d))}
        (root / "originals.json").write_text(json.dumps(identities))
        effect = d / "existing-effect.dpa"
        (root / "recovery-context.json").write_text(json.dumps({"operation_id": "EXPECTED", "effect_sha256": mod.digest(effect.read_bytes()), "mtime_ns": effect.stat().st_mtime_ns}))
        (b / "candidate-b.dps").write_bytes(wrap(b"SubType=2\r\nUnknown=preserve\r\n"))
        changed = body.replace(mod.caption("START"), mod.caption("KAPALI")).replace(mod.caption("START ON"), mod.caption("AÇIK"))
        (d / "candidate-d.dpa").write_bytes(NativeFile((d / "switch.dpa").read_bytes()).encode(changed))
        rows = [{"case": case, "kind": "call_tool:" + name} for case, name in (("B-retained", "dop_b__save_as"), ("D-captions", "dop_100__save_as"), ("read-only", "dop_b__inspect"), ("stale", "dop_b__preview"), ("source-text", "dop_100__inspect"), ("unknown", "dop_100__reconcile_operation"))]
        for row in rows:
            row["error"] = None
            data = {}
            if row["case"] == "B-retained":
                data["sha256"] = mod.digest((b / "candidate-b.dps").read_bytes())
            elif row["case"] == "D-captions":
                data["candidate_sha256"] = mod.digest((d / "candidate-d.dpa").read_bytes())
            elif row["case"] == "unknown":
                data["state"] = "SUCCEEDED"
                data["operation_id"] = "EXPECTED"
                data["result"] = {"candidate_sha256": mod.digest(effect.read_bytes())}
                row["arguments"] = {"operation_id": "EXPECTED"}
            row["result"] = {"isError": False, "structuredContent": data}
        for case, family in (("B-retained", "dop_b"), ("D-captions", "dop_100")):
            rows.append({"case": case, "kind": "call_tool:" + family + "__apply_plan", "error": None, "result": {"isError": False, "structuredContent": {}}})
        def trace(value):
            (root / "trace.jsonl").write_text("\n".join(json.dumps(r) for r in value) + "\n")
        trace(rows)
        return rows, trace

    def test_exact_effects_and_calls_then_corrupted_preserved_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            self.assertEqual(mod.audit(root)["status"], "PASS")
            source = (root / "dop_100/workspace/switch.dpa").read_bytes()
            saved = (root / "dop_100/workspace/candidate-d.dpa").read_bytes()
            self.assertNotEqual(len(mod.payload(source)), len(mod.payload(saved)))
            candidate = root / "dop_100/workspace/candidate-d.dpa"
            candidate.write_bytes(candidate.read_bytes() + b"bad framing")
            with self.assertRaises((ValueError, EOFError, OSError)):
                mod.audit(root)

    def test_no_call_coverage_and_unauthorized_call_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows, trace = self.fixture(root)
            trace([])
            with self.assertRaisesRegex(ValueError, "Empty trace"):
                mod.audit(root)
            trace(rows + [{"case": "version", "kind": "call_tool:dop_b__plan_changes"}])
            with self.assertRaisesRegex(ValueError, "Read-only intent"):
                mod.audit(root)
            trace(rows + [{"case": "unknown", "kind": "call_tool:dop_100__save_as"}])
            with self.assertRaisesRegex(ValueError, "Unauthorized route"):
                mod.audit(root)
            trace(rows + [{"case": "cleanup", "kind": "call_tool:dop_100__close_session"}])
            self.assertEqual(mod.audit(root)["status"], "PASS")
            trace(rows + [{"case": "cleanup", "kind": "call_tool:dop_100__apply_plan"}])
            with self.assertRaisesRegex(ValueError, "Unauthorized route"):
                mod.audit(root)
            rows[0]["result"]["isError"] = True
            trace(rows)
            with self.assertRaisesRegex(ValueError, "matching successful"):
                mod.audit(root)

    def test_package_effect_nested_uppercase_and_wrong_recovery_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows, trace = self.fixture(root)
            trace(rows + [{"case": "fake", "kind": "call_tool:dop_100__apply_offline_package"}])
            with self.assertRaisesRegex(ValueError, "Unauthorized route"):
                mod.audit(root)
            trace(rows)
            nested = root / "dop_b/workspace/nested"
            nested.mkdir()
            extra = nested / "unrequested.DPS"
            extra.write_bytes(b"unexpected")
            with self.assertRaisesRegex(ValueError, "unexpected native"):
                mod.audit(root)
            extra.unlink()
            extra = nested / "unrequested.zip"
            extra.write_bytes(b"unexpected")
            with self.assertRaisesRegex(ValueError, "unexpected native"):
                mod.audit(root)
            extra.unlink()
            recovery = next(r for r in rows if r["case"] == "unknown")
            recovery["arguments"]["operation_id"] = "OTHER"
            recovery["result"]["structuredContent"]["operation_id"] = "OTHER"
            trace(rows)
            with self.assertRaisesRegex(ValueError, "existing operation"):
                mod.audit(root)

    def test_separate_missing_backend_trace_is_also_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            secondary = root / "trace-missing.jsonl"
            secondary.write_text(json.dumps({"case": "missing", "kind": "call_tool:delta_catalog"}) + "\n")
            self.assertIn("trace-missing.jsonl", mod.audit(root)["traces"])
            secondary.write_text(json.dumps({"case": "missing", "kind": "call_tool:dop_100__apply_plan"}) + "\n")
            with self.assertRaisesRegex(ValueError, "Unauthorized route"):
                mod.audit(root)

    def test_identical_source_replacement_and_extra_native_output_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            extra = root / "dop_b/workspace/unrequested.dps"
            extra.write_bytes(b"unrequested")
            with self.assertRaisesRegex(ValueError, "unexpected native"):
                mod.audit(root)
            extra.unlink()
            source = root / "dop_b/workspace/switch.dps"
            import os
            os.utime(source, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns + 100000000))
            with self.assertRaisesRegex(ValueError, "Original source"):
                mod.audit(root)
