"""Host-installed task authority. Job JSON cannot install or widen this policy.

The OS account and the launcher own the trust boundary. This is not a sandbox
against another process running with the host administrator's privileges.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from .errors import HmiError


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, RecursionError) as exc:
        raise HmiError('JOB_JSON', 'Finite serializable JSON is required') from exc


def read_object(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise HmiError('JOB_JSON', 'Duplicate JSON keys are forbidden')
            result[key] = value
        return result
    try:
        with Path(path).open('rb') as handle:
            raw = handle.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise HmiError('JOB_JSON', 'JSON exceeds 8 MiB')
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(HmiError('JOB_JSON', 'Nonfinite JSON')))
        if not isinstance(value, dict):
            raise HmiError('JOB_JSON', 'JSON object required')
        canonical(value)
        return raw, value
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, HmiError):
            raise
        raise HmiError('JOB_JSON', 'Readable bounded JSON object required') from exc


def no_links(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise HmiError('JOB_PATH_LINK', 'Links and junctions are forbidden', path=str(part))
    return path


def relative_file(root, relative, *, exists=False):
    if (not isinstance(relative, str) or not relative or '\\' in relative
            or any(ord(c) < 32 or c in ':<>"|?*' for c in relative)
            or relative.startswith('/') or any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in relative.split('/'))):
        raise HmiError('JOB_PATH', 'Canonical relative path required')
    reserved = {'con', 'prn', 'aux', 'nul', 'conin$', 'conout$'} | {f'{p}{i}' for p in ('com', 'lpt') for i in range(10)}
    if any(p.split('.')[0].casefold() in reserved for p in PurePosixPath(relative).parts):
        raise HmiError('JOB_PATH', 'Device path forbidden')
    try:
        root = no_links(root).resolve(strict=True)
        path = no_links(root / relative)
        resolved = path.resolve(strict=exists)
    except OSError as exc:
        raise HmiError('JOB_PATH', 'Required root or source path is unavailable') from exc
    if not resolved.is_relative_to(root):
        raise HmiError('JOB_PATH', 'Path escapes its root')
    return path


def tree_digest(root):
    root = no_links(root).resolve(strict=True)
    entries = {}
    for path in sorted(root.rglob('*')):
        no_links(path)
        if path.is_file():
            entries[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    if not entries:
        raise HmiError('JOB_REGISTRY', 'Empty registry is not a qualified source')
    return digest(canonical(entries))


class TaskPolicy:
    """Loaded only from a launch argument, never from an MCP job argument."""
    FIELDS = {'schema_version', 'reference', 'workspace', 'profiles_root',
              'profile_tree_sha256', 'output_root', 'reviews_root', 'input_files',
              'profiles', 'allowed_operations', 'author_id', 'reviewers',
              'max_seconds', 'max_output_bytes'}
    ROLES = ('technical_plan', 'aesthetic_first', 'aesthetic_second', 'technical_native')

    def __init__(self, path):
        self.path = no_links(path).resolve(strict=True)
        raw, self.data = read_object(self.path)
        d = self.data
        if set(d) != self.FIELDS or type(d['schema_version']) is not int or d['schema_version'] != 1:
            raise HmiError('JOB_POLICY', 'Exact version-1 host policy required')
        if not isinstance(d['reference'], str) or not d['reference'].strip():
            raise HmiError('JOB_POLICY', 'Task-start human authorization reference required')
        for key in ('workspace', 'profiles_root', 'output_root', 'reviews_root'):
            if not isinstance(d[key], str) or not Path(d[key]).is_absolute():
                raise HmiError('JOB_POLICY', 'Host policy paths must be explicit absolute paths')
            setattr(self, key, no_links(d[key]).resolve(strict=True))
            if not getattr(self, key).is_dir():
                raise HmiError('JOB_POLICY', 'Host policy roots must be directories')
        # Neither native file tools nor produced artifacts can rewrite host authority.
        for trusted in (self.path, self.reviews_root, self.profiles_root):
            for writable in (self.workspace, self.output_root):
                if trusted.is_relative_to(writable):
                    raise HmiError('JOB_POLICY', 'Authority/registry/reviews must be outside writable job/output roots')
        if self.workspace == self.output_root or self.workspace.is_relative_to(self.output_root) or self.output_root.is_relative_to(self.workspace):
            raise HmiError('JOB_POLICY', 'Input workspace and delivery root must be separate')
        if not isinstance(d['input_files'], dict) or not d['input_files']:
            raise HmiError('JOB_POLICY', 'Exact input-file pins required')
        for rel, sha in d['input_files'].items():
            relative_file(self.workspace, rel, exists=True)
            if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
                raise HmiError('JOB_POLICY', 'Input SHA-256 required')
        for name in ('profiles', 'allowed_operations'):
            if not isinstance(d[name], list) or not d[name] or any(not isinstance(x, str) or not x for x in d[name]) or len(d[name]) != len(set(d[name])):
                raise HmiError('JOB_POLICY', 'Nonempty unique allowlist required')
        if not isinstance(d['reviewers'], dict) or set(d['reviewers']) != set(self.ROLES):
            raise HmiError('JOB_POLICY', 'Four review stages required')
        ids = [d['author_id'], *(d['reviewers'][role] for role in self.ROLES)]
        if any(not isinstance(x, str) or not x.strip() for x in ids):
            raise HmiError('JOB_POLICY', 'Explicit author/reviewer identities required')
        if len(set([ids[0], ids[1], ids[2], ids[3]])) != 4 or ids[0] == ids[4] or ids[4] in ids[2:4]:
            raise HmiError('JOB_POLICY', 'Technical and two sequential aesthetic reviewers must be independent of author')
        for key, upper in [('max_seconds', 86400), ('max_output_bytes', 1024**3)]:
            if type(d[key]) is not int or not 1 <= d[key] <= upper:
                raise HmiError('JOB_POLICY', 'Positive bounded integer budget required')
        self.sha256 = digest(raw)
        self.fresh()

    def fresh(self):
        no_links(self.path)
        if digest(self.path.read_bytes()) != self.sha256:
            raise HmiError('JOB_POLICY_CHANGED', 'Host authority changed; restart with a new task authorization')
        for root in (self.workspace, self.profiles_root, self.output_root, self.reviews_root):
            no_links(root)
        if tree_digest(self.profiles_root) != self.data['profile_tree_sha256']:
            raise HmiError('JOB_SOURCE_CHANGED', 'Profile/authority pack changed')
        for rel, sha in self.data['input_files'].items():
            if rel.split('/')[0].casefold() == '.headless':
                raise HmiError('JOB_POLICY', 'Generated work area cannot be an authorized input')
            if digest(relative_file(self.workspace, rel, exists=True).read_bytes()) != sha:
                raise HmiError('JOB_SOURCE_CHANGED', 'Input changed', path=rel)
        for path in self.workspace.rglob('*'):
            rel = path.relative_to(self.workspace).as_posix()
            if rel.split('/')[0] == '.headless':
                continue
            no_links(path)
            if path.is_file() and rel not in self.data['input_files']:
                raise HmiError('JOB_UNPINNED_INPUT', 'Every input asset and calibration witness must be pinned', path=rel)

    def authorize_job(self, job):
        self.fresh()
        if not isinstance(job, dict) or set(job) != {'schema_version', 'profile_id', 'source_path', 'design'} or job['schema_version'] != 1 or type(job['schema_version']) is not int:
            raise HmiError('JOB_CONTRACT', 'Exact version-1 job with profile, source and final design required')
        if (not isinstance(job['profile_id'], str) or not isinstance(job['source_path'], str)
                or job['profile_id'] not in self.data['profiles'] or job['source_path'] not in self.data['input_files'] or not isinstance(job['design'], dict)):
            raise HmiError('JOB_AUTHORITY', 'Job outside task-start authorization')

    def authorize_plan(self, operations):
        # Operations carry a canonical op discriminator in the existing service.
        for operation in operations:
            if operation.get('op') not in self.data['allowed_operations']:
                raise HmiError('JOB_AUTHORITY', 'Operation not authorized', op=operation.get('op'))

    def review(self, job_id, role, subject_sha256, previous_sha256=None):
        self.fresh()
        path = relative_file(self.reviews_root, f'{job_id}/{role}.json')
        if not path.is_file():
            return None
        raw, report = read_object(path)
        required = {'schema_version', 'job_id', 'role', 'reviewer_id', 'subject_sha256', 'previous_review_sha256', 'verdict', 'findings', 'evidence'}
        if (set(report) != required or type(report['schema_version']) is not int or report['schema_version'] != 1
                or report['job_id'] != job_id or report['role'] != role
                or report['reviewer_id'] != self.data['reviewers'][role]
                or report['subject_sha256'] != subject_sha256
                or report['previous_review_sha256'] != previous_sha256):
            raise HmiError('JOB_REVIEW', 'Review is stale or belongs to another author/stage/artifact')
        if not isinstance(report['findings'], list) or not isinstance(report['evidence'], str) or not report['evidence'].strip():
            raise HmiError('JOB_REVIEW', 'Findings and concrete inspection evidence required')
        if report['verdict'] != 'PASS' or any(not isinstance(f, dict) or f.get('status') != 'CLOSED' for f in report['findings']):
            raise HmiError('JOB_REVIEW_FAILED', 'Independent review has unresolved findings')
        return {'sha256': digest(raw), 'report': report}
