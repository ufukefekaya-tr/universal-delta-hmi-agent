# SPDX-License-Identifier: Apache-2.0
"""Durable intent log. It authenticates no external vendor receipt."""
import json
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import uuid
from .file_ownership import immutable_read, worker_lease
from .common import canonical, engine_identity, hash_value, no_links, now, require, sha

TERMINAL = {'SUCCEEDED', 'FAILED', 'TIMED_OUT'}


class Journal:
    def __init__(self, workspace):
        self.workspace = no_links(workspace).resolve(strict=True)
        state = no_links(self.workspace / '.runtime')
        state.mkdir(exist_ok=True)
        self.path = no_links(state / 'operations.sqlite3')
        require(not self.path.exists() or self.path.stat().st_nlink == 1, 'STATE_LINK', 'Journal must not be hardlinked')
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY,value TEXT NOT NULL)')
            previous = db.execute('SELECT value FROM metadata WHERE name=?', ('engine_sha256',)).fetchone()
            self.engine_sha256 = engine_identity()
            require(previous is None or previous[0] == self.engine_sha256, 'ENGINE_DRIFT', 'Workspace journal belongs to different engine bytes; preserve it and use a new workspace')
            if previous is None:
                db.execute('INSERT INTO metadata VALUES (?,?)', ('engine_sha256', self.engine_sha256))
            db.execute('CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, record BLOB NOT NULL, candidate BLOB NOT NULL, profile BLOB NOT NULL, steps BLOB NOT NULL, parent TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, intent BLOB NOT NULL, state TEXT NOT NULL, result BLOB, created TEXT NOT NULL, updated TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT NOT NULL, state TEXT NOT NULL, record BLOB NOT NULL)')

    @contextmanager
    def connect(self):
        no_links(self.path)
        for suffix in ('-journal', '-wal', '-shm'):
            no_links(str(self.path) + suffix)
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute('PRAGMA synchronous=FULL')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def save_plan(self, plan_id, plan, parent):
        hash_value(plan_id)
        values = (plan_id, canonical(plan['record']), plan['candidate'], canonical(plan['profile']), canonical(plan['steps']), parent)
        require(sha(values[1]) == plan_id, 'PLAN_DRIFT', 'Record no longer identifies immutable plan')
        require(sha(values[2]) == plan['record']['candidate_sha256']
                and sha(values[3]) == plan['record']['candidate_profile_sha256']
                and sha(values[4]) == plan['record']['ledger_sha256'], 'PLAN_DRIFT', 'Plan payload/profile/ledger drift')
        with self.connect() as db:
            old = db.execute('SELECT * FROM plans WHERE id=?', (plan_id,)).fetchone()
            require(old is None or tuple(old) == values, 'PLAN_DRIFT', 'Durable plan identity already holds other bytes')
            if old is None:
                db.execute('INSERT INTO plans VALUES (?,?,?,?,?,?)', values)

    def load_plan(self, plan_id):
        hash_value(plan_id)
        with self.connect() as db:
            row = db.execute('SELECT * FROM plans WHERE id=?', (plan_id,)).fetchone()
        require(row is not None, 'PLAN_UNKNOWN', 'No durable plan with this identity')
        result = {'record': json.loads(row[1]), 'candidate': bytes(row[2]), 'profile': json.loads(row[3]), 'steps': json.loads(row[4])}
        require(sha(canonical(result['record'])) == plan_id
                and sha(result['candidate']) == result['record']['candidate_sha256']
                and sha(canonical(result['profile'])) == result['record']['candidate_profile_sha256']
                and sha(canonical(result['steps'])) == result['record']['ledger_sha256'], 'PLAN_DRIFT', 'Durable plan was altered')
        return result, row[5]

    def reserve(self, request_key, kind, intent):
        identity = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            require(db.execute('SELECT id FROM operations WHERE request_key=?', (request_key,)).fetchone() is None,
                    'REPLAY_OR_UNKNOWN', 'Request already exists; inspect/reconcile it instead of replaying')
            stamp = now()
            db.execute('INSERT INTO operations VALUES (?,?,?,?,?,?,?,?)',
                       (identity, request_key, kind, canonical(intent), 'PREPARED', None, stamp, stamp))
            db.execute('INSERT INTO events(operation_id,state,record) VALUES (?,?,?)', (identity, 'PREPARED', canonical(intent)))
        return identity

    def transition(self, identity, state, result=None):
        require(state in TERMINAL | {'RUNNING', 'UNKNOWN_OUTCOME'}, 'OPERATION_STATE', 'Unknown operation state')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT state FROM operations WHERE id=?', (identity,)).fetchone()
            require(row is not None and row[0] not in TERMINAL, 'OPERATION_STATE', 'Absent or terminal operation cannot transition')
            require(state != 'RUNNING' or row[0] == 'PREPARED', 'OPERATION_STATE', 'Worker can start only a prepared operation')
            require(state != 'SUCCEEDED' or row[0] in ('RUNNING', 'UNKNOWN_OUTCOME'),
                    'OPERATION_STATE', 'Prepared intent alone cannot establish success')
            raw = canonical(result or {})
            db.execute('UPDATE operations SET state=?,result=?,updated=? WHERE id=?', (state, raw, now(), identity))
            db.execute('INSERT INTO events(operation_id,state,record) VALUES (?,?,?)', (identity, state, raw))

    def inspect(self, identity):
        with self.connect() as db:
            row = db.execute('SELECT id,kind,intent,state,result FROM operations WHERE id=?', (identity,)).fetchone()
        require(row is not None, 'OPERATION_UNKNOWN', 'Operation not found')
        return dict(operation_id=row[0], kind=row[1], intent=json.loads(row[2]), state=row[3],
                    result=json.loads(row[4]) if row[4] else None)

    def find(self, request_key):
        with self.connect() as db:
            row = db.execute('SELECT id FROM operations WHERE request_key=?', (request_key,)).fetchone()
        return self.inspect(row[0]) if row else None

    def reconcile_save(self, identity):
        with worker_lease(self.workspace):
            return self._reconcile_save_owned(identity)

    def _reconcile_save_owned(self, identity):
        require(engine_identity() == self.engine_sha256, 'ENGINE_DRIFT', 'Recovery engine changed')
        operation = self.inspect(identity)
        if operation['state'] in TERMINAL:
            return operation
        intent = operation['intent']
        require(operation['kind'] == 'save_as', 'RECONCILE_UNSUPPORTED', 'Only file-save effects have an implemented reconciliation oracle')
        with self.connect() as db:
            started = db.execute('SELECT 1 FROM events WHERE operation_id=? AND state=?', (identity, 'RUNNING')).fetchone()
        if not started:
            if operation['state'] != 'UNKNOWN_OUTCOME':
                self.transition(identity, 'UNKNOWN_OUTCOME', {'reason': 'UNOWNED_OUTPUT_FOR_PREPARED_INTENT'})
            return self.inspect(identity)
        relative = Path(intent['path'])
        output = no_links(self.workspace / relative)
        source = no_links(self.workspace / intent['source_path'])
        require(not relative.is_absolute() and output.resolve().is_relative_to(self.workspace)
                and source.resolve().is_relative_to(self.workspace), 'PATH_SCOPE', 'Recorded path escapes workspace')
        if output.is_file() and source.is_file():
            with immutable_read(source) as (source_raw,source_unchanged), immutable_read(output) as (saved,output_unchanged):
                if sha(saved) == intent['candidate_sha256'] and sha(source_raw) == intent['source_sha256']:
                    plan, _ = self.load_plan(intent['plan_sha256'])
                    require(plan['record']['source_sha256'] == intent['source_sha256']
                            and plan['record']['candidate_sha256'] == intent['candidate_sha256']
                            and plan['candidate'] == saved, 'PLAN_DRIFT', 'Saved effect differs from durable plan')
                    from universal_diascreen_hmi.native import Project
                    Project(saved);source_unchanged();output_unchanged()
                    self.transition(identity, 'SUCCEEDED', {'saved_reread': 'PASS', 'reconciled': True,
                        'candidate_sha256': intent['candidate_sha256'], 'vendor_compile': 'NOT_RUN', 'native_qualified':False})
                    return self.inspect(identity)
        if operation['state'] != 'UNKNOWN_OUTCOME':
            self.transition(identity, 'UNKNOWN_OUTCOME', {'reason': 'MISSING_OR_DIFFERENT_SOURCE_OR_OUTPUT'})
        return self.inspect(identity)
