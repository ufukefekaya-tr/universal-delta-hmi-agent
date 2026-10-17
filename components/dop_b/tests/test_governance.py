"""Real temporary-Git-repository regressions for bootstrap and session guards."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT / "tools"))
from _governance import CONTROL_PLANE, GuardError, authorize, normalize_path, policy_epoch, session, verify_bootstrap
from check_repo import check_repository


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="uhmi-governance-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Neutral Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        for name in CONTROL_PLANE:
            text = "# Türkçe kontrol\n" if name != "INDEX.md" else "# Index\n[Workflow](docs/WORKFLOW.md)\n"
            (self.root / name).write_text(text, encoding="utf-8", newline="\n")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "WORKFLOW.md").write_text("Meaningful workflow fixture\n", encoding="utf-8")
        self.git("add", "AGENTS.md", "SYSTEM_PROMPT.md", "INDEX.md", "docs/WORKFLOW.md")
        self.git("commit", "--quiet", "-m", "Neutral bootstrap")
        self.baseline = self.git("rev-parse", "HEAD").strip()
        self.state_dir = self.root / ".agent-state" / "TEST-1"
        self.state_dir.mkdir(parents=True)
        self.envelope_path = self.state_dir / "TASK_ENVELOPE.json"
        self.checkpoint_path = self.state_dir / "SESSION_CHECKPOINT.json"
        self.envelope = {
            "task_id": "TEST-1", "authority": "Neutral test exact scope",
            "baseline": self.baseline, "policy_epoch": policy_epoch(self.root),
            "allowed_write": ["docs/", "tests/", ".agent-state/TEST-1/"],
            "protected": list(CONTROL_PLANE), "commit_owner": "root",
            "scope_owners": {"docs_author": ["docs/"], "root": [".agent-state/TEST-1/"]}
        }
        self.checkpoint = {
            "task_id": "TEST-1", "sequence": 0, "policy_epoch": self.envelope["policy_epoch"],
            "repo_head": self.baseline, "envelope_sha256": "", "open": ["Native qualification pending"]
        }
        self.write_state()

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def write_state(self):
        raw = (json.dumps(self.envelope, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self.envelope_path.write_bytes(raw)
        self.checkpoint["envelope_sha256"] = hashlib.sha256(raw).hexdigest()
        self.checkpoint_path.write_text(json.dumps(self.checkpoint), encoding="utf-8")

    def run_cli(self, script, *args):
        return subprocess.run([sys.executable, str(SOURCE_ROOT / "tools" / script), "--root", str(self.root), *args],
                              capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "PYTHONUTF8": "1"})

    def current_session(self, **kwargs):
        return session(self.root, self.envelope_path, self.checkpoint_path, "TEST-1", **kwargs)

    def test_epoch_uses_exact_path_nul_raw_bytes_nul(self):
        data = b"".join(name.encode("utf-8") + b"\0" + (self.root / name).read_bytes() + b"\0" for name in CONTROL_PLANE)
        self.assertEqual(policy_epoch(self.root), hashlib.sha256(data).hexdigest())
        before = policy_epoch(self.root)
        path = self.root / "AGENTS.md"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.assertNotEqual(policy_epoch(self.root), before)
        with self.assertRaises(GuardError):
            verify_bootstrap(self.root)

    def test_bootstrap_detects_dirty_index_even_if_working_bytes_match_head(self):
        path = self.root / "AGENTS.md"
        raw = path.read_bytes()
        path.write_bytes(raw + b"Staged change\n")
        self.git("add", "AGENTS.md")
        path.write_bytes(raw)
        with self.assertRaisesRegex(GuardError, "clean/committed"):
            verify_bootstrap(self.root)

    def test_committed_control_plane_change_invalidates_whole_session(self):
        path = self.root / "SYSTEM_PROMPT.md"
        path.write_text("Changed global policy\n", encoding="utf-8")
        self.git("add", "SYSTEM_PROMPT.md")
        self.git("commit", "--quiet", "-m", "Changed policy epoch")
        verify_bootstrap(self.root)
        with self.assertRaisesRegex(GuardError, "Policy epoch"):
            self.current_session(allow_advanced_head=True)

    def test_raw_envelope_hash_cannot_be_bypassed_by_equivalent_json(self):
        raw = self.envelope_path.read_bytes()
        self.envelope_path.write_bytes(raw + b" \n")
        with self.assertRaisesRegex(GuardError, "raw-byte SHA"):
            self.current_session()

    def test_checkpoint_task_epoch_sequence_and_head_are_checked(self):
        changes = {"task_id": "WRONG", "policy_epoch": "0" * 64, "sequence": True, "repo_head": "0" * 40}
        original = dict(self.checkpoint)
        for key, value in changes.items():
            with self.subTest(field=key):
                self.checkpoint = {**original, key: value}
                self.write_state()
                with self.assertRaises(GuardError):
                    self.current_session()

    def test_baseline_must_be_immutable_existing_ancestor(self):
        for value in ("HEAD", "0" * 40):
            with self.subTest(baseline=value):
                self.envelope["baseline"] = value
                self.write_state()
                with self.assertRaisesRegex(GuardError, "baseline"):
                    self.current_session()

    def test_snapshot_current_head_increments_sequence_without_writing(self):
        (self.root / "docs" / "next.md").write_text("Scoped next revision\n", encoding="utf-8")
        self.git("add", "docs/next.md")
        self.git("commit", "--quiet", "-m", "Scoped update")
        with self.assertRaisesRegex(GuardError, "HEAD differs"):
            self.current_session()
        checkpoint_bytes = self.checkpoint_path.read_bytes()
        result = self.run_cli("session_guard.py", "snapshot", "--task-id", "TEST-1")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["repo_head"], self.git("rev-parse", "HEAD").strip())
        self.assertEqual(output["sequence"], 1)
        self.assertEqual(output["open"], self.checkpoint["open"])
        self.assertEqual(self.checkpoint_path.read_bytes(), checkpoint_bytes)

    def test_unicode_path_allowed_and_parent_prefix_sibling_denied(self):
        relative = "docs/ölçü_İŞ_状态.md"
        self.assertEqual(authorize(self.root, self.envelope, [relative], "docs_author"), [relative])
        result = self.run_cli("session_guard.py", "action", "--task-id", "TEST-1", "--kind", "edit", "--owner", "docs_author", "--paths", relative)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["paths"], [relative])
        for sibling in ("docs-escape/file.md", "docsevil/file.md", "tests/unowned.py"):
            with self.subTest(path=sibling), self.assertRaises(GuardError):
                authorize(self.root, self.envelope, [sibling], "docs_author")

    def test_traversal_absolute_drive_stream_and_git_paths_denied(self):
        invalid = ("../secret", "docs/../AGENTS.md", "docs//file", "docs/./file", "/tmp/file", "C:/outside/file",
                   "\\\\server\\share\\file", "docs/file:stream", ".git/config", "docs/\0file")
        for relative in invalid:
            with self.subTest(path=relative), self.assertRaises(GuardError):
                authorize(self.root, self.envelope, [relative])

    def test_case_aliases_cannot_bypass_protected_scope(self):
        for relative in ("agents.md", "SYSTEM_prompt.MD", "index.Md"):
            with self.subTest(path=relative), self.assertRaisesRegex(GuardError, "Protected"):
                authorize(self.root, self.envelope, [relative])
        self.assertEqual(normalize_path("docs\\Türkçe.md"), "docs/Türkçe.md")
        with self.assertRaisesRegex(GuardError, "duplicate case"):
            authorize(self.root, self.envelope, ["docs/A.md", "docs/a.md"])

    def test_windows_trailing_aliases_reserved_devices_and_wildcards_denied(self):
        invalid = ("docs/.. /AGENTS.md", "docs/file.md.", "docs/file.md ", "docs/NUL.txt", "docs/COM1",
                   "docs/lpt².log", "docs/conout$", "docs/*.md", "docs/file?.md", "docs/file\nname.md")
        for relative in invalid:
            with self.subTest(path=relative), self.assertRaises(GuardError):
                authorize(self.root, self.envelope, [relative])

    def directory_link(self, target, link):
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                raise
            # NTFS junction creation needs no symlink privilege. No shell deletion.
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_real_directory_links_cannot_escape_root_or_owner_scope(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        self.directory_link(outside, self.root / "docs" / "escape")
        with self.assertRaisesRegex(GuardError, "escapes"):
            authorize(self.root, self.envelope, ["docs/escape/file.md"], "docs_author")
        private = self.root / "private"
        private.mkdir()
        self.directory_link(private, self.root / "docs" / "alias")
        with self.assertRaisesRegex(GuardError, "outside allowed_write"):
            authorize(self.root, self.envelope, ["docs/alias/file.md"], "docs_author")
        self.directory_link(self.root, self.root / "docs" / "control_alias")
        with self.assertRaisesRegex(GuardError, "Protected"):
            authorize(self.root, self.envelope, ["docs/control_alias/AGENTS.md"])

    def test_unknown_owner_bad_scope_and_missing_protection_fail(self):
        with self.assertRaisesRegex(GuardError, "Unknown scope owner"):
            authorize(self.root, self.envelope, ["docs/a.md"], "nonexistent")
        for scopes in ([], ["../escape/"], ["docs/", "DOCS/"]):
            with self.subTest(scopes=scopes):
                self.envelope["allowed_write"] = scopes
                self.write_state()
                with self.assertRaises(GuardError):
                    self.current_session()
        self.envelope["allowed_write"] = ["docs/"]
        self.envelope["protected"] = ["AGENTS.md"]
        self.write_state()
        with self.assertRaisesRegex(GuardError, "protect all"):
            self.current_session()

    def test_commit_lease_integrates_other_owners_exact_staged_paths_only(self):
        (self.root / "docs" / "a.md").write_text("Scoped integration\n", encoding="utf-8")
        self.git("add", "docs/a.md")
        base = ("action", "--task-id", "TEST-1", "--kind", "commit")
        passed = self.run_cli("session_guard.py", *base, "--owner", "root", "--paths", "docs/a.md")
        self.assertEqual(passed.returncode, 0, passed.stderr)
        for extra in (("--paths", "docs/a.md"), ("--owner", "docs_author", "--paths", "docs/a.md"),
                      ("--owner", "root", "--paths", "docs/missing.md")):
            with self.subTest(args=extra):
                rejected = self.run_cli("session_guard.py", *base, *extra)
                self.assertNotEqual(rejected.returncode, 0)
        (self.root / "private.md").write_text("Unauthorized staged path\n", encoding="utf-8")
        self.git("add", "private.md")
        rejected = self.run_cli("session_guard.py", *base, "--owner", "root", "--paths", "docs/a.md", "private.md")
        self.assertNotEqual(rejected.returncode, 0)

    def test_cli_root_after_subcommand_and_external_state_denied(self):
        result = subprocess.run([sys.executable, str(SOURCE_ROOT / "tools" / "session_guard.py"), "resume", "--root", str(self.root),
                                 "--task-id", "TEST-1"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no claim", json.loads(result.stdout)["limitation"])
        with self.assertRaisesRegex(GuardError, "inside this repository"):
            session(self.root, Path(self.temp.name) / "outside.json", self.checkpoint_path, "TEST-1")
        rejected = self.run_cli("session_guard.py", "resume", "--task-id", "../TEST-1")
        self.assertNotEqual(rejected.returncode, 0)

    def test_checker_bootstrap_and_substantive_repository_validation(self):
        result = self.run_cli("check_repo.py", "--verify-bootstrap", "--policy-epoch", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["policy_epoch"], self.envelope["policy_epoch"])
        with self.assertRaisesRegex(GuardError, "Missing/empty"):
            check_repository(self.root)
        for directory in ("docs", "prompts", "templates", "kaizen", "projects"):
            shutil.copytree(SOURCE_ROOT / directory, self.root / directory, dirs_exist_ok=True)
        checked = check_repository(self.root)
        self.assertGreaterEqual(checked["documents_checked"], 20)
        self.assertGreaterEqual(checked["json_templates_checked"], 6)
        (self.root / "templates" / "TARGET_PROFILE.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(GuardError, "Empty JSON"):
            check_repository(self.root)


if __name__ == "__main__":
    unittest.main()
