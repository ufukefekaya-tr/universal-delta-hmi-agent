# SPDX-License-Identifier: Apache-2.0
"""Neutral proposal-review isolation and coordinate-inspection regressions."""
from copy import deepcopy
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from universal_diascreen_hmi.errors import AgentError, digest
from universal_diascreen_hmi.native import Project, layout_digest
from universal_diascreen_hmi.operations import canonical
from universal_diascreen_hmi.resources import flat_dib
from universal_diascreen_hmi.session import Session
from tests.fixtures import element, line, payload, profile as base_profile, wide, wrap


ROOT = Path(__file__).resolve().parents[1]


def flat_body(body):
    # Explicitly construct the supported flat synthetic variant. The general
    # framing fixture also exercises vendor fields outside flat-v1.
    for prefix in (b'Fg', b'Bg'):
        body = body.replace(prefix + b'FillType=6\r\n', prefix + b'FillType=1\r\n')
        body = body.replace(prefix + b'FillAngle=None\r\n', prefix + b'FillAngleArg=None\r\n')
    return body


def native():
    return wrap(flat_body(payload()))


def profile():
    contract = base_profile()
    contract['indexed_layout_sha256'] = layout_digest(Project(native()))
    return contract


def caption(text, state_value=0):
    return {'op': 'set_text', 'page_id': 1, 'element_id': 10,
            'state_value': state_value, 'text': text}


def coordinate_fixture():
    body = payload()
    source = Project(native())
    app = body[:source.pages[0].section.start]
    tail = body[body.index(b'[SubMacro]\r\n'):]

    def page(identity, elements):
        return (b'[Screen]\r\n' + line('ID', identity) + wide('wTextLen', 'Neutral page')
                + line('PictureOffset', 0) + line('BgColor', 0x111111)
                + b'[AuxKeyElement]\r\n' + elements)

    # Page2 precedes page1; equal coordinates retain native layer order11,10.
    page_two = page(2, element(21, 'PageTwo', x=200, y=50, caption='PAGE TWO'))
    page_one = page(1, element(13, 'Lower', x=180, y=80, caption='LOWER')
                    + element(11, 'TieFirst', x=10, y=10, caption='TIE FIRST')
                    + element(12, 'Left', x=10, y=80, caption='LEFT')
                    + element(10, 'TieLast', x=10, y=10, caption='TIE LAST'))
    return wrap(flat_body(app + page_two + page_one + tail))


class PlanReviewTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.source = self.root / 'source.dpa'
        self.source.write_bytes(native())
        self.s = self.open_session()

    def open_session(self, *, write=False, data=None, contract=None):
        data = native() if data is None else data
        self.source.write_bytes(data)
        contract = profile() if contract is None else contract
        session = Session(self.root, allow_write=write)
        session.open_project('source.dpa', digest(data), contract, digest(canonical(contract)))
        return session

    def plan(self, text='PROPOSED CAPTION', *, session=None, operations=None):
        session = self.s if session is None else session
        session.inspect()
        return session.plan_changes([caption(text)] if operations is None else operations)

    def snapshot(self, session):
        # Include every session field and nested stored plan/donor, not a hand-
        # picked subset that could miss a new cache or inspection side effect.
        state = pickle.dumps(vars(session), protocol=4)
        disk = tuple(sorted((path.relative_to(self.root).as_posix(),
                             path.read_bytes() if path.is_file() else None)
                            for path in self.root.rglob('*')))
        return state, disk

    def readonly(self, session, operation):
        before = self.snapshot(session)
        try:
            return operation()
        finally:
            self.assertEqual(self.snapshot(session), before)

    def refused(self, session, operation, code):
        with self.assertRaises(AgentError) as error:
            self.readonly(session, operation)
        self.assertEqual(error.exception.code, code)

    def assert_identity(self, result, plan=None, session=None):
        session = self.s if session is None else session
        self.assertEqual(result['source_sha256'], digest(session.source))
        self.assertEqual(result['view'], 'current' if plan is None else 'proposal')
        self.assertEqual(result['plan_sha256'], None if plan is None else plan['plan_sha256'])
        self.assertEqual(result['candidate_sha256'], digest(session.current) if plan is None else plan['candidate_sha256'])
        self.assertEqual(result['candidate_profile_sha256'], session.current_profile_sha256
                         if plan is None else plan['candidate_profile_sha256'])

    def test_proposal_caption_sha_and_readonly_state(self):
        plan = self.plan()
        other = self.s.plan_changes([caption('OTHER PENDING CAPTION')])
        for _ in range(2):
            proposal = self.readonly(self.s, lambda: self.s.preview(plan_sha256=plan['plan_sha256']))
            current = self.readonly(self.s, self.s.preview)
            validation = self.readonly(self.s, lambda: self.s.validate(plan_sha256=plan['plan_sha256']))
            self.assert_identity(proposal, plan)
            self.assert_identity(current)
            self.assert_identity(validation, plan)
            self.assertIn('PROPOSED CAPTION', proposal['result']['svg'])
            self.assertNotIn('OTHER PENDING CAPTION', proposal['result']['svg'])
            self.assertNotIn('PROPOSED CAPTION', current['result']['svg'])
            self.assertEqual(validation['status'], 'OFFLINE_STRUCTURAL_PASS')
            self.assertEqual(validation['preservation'], 'PASS')
            self.assertEqual(validation['runtime'], 'NOT_RUN')
            self.assertEqual(validation['vendor_compile'], 'NOT_RUN')
        selected = self.readonly(self.s, lambda: self.s.preview(plan_sha256=other['plan_sha256']))
        self.assertIn('OTHER PENDING CAPTION', selected['result']['svg'])
        self.assertFalse(self.s.allow_write)
        self.assertEqual(self.s.current, native())
        self.assertEqual(self.source.read_bytes(), native())
        self.assertEqual(len(self.s.pending_changes()['plans']), 2)

    def test_current_views_keep_inspection_and_all_state(self):
        self.assertIsNone(self.s.inspected_sha)
        for operation in (self.s.preview, self.s.validate,
                          lambda: self.s.preview(plan_sha256=None),
                          lambda: self.s.validate(plan_sha256=None)):
            result = self.readonly(self.s, operation)
            self.assert_identity(result)
            self.assertIsNone(self.s.inspected_sha)
        with self.assertRaises(AgentError) as error:
            self.s.plan_changes([caption('Inspection still required')])
        self.assertEqual(error.exception.code, 'INSPECTION_REQUIRED')

    def test_gallery_uses_proposed_background_profile(self):
        old = flat_dib(400, 240, 0x111111)
        plan = self.plan(operations=[caption('BACKGROUND PROPOSAL'),
            {'op': 'flat_background', 'page_ids': [1], 'rgb': 0x123456,
             'expected_bank_sha256': digest(old)}])
        proposed_profile = self.s.plans[plan['plan_sha256']]['profile']
        self.assertEqual(proposed_profile['background_sha256']['1'], digest(flat_dib(400, 240, 0x123456)))
        self.assertEqual(self.s.current_profile['background_sha256']['1'], digest(old))
        gallery = self.readonly(self.s, lambda: self.s.preview(gallery=True, plan_sha256=plan['plan_sha256']))
        self.assert_identity(gallery, plan)
        self.assertEqual(len(gallery['result']), 10)
        self.assertEqual({entry['page_id'] for entry in gallery['result']}, {1, 2})
        off = next(entry for entry in gallery['result'] if entry['page_id'] == 1 and entry['case'] == 'SYNTHETIC_OFF')
        self.assertIn('BACKGROUND PROPOSAL', off['svg'])
        current = self.readonly(self.s, lambda: self.s.preview(page_id=1))
        self.assertNotIn('BACKGROUND PROPOSAL', current['result']['svg'])
        self.assertNotEqual(off['layer_digest'], current['result']['layer_digest'])
        self.assertEqual(self.readonly(self.s, lambda: self.s.validate(plan_sha256=plan['plan_sha256']))['preservation'], 'PASS')

    def test_unknown_malformed_and_immutable_plan_drift(self):
        plan = self.plan()
        key = plan['plan_sha256']
        for method in (self.s.preview, self.s.validate):
            self.refused(self.s, lambda: method(plan_sha256='0' * 64), 'PLAN_UNKNOWN')
            for value in ('', 'bad', 'A' * 64, 7, True, [], {}):
                with self.subTest(method=method.__name__, value=value):
                    self.refused(self.s, lambda: method(plan_sha256=value), 'HASH')
        original = deepcopy(self.s.plans[key])
        for component in ('candidate', 'profile', 'record', 'steps'):
            self.s.plans[key] = deepcopy(original)
            stored = self.s.plans[key]
            if component == 'candidate':
                stored['candidate'] += b'changed'
            elif component == 'profile':
                stored['profile']['station'] = 1
            elif component == 'record':
                stored['record']['operations'][0]['text'] = 'Changed record'
            else:
                stored['steps'][0]['output_payload_sha256'] = '0' * 64
            with self.subTest(component=component):
                self.refused(self.s, lambda: self.s.preview(plan_sha256=key), 'PLAN_DRIFT')
                self.refused(self.s, lambda: self.s.validate(plan_sha256=key), 'PLAN_DRIFT')

    def test_source_profile_and_donor_drift_refused(self):
        for field in ('profile', 'current_profile'):
            session = self.open_session()
            plan = self.plan(session=session)
            getattr(session, field)['station'] = 2
            for method in (session.preview, session.validate):
                self.refused(session, lambda: method(plan_sha256=plan['plan_sha256']), 'PROFILE_DRIFT')
        session = self.open_session()
        plan = self.plan(session=session)
        self.source.write_bytes(native() + b'changed source')
        for method in (session.preview, session.validate):
            self.refused(session, lambda: method(plan_sha256=plan['plan_sha256']), 'SOURCE_DRIFT')
        session = self.open_session()
        session.register_donor('seed', 'source.dpa', digest(native()))
        plan = self.plan(session=session)
        session.register_donor('extra', 'source.dpa', digest(native()))
        for method in (session.preview, session.validate):
            self.refused(session, lambda: method(plan_sha256=plan['plan_sha256']), 'DONOR_DRIFT')

    def test_stale_applied_and_rollback_proposals_refused(self):
        session = self.open_session(write=True)
        first = self.plan('FIRST', session=session)
        stale = session.plan_changes([caption('STALE')])
        session.apply_plan(first['plan_sha256'], first['plan_sha256'])
        session.inspect()
        for method in (session.preview, session.validate):
            self.refused(session, lambda: method(plan_sha256=first['plan_sha256']), 'ALREADY_APPLIED')
            self.refused(session, lambda: method(plan_sha256=stale['plan_sha256']), 'STALE_PLAN')
        self.assert_identity(self.readonly(session, session.preview), session=session)
        session.rollback()
        for method in (session.preview, session.validate):
            self.refused(session, lambda: method(plan_sha256=stale['plan_sha256']), 'PLAN_UNKNOWN')
        self.assertEqual(session.current, native())

    def test_proposal_inverse_extends_applied_chain(self):
        session = self.open_session(write=True)
        first = self.plan('APPLIED FIRST', session=session)
        session.apply_plan(first['plan_sha256'], first['plan_sha256'])
        second = self.plan(session=session, operations=[caption('SECOND STATE', 1),
            {'op': 'set_property', 'page_id': 1, 'element_id': 10, 'field': 'X', 'value': 15}])
        current = session.current
        result = self.readonly(session, lambda: session.validate(plan_sha256=second['plan_sha256']))
        self.assert_identity(result, second, session)
        self.assertEqual(result['status'], 'OFFLINE_STRUCTURAL_PASS')
        self.assertEqual(result['preservation'], 'PASS')
        self.assertEqual(session.current, current)
        self.assertEqual(len(session.applied), 1)
        self.assertEqual(self.readonly(session, session.validate)['preservation'], 'PASS')
        session.plans[first['plan_sha256']]['steps'][0]['output_payload_sha256'] = '0' * 64
        self.refused(session, lambda: session.validate(plan_sha256=second['plan_sha256']), 'PLAN_DRIFT')

    def test_inverse_rejects_coherently_rehashed_bad_ledger(self):
        plan = self.plan()
        stored = self.s.plans.pop(plan['plan_sha256'])
        stored['steps'][0]['output_payload_sha256'] = '0' * 64
        stored['record']['ledger_sha256'] = digest(canonical(stored['steps']))
        key = digest(canonical(stored['record']))
        self.s.plans[key] = stored
        self.refused(self.s, lambda: self.s.validate(plan_sha256=key), 'INVERSE')

    def test_failure_results_and_unsupported_render_do_not_mutate(self):
        unsupported = wrap(flat_body(payload()).replace(b'FontItalic=0\r\n', b'FontItalic=1\r\n', 1))
        contract = profile()
        contract['indexed_layout_sha256'] = layout_digest(Project(unsupported))
        session = self.open_session(data=unsupported, contract=contract)
        plan = self.plan(session=session)
        self.refused(session, lambda: session.preview(plan_sha256=plan['plan_sha256']), 'UNSUPPORTED_RENDER')
        self.s = self.open_session()
        self.plan()
        good = self.s.plan_changes([caption('VALIDATION FAILURE CASE')])
        with patch('universal_diascreen_hmi.session.validate_references',
                   side_effect=AgentError('NEUTRAL_REFERENCE', 'Synthetic reference validation failure')):
            result = self.readonly(self.s, lambda: self.s.validate(plan_sha256=good['plan_sha256']))
        self.assert_identity(result, good)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['errors'][0]['code'], 'NEUTRAL_REFERENCE')
        self.assertEqual(result['preservation'], 'PASS')
        self.assertNotIn('PROPOSED CAPTION', self.readonly(self.s, self.s.preview)['result']['svg'])

    def test_coordinate_layout_text_order_preserves_render_layers(self):
        data = coordinate_fixture()
        contract = profile()
        contract['indexed_layout_sha256'] = layout_digest(Project(data))
        session = self.open_session(data=data, contract=contract)
        initial = self.readonly(session, lambda: session.preview(page_id=1))
        layer = session.inspect('layout')
        expected_layer = [(2, 21), (1, 13), (1, 11), (1, 12), (1, 10)]
        self.assertEqual([(r['page_id'], r['element_id']) for r in layer], expected_layer)
        coordinate = session.inspect('layout', sort='coordinate')
        expected_coordinate = [(2, 21), (1, 11), (1, 10), (1, 12), (1, 13)]
        self.assertEqual([(r['page_id'], r['element_id']) for r in coordinate], expected_coordinate)
        self.assertEqual([r['layer_index'] for r in coordinate if r['page_id'] == 1], [1, 3, 2, 0])
        for sort, expected in (('layer', expected_layer), ('coordinate', expected_coordinate)):
            text = session.inspect('text', sort=sort)
            actual = [tuple(int(part.split('=')[1]) for part in row.split()[:2]) for row in text.splitlines()]
            self.assertEqual(actual, expected)
        selected = session.inspect('layout', page_id=1, sort='coordinate')
        self.assertEqual([r['element_id'] for r in selected], [11, 10, 12, 13])
        final = self.readonly(session, lambda: session.preview(page_id=1))
        self.assertEqual(initial, final)
        self.assertEqual([r['element_id'] for r in final['result']['samples']], [13, 11, 12, 10])
        self.assertEqual(session.current, data)
        self.assertEqual(self.source.read_bytes(), data)

    def test_sort_invalid_or_unrelated_views_refused(self):
        for sort in ('unknown', 'Coordinate', True, 1, [], None):
            self.refused(self.s, lambda: self.s.inspect('layout', sort=sort), 'INSPECT_SORT')
        for view in ('project', 'screens', 'element', 'find', 'addresses', 'design'):
            self.refused(self.s, lambda: self.s.inspect(view, sort='coordinate'), 'INSPECT_SORT')

    def test_stdio_readonly_proposal_review_and_discovery_schemas(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        process = subprocess.Popen([sys.executable, '-B', '-X', 'utf8', '-m', 'universal_diascreen_hmi.cli',
                                    '--workspace', str(self.root)], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT, env=env)
        count = 0

        def rpc(method, params):
            nonlocal count
            count += 1
            request = {'jsonrpc': '2.0', 'id': count, 'method': method, 'params': params}
            process.stdin.write((json.dumps(request) + '\n').encode('utf-8'))
            process.stdin.flush()
            row = process.stdout.readline()
            self.assertTrue(row, 'Read-only process closed before replying')
            reply = json.loads(row)
            self.assertEqual(reply['id'], count)
            self.assertNotIn('error', reply)
            return reply['result']

        def call(name, **arguments):
            return rpc('tools/call', {'name': name, 'arguments': arguments})

        try:
            rpc('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                               'clientInfo': {'name': 'neutral-review', 'version': '1'}})
            schemas = {row['name']: row['inputSchema'] for row in rpc('tools/list', {})['tools']}
            self.assertLessEqual({'open_project', 'list_screens', 'layout', 'element', 'find',
                'addresses', 'macros', 'alarms', 'set_property', 'set_text', 'rebind', 'pending_changes',
                'save', 'screenshot_text', 'clone_element', 'clone_screen', 'delete_element', 'set_state_text'},
                set(schemas))
            for name in ('preview', 'validate'):
                self.assertEqual(schemas[name]['properties']['plan_sha256'], {'type': 'string', 'pattern': '^[0-9a-f]{64}$'})
                self.assertNotIn('plan_sha256', schemas[name]['required'])
            for name in ('inspect', 'layout', 'screenshot_text'):
                self.assertEqual(schemas[name]['properties']['sort']['enum'], ['layer', 'coordinate'])
                self.assertNotIn('sort', schemas[name]['required'])
            self.assertNotIn('sort', schemas['find']['properties'])
            contract = profile()
            self.assertFalse(call('open_project', path='source.dpa', source_sha256=digest(native()),
                                  profile=contract, profile_sha256=digest(canonical(contract)))['isError'])
            self.assertFalse(call('inspect')['isError'])
            planned = call('plan_changes', operations=[caption('STDIO PROPOSAL')])
            self.assertFalse(planned['isError'])
            plan = planned['structuredContent']
            for name in ('preview', 'validate'):
                result = call(name, plan_sha256=plan['plan_sha256'])
                self.assertFalse(result['isError'])
                self.assert_identity(result['structuredContent'], plan)
                self.assertTrue(call(name, plan_sha256=None)['isError'])
                self.assertTrue(call(name, plan_sha256='not-a-hash')['isError'])
                self.assertTrue(call(name, plan_sha256='0' * 64)['isError'])
            proposed = call('preview', plan_sha256=plan['plan_sha256'])['structuredContent']
            self.assertIn('STDIO PROPOSAL', proposed['result']['svg'])
            current = call('preview')['structuredContent']
            self.assertNotIn('STDIO PROPOSAL', current['result']['svg'])
            self.assert_identity(current)
            self.assertFalse(call('preview', gallery=True, plan_sha256=plan['plan_sha256'])['isError'])
            for alias in ('layout', 'screenshot_text'):
                self.assertFalse(call(alias, sort='coordinate')['isError'])
            self.assertTrue(call('inspect', view='addresses', sort='coordinate')['isError'])
            denied = call('apply_plan', plan_sha256=plan['plan_sha256'], approval_sha256=plan['plan_sha256'])
            self.assertEqual(denied['structuredContent']['error']['code'], 'WRITE_DISABLED')
            self.assertEqual(call('diff')['structuredContent']['applied'], [])
            self.assertFalse(call('pending_changes')['structuredContent']['unsaved_candidate'])
            self.assertEqual(self.source.read_bytes(), native())
            self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['.runtime','source.dpa'])
            self.assertTrue((self.root/'.runtime/operations.sqlite3').is_file())
        finally:
            process.stdin.close()
            process.wait(timeout=10)
            remaining, errors = process.stdout.read(), process.stderr.read()
            process.stdout.close()
            process.stderr.close()
            self.assertEqual(process.returncode, 0)
            self.assertEqual(remaining, b'')
            self.assertEqual(errors, b'')


if __name__ == '__main__':
    unittest.main()
