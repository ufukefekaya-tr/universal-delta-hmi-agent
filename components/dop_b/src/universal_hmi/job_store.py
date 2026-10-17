"""Durable local queue. A lease owner must be unique to one execution attempt.

SQLite serializes writers across processes; leases use persisted UTC wall-clock
seconds so they survive restarts. A backward clock adjustment conservatively
delays recovery. Publication pins are durable commit intentions: after pinning,
cancellation closes and only idempotent publication recovery may complete a job.
The publish callback runs with the database write lock, must be bounded, and
must not call back into this store. It verifies/renames only the pinned artifact.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
import uuid

from .errors import HmiError


STATES = frozenset({"QUEUED", "RUNNING", "WAITING_REVIEWS", "COMPLETED", "FAILED", "CANCELLED"})
TERMINAL = frozenset({"COMPLETED", "FAILED", "CANCELLED"})
MAX_JSON_BYTES = 8 * 1024 * 1024


def _json(value: dict) -> str:
    if type(value) is not dict:
        raise HmiError("JOB_INPUT_INVALID", "Job JSON must be an object")
    pending = [(value, 0)]
    count = 0
    text_size = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 64 or count > 100_000:
            raise HmiError("JOB_INPUT_INVALID", "Job JSON exceeds depth/node limits")
        if type(item) is dict:
            if count + len(pending) + 2 * len(item) > 100_000:
                raise HmiError("JOB_INPUT_INVALID", "Job JSON exceeds node limit")
            if any(type(key) is not str for key in item):
                raise HmiError("JOB_INPUT_INVALID", "Job JSON keys must be strings")
            pending.extend((key, depth + 1) for key in item)
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            if count + len(pending) + len(item) > 100_000:
                raise HmiError("JOB_INPUT_INVALID", "Job JSON exceeds node limit")
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            text_size += len(item)
            if text_size > MAX_JSON_BYTES:
                raise HmiError("JOB_INPUT_INVALID", "Job JSON exceeds byte limit")
        elif item is None or type(item) in (bool, int):
            pass
        elif type(item) is float and math.isfinite(item):
            pass
        else:
            raise HmiError("JOB_INPUT_INVALID", "Only finite JSON values are accepted")
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_JSON_BYTES:
            raise HmiError("JOB_INPUT_INVALID", "Job JSON exceeds byte limit")
        return encoded
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise HmiError("JOB_INPUT_INVALID", "Job JSON cannot be encoded") from exc


def _label(value: str, name: str) -> str:
    if type(value) is not str or not value or len(value) > 256 or any(ord(c) < 32 for c in value):
        raise HmiError("JOB_INPUT_INVALID", f"Invalid {name}")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise HmiError("JOB_INPUT_INVALID", f"Invalid {name} encoding") from exc
    return value


class JobStore:
    def __init__(self, state_dir, *, clock=time.time):
        self.state_dir = Path(os.path.abspath(os.fspath(state_dir)))
        self.db_path = self.state_dir / "jobs.sqlite3"
        self.clock = clock
        self._check_paths()
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._check_paths()
        if os.name != "nt":
            self.state_dir.chmod(0o700)
        with self._transaction() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY, key TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN
                    ('QUEUED','RUNNING','WAITING_REVIEWS','COMPLETED','FAILED','CANCELLED')),
                attempts INTEGER NOT NULL DEFAULT 0,
                owner TEXT, lease_expires_at REAL, lease_seconds REAL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                details TEXT NOT NULL DEFAULT '{}')""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
            for name, definition in (("publication_sha256", "TEXT"), ("max_seconds", "REAL"),
                                     ("active_seconds", "REAL NOT NULL DEFAULT 0"), ("run_started_at", "REAL")):
                if name not in columns:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        if os.name != "nt":
            self.db_path.chmod(0o600)

    def _check_paths(self):
        # Do not resolve first: doing so would hide symlink/junction traversal.
        for path in (*reversed(self.state_dir.parents), self.state_dir,
                     self.db_path, Path(str(self.db_path) + "-journal"),
                     Path(str(self.db_path) + "-wal"), Path(str(self.db_path) + "-shm")):
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise HmiError("JOB_STATE_PATH", "State paths cannot traverse links or reparse points", path=str(path))
            if path == self.state_dir or path in self.state_dir.parents:
                valid = stat.S_ISDIR(info.st_mode)
            else:
                valid = stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            if not valid:
                raise HmiError("JOB_STATE_PATH", "State path has an unsafe file type", path=str(path))

    @contextmanager
    def _transaction(self):
        self._check_paths()
        db = None
        try:
            db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except sqlite3.Error as exc:
            raise HmiError("JOB_STORE_ERROR", "Durable job store operation failed") from exc
        finally:
            if db is not None:
                if db.in_transaction:
                    db.rollback()
                db.close()

    def _now(self):
        now = self.clock()
        if type(now) not in (int, float) or not 0 <= now <= 1e15:
            raise HmiError("JOB_CLOCK_INVALID", "Lease clock must provide finite nonnegative seconds")
        return float(now)

    @staticmethod
    def _row(db, job_id):
        if type(job_id) is not str or re.fullmatch(r"[0-9a-f]{32}", job_id) is None:
            raise HmiError("JOB_ID_INVALID", "Invalid job identifier")
        row = db.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise HmiError("JOB_NOT_FOUND", "Job was not found", job_id=job_id)
        return row

    @staticmethod
    def _active(row, now):
        active = row["active_seconds"]
        if row["status"] == "RUNNING" and row["run_started_at"] is not None:
            active += max(0, min(now, row["lease_expires_at"]) - row["run_started_at"])
        return active

    def _record(self, row):
        result = dict(row)
        result.pop("payload")
        result.pop("lease_seconds")
        result.pop("run_started_at")
        result["active_seconds"] = self._active(row, self._now())
        result["details"] = json.loads(result["details"])
        return result

    def _budget(self, row, now):
        # A pinned operation can only reconcile its immutable publication.
        if (row["publication_sha256"] is None and row["max_seconds"] is not None
                and self._active(row, now) >= row["max_seconds"]):
            raise HmiError("JOB_BUDGET_EXCEEDED", "Cumulative active execution budget is exhausted")

    @staticmethod
    def _sha(value):
        if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise HmiError("JOB_INPUT_INVALID", "Publication requires a lowercase SHA-256")
        return value

    def _finish(self, db, row, status, details, now):
        db.execute("""UPDATE jobs SET status=?,owner=NULL,lease_expires_at=NULL,lease_seconds=NULL,
                      run_started_at=NULL,active_seconds=?,details=?,updated_at=MAX(updated_at,?) WHERE job_id=?""",
                   (status, self._active(row, now), details, now, row["job_id"]))

    @staticmethod
    def _owned(row, owner, now):
        _label(owner, "lease owner")
        if row["status"] != "RUNNING" or row["owner"] != owner or row["lease_expires_at"] <= now:
            raise HmiError("JOB_LEASE_LOST", "Job requires the current unexpired execution lease")

    def submit(self, key: str, payload: dict, *, max_seconds=None) -> dict:
        _label(key, "idempotency key")
        encoded = _json(payload)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        if max_seconds is not None and (type(max_seconds) not in (int, float) or not 0 < max_seconds <= 1e9):
            raise HmiError("JOB_INPUT_INVALID", "Active execution budget must be finite positive seconds")
        with self._transaction() as db:
            existing = db.execute("SELECT * FROM jobs WHERE key = ?", (key,)).fetchone()
            if existing is not None:
                if existing["payload_sha256"] != digest or existing["max_seconds"] != max_seconds:
                    raise HmiError("JOB_KEY_CONFLICT", "Idempotency key already names different input")
                return self._record(existing)
            now = self._now()
            job_id = uuid.uuid4().hex
            db.execute("""INSERT INTO jobs (job_id,key,payload,payload_sha256,status,created_at,updated_at,max_seconds)
                          VALUES (?,?,?,?,'QUEUED',?,?,?)""", (job_id, key, encoded, digest, now, now, max_seconds))
            return self._record(self._row(db, job_id))

    def status(self, job_id: str) -> dict:
        with self._transaction() as db:
            return self._record(self._row(db, job_id))

    def payload(self, job_id: str) -> dict:
        with self._transaction() as db:
            return json.loads(self._row(db, job_id)["payload"])

    def has_unfinished(self) -> bool:
        """Include live leases so a dispatcher stays available for crash recovery."""
        with self._transaction() as db:
            return db.execute("SELECT 1 FROM jobs WHERE status IN ('QUEUED','RUNNING','WAITING_REVIEWS') LIMIT 1").fetchone() is not None

    def pending(self, limit=100, *, include_waiting=True) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 1000 or type(include_waiting) is not bool:
            raise HmiError("JOB_INPUT_INVALID", "Pending limit must be 1..1000 and include_waiting boolean")
        with self._transaction() as db:
            rows = db.execute("""SELECT * FROM jobs WHERE status='QUEUED'
                OR (status='WAITING_REVIEWS' AND ?) OR (status='RUNNING' AND lease_expires_at <= ?)
                ORDER BY created_at,job_id LIMIT ?""", (include_waiting, self._now(), limit)).fetchall()
            return [self._record(row) for row in rows]

    def enforce_budget(self, job_id: str) -> dict:
        """Trusted supervisor closure after stopping an over-budget worker.

        Serialized with claims/publication. This does not terminate processes;
        pinned publication always remains recoverable, including after timeout.
        """
        with self._transaction() as db:
            row = self._row(db, job_id)
            now = self._now()
            if row["status"] not in TERMINAL:
                try:
                    self._budget(row, now)
                except HmiError as exc:
                    self._finish(db, row, "FAILED", _json({"error": exc.as_dict()}), now)
            return self._record(self._row(db, job_id))

    def claim(self, job_id: str, owner: str, lease_seconds=60) -> bool:
        _label(owner, "lease owner")
        if type(lease_seconds) not in (int, float) or not 0 < lease_seconds <= 86400:
            raise HmiError("JOB_INPUT_INVALID", "Lease duration must be positive and at most one day")
        with self._transaction() as db:
            row = self._row(db, job_id)
            now = self._now()
            if row["status"] in TERMINAL:
                return False
            if db.execute("SELECT 1 FROM jobs WHERE status='RUNNING' AND lease_expires_at > ?", (now,)).fetchone():
                return False
            try:
                self._budget(row, now)
            except HmiError as exc:
                self._finish(db, row, "FAILED", _json({"error": exc.as_dict()}), now)
                return False
            db.execute("""UPDATE jobs SET status='RUNNING',owner=?,lease_expires_at=?,lease_seconds=?,
                          attempts=attempts+1,updated_at=MAX(updated_at,?),active_seconds=?,run_started_at=? WHERE job_id=?""",
                       (owner, now + lease_seconds, lease_seconds, now, self._active(row, now), now, job_id))
            return True

    def heartbeat(self, job_id: str, owner: str) -> dict:
        with self._transaction() as db:
            row = self._row(db, job_id)
            now = self._now()
            self._owned(row, owner, now)
            self._budget(row, now)
            db.execute("""UPDATE jobs SET lease_expires_at=MAX(lease_expires_at,?),updated_at=MAX(updated_at,?),
                       active_seconds=?,run_started_at=MAX(run_started_at,?) WHERE job_id=?""",
                       (now + row["lease_seconds"], now, self._active(row, now), now, job_id))
            return self._record(self._row(db, job_id))

    def transition(self, job_id: str, owner: str, status: str, details=None) -> dict:
        if type(status) is not str or status not in TERMINAL | {"WAITING_REVIEWS"}:
            raise HmiError("JOB_TRANSITION_INVALID", "Only a running job may wait for reviews or enter a terminal state")
        encoded = _json(details) if details is not None else None
        with self._transaction() as db:
            row = self._row(db, job_id)
            now = self._now()
            self._owned(row, owner, now)
            if row["publication_sha256"] is not None:
                raise HmiError("JOB_PUBLICATION_PENDING", "Pinned publication must finish through publish")
            if status not in {"FAILED", "CANCELLED"}:
                self._budget(row, now)
            self._finish(db, row, status, encoded if encoded is not None else row["details"], now)
            return self._record(self._row(db, job_id))

    def cancel(self, job_id: str) -> dict:
        with self._transaction() as db:
            row = self._row(db, job_id)
            if row["status"] == "CANCELLED":
                return self._record(row)
            if row["status"] in TERMINAL:
                raise HmiError("JOB_TRANSITION_INVALID", "A terminal job cannot be cancelled")
            if row["publication_sha256"] is not None:
                raise HmiError("JOB_PUBLICATION_PENDING", "Publication has committed to its immutable output; recovery is required")
            now = self._now()
            self._finish(db, row, "CANCELLED", row["details"], now)
            return self._record(self._row(db, job_id))

    def pin_publication(self, job_id: str, owner: str, expected_manifest_sha: str) -> dict:
        self._sha(expected_manifest_sha)
        with self._transaction() as db:
            row = self._row(db, job_id)
            now = self._now()
            self._owned(row, owner, now)
            self._budget(row, now)
            if row["publication_sha256"] not in (None, expected_manifest_sha):
                raise HmiError("JOB_PUBLICATION_CONFLICT", "Publication intent cannot change")
            db.execute("UPDATE jobs SET publication_sha256=?,updated_at=MAX(updated_at,?) WHERE job_id=?",
                       (expected_manifest_sha, now, job_id))
            return self._record(self._row(db, job_id))

    def publication_intent(self, job_id: str) -> str | None:
        with self._transaction() as db:
            return self._row(db, job_id)["publication_sha256"]

    def publish(self, job_id: str, owner: str, expected_manifest_sha: str, callback) -> dict:
        """Serialize bounded artifact publication against cancellation and claims.

        Pin first in a separate committed transaction. The callback must verify
        the manifest hash and output scope, then idempotently publish/reconcile.
        An exception rolls back database changes, never the durable pin; callers
        must leave the job recoverable. Do not perform new production work here.
        """
        self._sha(expected_manifest_sha)
        if not callable(callback):
            raise HmiError("JOB_INPUT_INVALID", "Publication callback must be callable")
        with self._transaction() as db:
            row = self._row(db, job_id)
            now = self._now()
            self._owned(row, owner, now)
            self._budget(row, now)
            if row["publication_sha256"] != expected_manifest_sha:
                raise HmiError("JOB_PUBLICATION_CONFLICT", "Publication must match an already committed intent")
            details = callback()
            encoded = row["details"] if details is None else _json(details)
            # Once callback publishes, time crossing cannot undo the filesystem.
            self._finish(db, row, "COMPLETED", encoded, now)
            return self._record(self._row(db, job_id))
