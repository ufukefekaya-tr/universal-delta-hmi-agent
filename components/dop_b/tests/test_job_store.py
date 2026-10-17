"""Real SQLite queue/restart tests; no vendor or external services."""
from concurrent.futures import ThreadPoolExecutor
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from universal_hmi.errors import HmiError
from universal_hmi.job_store import JobStore, MAX_JSON_BYTES


class JobStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="uhmi-jobs-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state"
        self.now = 1000.0
        self.store = JobStore(self.path, clock=lambda: self.now)

    def submit(self, key="example"):
        return self.store.submit(key, {"design": "neutral", "revision": 1})["job_id"]

    def error(self, code, call, *args, **kwargs):
        with self.assertRaises(HmiError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_restart_retains_payload_idempotency_details_and_attempts(self):
        job = self.submit()
        self.assertTrue(self.store.claim(job, "first", 20))
        self.store.transition(job, "first", "WAITING_REVIEWS", {"stage": "technical"})
        restarted = JobStore(self.path, clock=lambda: self.now)
        self.assertEqual(restarted.payload(job), {"design": "neutral", "revision": 1})
        record = restarted.submit("example", {"revision": 1, "design": "neutral"})
        self.assertEqual(record["job_id"], job)
        self.assertEqual(record["status"], "WAITING_REVIEWS")
        self.assertEqual(record["details"], {"stage": "technical"})
        self.assertTrue(restarted.claim(job, "second"))
        self.assertEqual(restarted.status(job)["attempts"], 2)
        self.error("JOB_KEY_CONFLICT", restarted.submit, "example", {"revision": 2})

    def test_concurrent_same_key_submit_is_one_durable_job(self):
        def submit(_):
            return JobStore(self.path).submit("same", {"a": [1, 2], "b": True})["job_id"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(submit, range(24)))
        self.assertEqual(len(set(ids)), 1)

    def test_concurrent_conflicting_submit_has_single_winner(self):
        def submit(value):
            try:
                return JobStore(self.path).submit("same", {"value": value})["job_id"]
            except HmiError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(submit, [1, 2]))
        self.assertEqual(result.count("JOB_KEY_CONFLICT"), 1)

    def test_global_single_execution_lease_across_instances(self):
        jobs = [self.submit("a"), self.submit("b")]
        other = JobStore(self.path, clock=lambda: self.now)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda pair: pair[0].claim(pair[1], pair[1]),
                                    [(self.store, jobs[0]), (other, jobs[1])]))
        self.assertEqual(sum(results), 1)
        winner = jobs[results.index(True)]
        loser = jobs[results.index(False)]
        self.assertFalse(other.claim(winner, winner))
        self.store.transition(winner, winner, "COMPLETED")
        self.assertTrue(other.claim(loser, "next"))

    def test_expired_lease_recovery_fences_previous_worker(self):
        job = self.submit()
        self.store.claim(job, "old", 10)
        self.now += 10
        self.error("JOB_LEASE_LOST", self.store.heartbeat, job, "old")
        self.error("JOB_LEASE_LOST", self.store.transition, job, "old", "COMPLETED")
        restarted = JobStore(self.path, clock=lambda: self.now)
        self.assertTrue(restarted.claim(job, "new"))
        self.error("JOB_LEASE_LOST", self.store.transition, job, "old", "FAILED")
        self.assertEqual(restarted.status(job)["attempts"], 2)

    def test_process_crash_preserves_claim_and_can_recover(self):
        script = """import os, sys
from universal_hmi.job_store import JobStore
store = JobStore(sys.argv[1], clock=lambda: 1000)
job = store.submit('crash', {'saved': True})['job_id']
assert store.claim(job, 'crashed-process', 10)
os._exit(17)
"""
        result = subprocess.run([sys.executable, "-c", script, str(self.path)], capture_output=True)
        self.assertEqual(result.returncode, 17, result.stderr)
        job = self.store.submit("crash", {"saved": True})["job_id"]
        self.assertFalse(self.store.claim(job, "recovery"))
        self.now = 1010
        self.assertTrue(self.store.claim(job, "recovery"))
        self.assertEqual(self.store.status(job)["attempts"], 2)

    def test_heartbeat_renews_lease_and_wrong_owner_is_rejected(self):
        job = self.submit()
        self.store.claim(job, "owner", 10)
        self.now += 9
        self.error("JOB_LEASE_LOST", self.store.heartbeat, job, "outsider")
        self.assertEqual(self.store.heartbeat(job, "owner")["lease_expires_at"], 1019)
        self.now += 2
        self.assertFalse(self.store.claim(job, "new"))
        self.now -= 5
        record = self.store.heartbeat(job, "owner")
        self.assertEqual(record["lease_expires_at"], 1019)
        self.assertEqual(record["updated_at"], 1009)

    def test_cancel_fences_worker_and_does_not_revive(self):
        for initial in ("QUEUED", "RUNNING", "WAITING_REVIEWS"):
            job = self.submit(initial)
            if initial != "QUEUED":
                self.store.claim(job, "worker")
            if initial == "WAITING_REVIEWS":
                self.store.transition(job, "worker", initial)
            self.assertEqual(self.store.cancel(job)["status"], "CANCELLED")
            self.assertEqual(self.store.cancel(job)["status"], "CANCELLED")
            self.assertFalse(self.store.claim(job, "new"))
            self.error("JOB_LEASE_LOST", self.store.transition, job, "worker", "COMPLETED")

    def test_illegal_transitions_and_terminal_states(self):
        job = self.submit()
        self.error("JOB_LEASE_LOST", self.store.transition, job, "worker", "COMPLETED")
        self.store.claim(job, "worker")
        for target in ("QUEUED", "RUNNING", "INVALID", [], None):
            self.error("JOB_TRANSITION_INVALID", self.store.transition, job, "worker", target)
        self.store.transition(job, "worker", "COMPLETED")
        self.error("JOB_TRANSITION_INVALID", self.store.cancel, job)
        self.assertFalse(self.store.claim(job, "next"))
        failed = self.submit("failed")
        self.store.claim(failed, "worker")
        self.store.transition(failed, "worker", "FAILED")
        self.assertFalse(self.store.claim(failed, "next"))

    def test_finite_bounded_strict_json(self):
        cyclic = {}; cyclic["self"] = cyclic
        deep = {}
        for _ in range(66):
            deep = {"child": deep}
        for payload in ({"n": math.nan}, {"n": math.inf}, {1: "x"}, {"x": (1,)},
                        {"x": "\ud800"}, {"x": "x" * (MAX_JSON_BYTES + 1)},
                        {"x": [None] * 100_001}, cyclic, deep, []):
            self.error("JOB_INPUT_INVALID", self.store.submit, "bad", payload)
        job = self.submit()
        self.store.claim(job, "owner")
        self.error("JOB_INPUT_INVALID", self.store.transition, job, "owner", "COMPLETED", {"n": math.nan})
        self.assertEqual(self.store.status(job)["status"], "RUNNING")

    def test_identifiers_and_lease_validation(self):
        for job in ("../escape", "a" * 31, "A" * 32, [], None):
            self.error("JOB_ID_INVALID", self.store.status, job)
        self.error("JOB_NOT_FOUND", self.store.status, "a" * 32)
        for key in ("", "x" * 257, "bad\nkey", "\ud800", None):
            self.error("JOB_INPUT_INVALID", self.store.submit, key, {})
        job = self.submit()
        for duration in (0, -1, math.nan, math.inf, 86401, 10 ** 400, True, "1"):
            self.error("JOB_INPUT_INVALID", self.store.claim, job, "owner", duration)
        self.error("JOB_INPUT_INVALID", self.store.claim, job, "")

    def test_invalid_clock_does_not_write_job(self):
        self.now = math.nan
        self.error("JOB_CLOCK_INVALID", self.store.submit, "bad", {})

    def test_state_path_rejects_file_directory_and_hardlinked_database(self):
        file_path = Path(self.temp.name) / "file"
        file_path.write_text("not a directory")
        self.error("JOB_STATE_PATH", JobStore, file_path)
        link = Path(self.temp.name) / "db-link"
        os.link(self.store.db_path, link)
        self.error("JOB_STATE_PATH", self.store.submit, "x", {})

    def test_state_path_rejects_symbolic_link_or_windows_junction(self):
        link = Path(self.temp.name) / "linked-state"
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(self.path)], check=True, capture_output=True)
        else:
            link.symlink_to(self.path, target_is_directory=True)
        try:
            self.error("JOB_STATE_PATH", JobStore, link)
            self.error("JOB_STATE_PATH", JobStore, link / "child")
        finally:
            if os.name == "nt":
                link.rmdir()
            else:
                link.unlink()

    def test_budget_accumulates_across_attempts_and_excludes_wait(self):
        job = self.store.submit("budget", {}, max_seconds=15)["job_id"]
        self.store.claim(job, "one", 60)
        self.now += 5
        self.store.heartbeat(job, "one")
        self.now += 2
        waiting = self.store.transition(job, "one", "WAITING_REVIEWS")
        self.assertEqual(waiting["active_seconds"], 7)
        self.now += 100
        self.assertEqual(self.store.status(job)["active_seconds"], 7)
        restarted = JobStore(self.path, clock=lambda: self.now)
        self.assertTrue(restarted.claim(job, "two"))
        self.now += 8
        self.assertEqual(restarted.status(job)["active_seconds"], 15)
        self.error("JOB_BUDGET_EXCEEDED", restarted.heartbeat, job, "two")
        self.error("JOB_BUDGET_EXCEEDED", restarted.pin_publication, job, "two", "a" * 64)
        self.error("JOB_BUDGET_EXCEEDED", restarted.transition, job, "two", "COMPLETED")
        self.assertEqual(restarted.transition(job, "two", "FAILED")["max_seconds"], 15)

    def test_crashed_lease_is_charged_and_exhaustion_is_durable(self):
        job = self.store.submit("crash-budget", {}, max_seconds=10)["job_id"]
        self.store.claim(job, "crashed", 10)
        self.now += 1000
        self.assertEqual(self.store.status(job)["active_seconds"], 10)
        self.assertFalse(self.store.claim(job, "new"))
        failed = JobStore(self.path, clock=lambda: self.now).status(job)
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(failed["details"]["error"]["code"], "JOB_BUDGET_EXCEEDED")
        self.error("JOB_KEY_CONFLICT", self.store.submit, "crash-budget", {}, max_seconds=20)
        self.error("JOB_KEY_CONFLICT", self.store.submit, "crash-budget", {})

    def test_supervisor_enforces_budget_and_releases_global_lease(self):
        job = self.store.submit("supervised", {}, max_seconds=5)["job_id"]
        other = self.submit("next")
        self.store.claim(job, "worker", 60)
        self.now += 4
        before = self.store.status(job)
        self.assertEqual(self.store.enforce_budget(job), before)
        self.now += 1
        stopped = self.store.enforce_budget(job)
        self.assertEqual(stopped["status"], "FAILED")
        self.assertEqual(stopped["active_seconds"], 5)
        self.assertIsNone(stopped["owner"])
        self.assertIsNone(stopped["lease_expires_at"])
        self.assertEqual(stopped["details"]["error"]["code"], "JOB_BUDGET_EXCEEDED")
        self.assertEqual(JobStore(self.path, clock=lambda: self.now).enforce_budget(job), stopped)
        self.error("JOB_LEASE_LOST", self.store.heartbeat, job, "worker")
        self.assertTrue(self.store.claim(other, "next-worker"))

    def test_supervisor_preserves_pinned_publication_and_unlimited_jobs(self):
        job = self.store.submit("pinned", {}, max_seconds=5)["job_id"]
        self.store.claim(job, "worker", 10)
        self.store.pin_publication(job, "worker", "a" * 64)
        self.now += 10
        before = self.store.status(job)
        self.assertEqual(self.store.enforce_budget(job), before)
        self.assertTrue(self.store.claim(job, "recovery"))
        self.store.publish(job, "recovery", "a" * 64, lambda: {})
        unlimited = self.submit("unlimited")
        self.store.claim(unlimited, "worker", 60)
        self.now += 100
        self.assertEqual(self.store.enforce_budget(unlimited)["status"], "RUNNING")

    def test_pending_enumerates_dispatchable_jobs(self):
        queued, waiting, expired = [self.submit(key) for key in ("queued", "waiting", "expired")]
        self.store.claim(waiting, "worker")
        self.store.transition(waiting, "worker", "WAITING_REVIEWS")
        self.store.claim(expired, "worker", 10)
        self.assertEqual({r["job_id"] for r in self.store.pending()}, {queued, waiting})
        self.now += 10
        self.assertEqual({r["job_id"] for r in self.store.pending()}, {queued, waiting, expired})
        self.assertEqual({r["job_id"] for r in self.store.pending(include_waiting=False)}, {queued, expired})
        self.assertEqual(len(self.store.pending(limit=1)), 1)
        self.error("JOB_INPUT_INVALID", self.store.pending, limit=0)

    def test_has_unfinished_includes_crashed_worker_with_unexpired_lease(self):
        self.assertFalse(self.store.has_unfinished())
        script = """import os, sys
from universal_hmi.job_store import JobStore
store = JobStore(sys.argv[1], clock=lambda: 1000)
job = store.submit('unfinished-crash', {})['job_id']
assert store.claim(job, 'crashed-process', 10)
os._exit(17)
"""
        result = subprocess.run([sys.executable, "-c", script, str(self.path)], capture_output=True)
        self.assertEqual(result.returncode, 17, result.stderr)
        restarted = JobStore(self.path, clock=lambda: self.now)
        self.assertTrue(restarted.has_unfinished())
        self.assertEqual(restarted.pending(), [])
        job = restarted.submit("unfinished-crash", {})["job_id"]
        restarted.cancel(job)
        self.assertFalse(restarted.has_unfinished())

    def test_has_unfinished_covers_waiting_and_excludes_all_terminal_states(self):
        job = self.submit("unfinished")
        self.assertTrue(self.store.has_unfinished())
        self.store.claim(job, "worker")
        self.store.transition(job, "worker", "WAITING_REVIEWS")
        self.assertTrue(self.store.has_unfinished())
        self.store.claim(job, "worker-again")
        self.store.transition(job, "worker-again", "COMPLETED")
        self.assertFalse(self.store.has_unfinished())
        failed = self.submit("failed-unfinished")
        self.store.claim(failed, "worker")
        self.store.transition(failed, "worker", "FAILED")
        self.assertFalse(self.store.has_unfinished())

    def test_publication_pin_is_durable_immutable_and_closes_cancel(self):
        job = self.submit()
        self.store.claim(job, "owner")
        self.assertIsNone(self.store.publication_intent(job))
        self.error("JOB_PUBLICATION_CONFLICT", self.store.publish, job, "owner", "a" * 64, lambda: {})
        self.store.pin_publication(job, "owner", "a" * 64)
        self.assertEqual(JobStore(self.path).publication_intent(job), "a" * 64)
        self.store.pin_publication(job, "owner", "a" * 64)
        self.error("JOB_PUBLICATION_CONFLICT", self.store.pin_publication, job, "owner", "b" * 64)
        self.error("JOB_PUBLICATION_PENDING", self.store.cancel, job)
        self.error("JOB_PUBLICATION_PENDING", self.store.transition, job, "owner", "FAILED")
        self.error("JOB_PUBLICATION_CONFLICT", self.store.publish, job, "owner", "b" * 64, lambda: {})
        result = self.store.publish(job, "owner", "a" * 64, lambda: {"manifest_sha256": "a" * 64})
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["details"]["manifest_sha256"], "a" * 64)

    def test_publication_serializes_cancel_and_claim(self):
        job, other_job = self.submit(), self.submit("other")
        self.store.claim(job, "owner")
        self.store.pin_publication(job, "owner", "a" * 64)
        entered, proceed, cancel_started, claim_started = [threading.Event() for _ in range(4)]
        other = JobStore(self.path, clock=lambda: self.now)

        def callback():
            entered.set()
            if not proceed.wait(5):
                raise AssertionError("Publication synchronization timed out")
            return {"published": True}

        def cancel():
            cancel_started.set()
            try:
                other.cancel(job)
            except HmiError as exc:
                return exc.code

        def claim():
            claim_started.set()
            return other.claim(other_job, "other-owner")

        with ThreadPoolExecutor(max_workers=3) as pool:
            publication = pool.submit(self.store.publish, job, "owner", "a" * 64, callback)
            self.assertTrue(entered.wait(5))
            cancellation, next_claim = pool.submit(cancel), pool.submit(claim)
            self.assertTrue(cancel_started.wait(5))
            self.assertTrue(claim_started.wait(5))
            self.assertFalse(cancellation.done())
            self.assertFalse(next_claim.done())
            proceed.set()
            self.assertEqual(publication.result()["status"], "COMPLETED")
            self.assertEqual(cancellation.result(), "JOB_TRANSITION_INVALID")
            self.assertTrue(next_claim.result())

    def test_callback_exception_retains_recoverable_intent(self):
        job = self.submit()
        self.store.claim(job, "owner", 10)
        self.store.pin_publication(job, "owner", "a" * 64)
        def callback():
            raise OSError("rename failed")
        with self.assertRaises(OSError):
            self.store.publish(job, "owner", "a" * 64, callback)
        self.assertEqual(self.store.status(job)["status"], "RUNNING")
        self.assertEqual(self.store.publication_intent(job), "a" * 64)
        self.now += 10
        self.assertTrue(self.store.claim(job, "new"))
        self.assertEqual(self.store.publish(job, "new", "a" * 64, lambda: {})["status"], "COMPLETED")

    def test_crash_after_rename_reconciles_pinned_output_despite_spent_budget(self):
        target = Path(self.temp.name) / "manifest.json"
        script = """import hashlib, os, sys
from pathlib import Path
from universal_hmi.job_store import JobStore
store = JobStore(sys.argv[1], clock=lambda: 1000)
job = store.submit('publication-crash', {}, max_seconds=5)['job_id']
assert store.claim(job, 'crashed-process', 10)
sha = hashlib.sha256(b'{}').hexdigest()
store.pin_publication(job, 'crashed-process', sha)
def publish():
    target = Path(sys.argv[2])
    temp = target.with_suffix('.tmp')
    temp.write_bytes(b'{}')
    temp.rename(target)
    os._exit(17)
store.publish(job, 'crashed-process', sha, publish)
"""
        result = subprocess.run([sys.executable, "-c", script, str(self.path), str(target)], capture_output=True)
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(target.read_bytes(), b"{}")
        self.now += 10
        restarted = JobStore(self.path, clock=lambda: self.now)
        record = restarted.submit("publication-crash", {}, max_seconds=5)
        job, sha = record["job_id"], record["publication_sha256"]
        self.assertEqual(record["status"], "RUNNING")
        self.assertEqual(record["active_seconds"], 10)
        self.error("JOB_PUBLICATION_PENDING", restarted.cancel, job)
        self.assertTrue(restarted.claim(job, "reconcile"))
        def reconcile():
            import hashlib
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), sha)
            return {"reconciled": True}
        self.assertEqual(restarted.publish(job, "reconcile", sha, reconcile)["status"], "COMPLETED")

    def test_publication_does_not_rollback_after_callback_crosses_lease_deadline(self):
        job = self.submit()
        self.store.claim(job, "owner", 10)
        self.store.pin_publication(job, "owner", "a" * 64)
        def callback():
            self.now += 11
            return {"published": True}
        self.assertEqual(self.store.publish(job, "owner", "a" * 64, callback)["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
