"""Original neutral public source-clone tests; no manufacturer assets."""
from copy import deepcopy
import asyncio
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from universal_hmi.errors import HmiError
from universal_hmi.native import NativeAdapter
from universal_hmi.native.diascreen_control_append import DiaScreenControlAppend
from universal_hmi.preview import render_preview
from universal_hmi.service import FileService
from universal_hmi.validation import validate_design

ROOT = Path(__file__).resolve().parents[1]


def common_fixture():
    profile = dict(id='source_clone_test', family='delta_diascreen',
                   resolution=[800, 480], capabilities={'native_control_clone': 'OFFLINE_PASS'})
    element = dict(id='clone97', native_id='97', kind='native_control_clone',
                   x=180, y=80, width=160, height=40, text='',
                   source_owner_sha256='a' * 64,
                   clone=dict(donor_kind='maintained', captions=[
                       dict(value=0, text='KAPALI'), dict(value=1, text='AÇIK')]))
    design = dict(schema_version=1, project_id='neutral-clone', profile_id=profile['id'],
                  tags=[], macros=[], alarms=[], screens=[dict(id='page20', native_id='20',
                  name='Neutral source', width=800, height=480, elements=[element])])
    return design, profile


class DiascreenCloneIntentTests(unittest.TestCase):
    def test_source_clone_is_separate_from_generic_control_qualification(self):
        design, profile = common_fixture()
        self.assertEqual(validate_design(design, profile), [])
        profile['capabilities'] = {'button': 'PHYSICAL_PASS', 'numeric_input': 'VENDOR_PASS'}
        self.assertIn('FEATURE_UNSUPPORTED', {f['code'] for f in validate_design(design, profile)})
        profile['capabilities'] = {'native_control_clone': 'OFFLINE_PASS'}
        element = design['screens'][0]['elements'][0]
        element.update(kind='numeric_input', binding={})
        self.assertIn('FEATURE_UNSUPPORTED', {f['code'] for f in validate_design(design, profile)})

    def test_clone_refuses_fabricated_binding_state_behavior_numeric_or_style_intent(self):
        original, profile = common_fixture()
        forbidden = {'binding': {'read': 'invented'}, 'behavior': 'set_on', 'states': [],
                     'minimum': 0, 'maximum': 100, 'fractional': 0, 'format': 'unsigned',
                     'role': 'feedback', 'fill': '#008800', 'font_size': 12, 'text': 'new',
                     'presentation': {}, 'unit': 'mm'}
        for key, value in forbidden.items():
            design = deepcopy(original)
            design['screens'][0]['elements'][0][key] = value
            with self.subTest(key=key):
                self.assertTrue(validate_design(design, profile))

    def test_exact_donor_kind_and_caption_state_frame_intent(self):
        original, profile = common_fixture()
        invalid = [None, [], {}, {'donor_kind': 'set_on', 'captions': []},
                   {'donor_kind': 'maintained', 'captions': []},
                   {'donor_kind': 'numeric_input', 'captions': [{'value': 0, 'text': '0'}]},
                   {'donor_kind': 'maintained', 'captions': [{'value': True, 'text': 'OFF'}, {'value': 1, 'text': 'ON'}]},
                   {'donor_kind': 'maintained', 'captions': [{'value': 1, 'text': 'ON'}, {'value': 0, 'text': 'OFF'}]},
                   {'donor_kind': 'momentary', 'captions': [{'value': 0, 'text': '\ud800'}, {'value': 1, 'text': 'GO'}]},
                   {'donor_kind': 'momentary', 'captions': [{'value': 0, 'text': 'a\0b'}, {'value': 1, 'text': 'GO'}]},
                   {'donor_kind': 'maintained', 'captions': [{'value': 0, 'text': 'OFF', 'fill': '#fff'}, {'value': 1, 'text': 'ON'}]}]
        for clone in invalid:
            design = deepcopy(original)
            design['screens'][0]['elements'][0]['clone'] = clone
            with self.subTest(clone=clone):
                self.assertTrue(validate_design(design, profile))
        for kind in ('numeric_input', 'numeric_display'):
            design = deepcopy(original)
            design['screens'][0]['elements'][0]['clone'] = {'donor_kind': kind, 'captions': []}
            with self.subTest(kind=kind):
                self.assertEqual(validate_design(design, profile), [])

    def test_provenance_native_id_and_rectangle_are_explicit(self):
        original, profile = common_fixture()
        for key, value in [('source_owner_sha256', 'A' * 64), ('native_id', '097'),
                           ('x', -1), ('width', 0), ('x', 799), ('source_owner_sha256', None)]:
            design = deepcopy(original)
            design['screens'][0]['elements'][0][key] = value
            with self.subTest(key=key, value=value):
                self.assertTrue(validate_design(design, profile))

    def test_preview_never_turns_clone_into_sample_or_runtime_state(self):
        design, profile = common_fixture()
        page = render_preview(design, profile, values={'clone97': 1}, states={'clone97': 'valid'})
        self.assertIn('SOURCE CLONE', page)
        self.assertIn('<span class="value">UNKNOWN</span>', page)
        self.assertIn('NATIVE NOT RENDERED', page)
        self.assertNotIn('<span class="value">AÇIK</span>', page)
        self.assertNotIn('<span class="value">1</span>', page)


class DiascreenControlServiceTests(unittest.TestCase):
    def setUp(self):
        # Generated here from invented records, never copied vendor data.
        from test_diascreen_controls import diascreen_controls_fixture, operations
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw, schema = diascreen_controls_fixture(); self.ops = operations()
        (self.root / 'source.dpa').write_bytes(self.raw)
        descriptor = schema['diascreen_control_append']
        authority = dict(contract_version=1, scope='STORED_CONTROL_APPEND_REVIEW',
            source_sha256=descriptor['source_sha256'], family='delta_diascreen', model_id=268502784,
            serialized_version='6.0.00205.8268', donors=descriptor['donors'],
            review_reference='MOCK UNIT REVIEW of original invented records; no vendor authority')
        self.write('review.json', authority)
        self.helper = runpy.run_path(str(ROOT / 'scripts/calibrate_diascreen_controls.py'))['calibrate']
        self.create()
        self.registry = self.root / 'contracts/profiles'
        self.service = FileService(self.root, self.registry)
        self.sid = self.service.open_project('diascreen_source_clones_v1', 'source.dpa')['session_id']
        self.base = json.loads((self.root / 'contracts/design.json').read_bytes())
        self.profile = self.service.sessions[self.sid]['profile']

    def write(self, path, data):
        target = self.root / path; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def create(self, output='contracts', origin='original_neutral_fixture'):
        return self.helper(self.root, 'source.dpa', output, origin,
            'MOCK original invented source, no manufacturer asset', 'MOCK independent unit contract', 'review.json')

    def changed(self):
        design = deepcopy(self.base)
        target = next(s for s in design['screens'] if s['native_id'] == '20')
        donors = self.profile['native_schema']['diascreen_control_append']['donors']
        for operation in self.ops:
            kind = operation['donor_kind']
            target['elements'].append(dict(id='clone' + operation['element_id'], native_id=operation['element_id'],
                kind='native_control_clone', text='', source_owner_sha256=donors[kind]['owner_sha256'],
                clone={'donor_kind': kind, 'captions': deepcopy(operation['captions'])},
                **{k: operation[k] for k in ('x', 'y', 'width', 'height')}))
        return design

    def approve(self, receipt, name='approval.json'):
        approval = {k: v for k, v in receipt.items() if k.endswith('_sha256')}
        approval.update(approved=True, authority='direct_human', purpose='qualification_only',
                        human_reference='MOCK UNIT RECEIPT ONLY; not a real human or vendor approval')
        self.write(name, approval)
        return name

    def program(self):
        return DiaScreenControlAppend(NativeAdapter(self.raw, 'delta_diascreen'),
            {'diascreen_control_append': self.profile['native_schema']['diascreen_control_append']})

    def test_helper_public_candidate_replay_full_body_and_preserved_source(self):
        design = self.changed(); receipt = self.service.plan_changes(self.sid, design, None, 'append')
        self.assertEqual(receipt['operations'], self.ops)
        self.assertEqual(receipt, self.service.plan_changes(self.sid, design, None, 'append'))
        self.assertTrue(self.service.validate(self.sid, receipt['plan_id'])['offline_pass'])
        applied = self.service.apply_plan(self.sid, receipt['plan_id'], self.approve(receipt))
        saved = self.service.save_as(self.sid, 'candidate.dpa')
        raw = (self.root / 'candidate.dpa').read_bytes()
        self.assertEqual(NativeAdapter(raw, 'delta_diascreen').envelope.body, self.program().expected_body(self.ops))
        self.assertTrue(self.program().verify(raw, self.ops))
        self.assertEqual(saved['sha256'], self.service.diff(self.sid)['candidate_sha256'])
        self.assertFalse(applied['program_writer_complete']); self.assertEqual(saved['vendor'], 'NOT_RUN')
        sid = self.service.open_project('diascreen_source_clones_v1', 'source.dpa')['session_id']
        replay = self.service.plan_changes(sid, design, None, 'append')
        self.service.apply_plan(sid, replay['plan_id'], 'approval.json'); self.service.save_as(sid, 'replay.dpa')
        self.assertEqual(raw, (self.root / 'replay.dpa').read_bytes())
        self.assertEqual((self.root / 'source.dpa').read_bytes(), self.raw)

    def test_noop_preserves_complete_file_and_heterogeneous_doc_panel_sizes(self):
        page = next(s for s in self.base['screens'] if s['native_id'] == '24')
        self.assertEqual([page['width'], page['height']], [126, 96])
        receipt = self.service.plan_changes(self.sid, self.base, None, 'noop')
        self.assertEqual(receipt['operations'], [])
        self.assertTrue(self.service.validate(self.sid, receipt['plan_id'])['offline_pass'])
        self.service.apply_plan(self.sid, receipt['plan_id'], self.approve(receipt))
        self.service.save_as(self.sid, 'noop.dpa')
        self.assertEqual((self.root / 'noop.dpa').read_bytes(), self.raw)
        design = deepcopy(self.base); next(s for s in design['screens'] if s['native_id'] == '24')['width'] = 800
        with self.assertRaises(HmiError): self.service.plan_changes(self.sid, design, None, 'resize')

    def test_single_pass_owner_hashes_equal_complete_source_extent_hashes(self):
        # Complete Element+States bytes, including duplicates across pages;
        # source identity remains (page,id), never an ID-only hash cache.
        original, operations = self.service._diascreen_control_intent(self.service.sessions[self.sid], self.base)
        self.assertEqual(operations, [])
        for page in self.base['screens']:
            for owner in page['elements']:
                self.assertEqual(owner['source_owner_sha256'],
                    original.owner_extent_sha256(page['native_id'], owner['native_id']))

    def test_preserved_owner_or_foreign_clone_intent_refuses_before_output(self):
        for mutation in ('original', 'tag', 'binding', 'number', 'subtype', 'foreign', 'wrong-page'):
            design = self.changed(); target = design['screens'][0]; clone = target['elements'][-1]
            if mutation == 'original': target['elements'][0]['source_owner_sha256'] = 'f' * 64
            elif mutation == 'tag': design['tags'] = [dict(id='tag', address='$510', access='Read', data_type='UINT')]
            elif mutation == 'binding': clone['binding'] = {'read': '$510'}
            elif mutation == 'number': clone['fractional'] = 1
            elif mutation == 'subtype': clone['clone']['donor_kind'] = 'set_on'
            elif mutation == 'foreign': clone['source_owner_sha256'] = 'f' * 64
            else: design['screens'][1]['elements'].append(target['elements'].pop())
            with self.subTest(mutation=mutation), self.assertRaises(HmiError):
                self.service.plan_changes(self.sid, design, None, mutation)
        self.assertEqual((self.root / 'source.dpa').read_bytes(), self.raw)

    def test_explicit_operations_cannot_hide_extra_changes_or_change_approved_clone(self):
        for operations in (self.ops + [dict(op='bind')], self.ops[:-1], deepcopy(self.ops)):
            if len(operations) == len(self.ops): operations[0]['x'] += 1
            receipt = self.service.plan_changes(self.sid, self.changed(), operations, str(operations))
            self.assertFalse(self.service.validate(self.sid, receipt['plan_id'])['offline_pass'])
            with self.assertRaises(HmiError): self.service.apply_plan(self.sid, receipt['plan_id'], self.approve(receipt))
        self.assertFalse((self.root / 'candidate.dpa').exists())

    def test_source_review_calibration_and_profile_freshness(self):
        for name in ('source.dpa', 'review.json', 'contracts/CALIBRATION.json', 'contracts/profiles/diascreen_source_clones_v1.json'):
            receipt = self.service.plan_changes(self.sid, self.changed(), None, name)
            path = self.root / name; original = path.read_bytes(); path.write_bytes(original + b' ')
            try:
                with self.subTest(name=name), self.assertRaises(HmiError):
                    self.service.apply_plan(self.sid, receipt['plan_id'], self.approve(receipt))
            finally: path.write_bytes(original)
        self.assertFalse((self.root / 'candidate.dpa').exists())

    def test_review_artifact_is_exact_source_and_donor_metadata_not_arbitrary_digest(self):
        original = json.loads((self.root / 'review.json').read_bytes())
        for key, value in [('source_sha256', 'f' * 64), ('scope', 'VENDOR_PASS'), ('donors', {}), ('model_id', True)]:
            review = deepcopy(original); review[key] = value; self.write('review.json', review)
            try:
                with self.subTest(key=key), self.assertRaises(HmiError): self.create('wrong' + key)
            finally: self.write('review.json', original)
        self.assertFalse((self.root / 'wrongscope').exists())

    def test_samples_are_rejected_and_preview_remains_source_clone_placeholder(self):
        receipt = self.service.plan_changes(self.sid, self.changed(), None, 'preview')
        for kwargs in ({'values': {'clone97': 1}}, {'states': {'clone97': 'valid'}}, {'values': {}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(HmiError):
                self.service.preview(self.sid, receipt['plan_id'], **kwargs)
        html = self.service.preview(self.sid, receipt['plan_id'])['html']
        self.assertIn('SOURCE CLONES · NATIVE NOT RENDERED', html)
        self.assertIn('<span class="element-title">SOURCE CLONE</span>', html)
        self.assertNotIn('<span class="value">1</span>', html)

    def test_all_approval_pins_and_non_synthetic_exception_are_enforced(self):
        receipt = self.service.plan_changes(self.sid, self.changed(), None, 'pins')
        self.approve(receipt); original = json.loads((self.root / 'approval.json').read_bytes())
        for key in [k for k in original if k.endswith('_sha256')]:
            wrong = deepcopy(original); wrong[key] = 'f' * 64; self.write('wrong.json', wrong)
            with self.subTest(key=key), self.assertRaises(HmiError):
                self.service.apply_plan(self.sid, receipt['plan_id'], 'wrong.json')
        wrong = deepcopy(original); wrong['authority'] = 'neutral_fixture_qualification'; self.write('wrong.json', wrong)
        with self.assertRaises(HmiError): self.service.apply_plan(self.sid, receipt['plan_id'], 'wrong.json')
        self.assertFalse((self.root / 'candidate.dpa').exists())

    def test_mixed_ordinary_schema_or_other_family_is_not_a_source_clone_route(self):
        original = json.loads((self.registry / 'diascreen_source_clones_v1.json').read_bytes())
        for mutation in ('mixed', 'family', 'descriptor'):
            profile = deepcopy(original)
            if mutation == 'mixed': profile['native_schema']['control_generation'] = {}
            elif mutation == 'family': profile['family'] = 'delta_dopsoft2'
            else: profile['native_schema']['diascreen_control_append'] = []
            self.write('contracts/profiles/diascreen_source_clones_v1.json', profile)
            try:
                with self.subTest(mutation=mutation), self.assertRaises(HmiError):
                    FileService(self.root, self.registry).open_project('diascreen_source_clones_v1', 'source.dpa')
            finally: self.write('contracts/profiles/diascreen_source_clones_v1.json', original)


class DiascreenControlSdkTests(unittest.TestCase):
    def test_original_neutral_clones_through_all_nine_stdio_tools(self):
        fixture = DiascreenControlServiceTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        install = fixture.root / 'isolated_install'; shutil.copytree(ROOT / 'src/universal_hmi', install / 'src/universal_hmi')
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=['-m', 'universal_hmi.cli', '--profiles',
                str(fixture.registry), 'serve', '--workspace', str(fixture.root)],
                env={**os.environ, 'PYTHONPATH': str(install / 'src'), 'PYTHONUTF8': '1'}, cwd=str(fixture.root))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize(); self.assertEqual(len((await client.list_tools()).tools), 9)
                    used = set()
                    async def call(name, **args):
                        used.add(name); result = await client.call_tool(name, args)
                        self.assertFalse(result.is_error, str(result)); return result.structured_content
                    profile = await call('capabilities', profile_id='diascreen_source_clones_v1')
                    self.assertNotIn('button', profile['capabilities'])
                    sid = (await call('open_project', profile_id='diascreen_source_clones_v1', source_path='source.dpa'))['session_id']
                    await call('inspect', session_id=sid)
                    receipt = await call('plan_changes', session_id=sid, design=fixture.changed(), idempotency_key='clone')
                    self.assertTrue((await call('validate', session_id=sid, plan_id=receipt['plan_id']))['offline_pass'])
                    self.assertEqual((await call('preview', session_id=sid, plan_id=receipt['plan_id']))['native_visual_acceptance'], 'NOT_RUN')
                    applied = await call('apply_plan', session_id=sid, plan_id=receipt['plan_id'], approval_path=fixture.approve(receipt))
                    saved = await call('save_as', session_id=sid, output_path='sdk.dpa')
                    self.assertEqual(saved['sha256'], (await call('diff', session_id=sid))['candidate_sha256'])
                    self.assertEqual(used, {'open_project', 'capabilities', 'inspect', 'plan_changes', 'preview', 'validate', 'apply_plan', 'save_as', 'diff'})
                    self.assertTrue(fixture.program().verify((fixture.root / 'sdk.dpa').read_bytes(), fixture.ops))
                    self.assertEqual((fixture.root / 'source.dpa').read_bytes(), fixture.raw)
                    self.assertFalse(applied['program_writer_complete'])
        asyncio.run(exercise())


if __name__ == '__main__':
    unittest.main()
