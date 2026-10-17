# SPDX-License-Identifier: Apache-2.0
"""Neutral refusal/workflow contracts, not vendor or physical acceptance."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from universal_diascreen_hmi.contracts import evaluate_status
from universal_diascreen_hmi.errors import AgentError, digest
from universal_diascreen_hmi.native import Project, encode_token
from universal_diascreen_hmi.operations import OP_FIELDS, canonical
from universal_diascreen_hmi.preview import render_preview
from universal_diascreen_hmi.session import Session
from tests.fixtures import native, payload, profile, wrap

ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.source = self.root / 'source.dpa'
        self.source.write_bytes(native())
        self.s = Session(self.root, allow_write=True)
        p = profile()
        self.s.open_project('source.dpa', digest(native()), p, digest(canonical(p)))

    def refuse(self, operation, code=None):
        self.s.inspect()
        before = self.s.current
        with self.assertRaises(AgentError) as error:
            self.s.plan_changes([operation])
        if code:
            self.assertEqual(error.exception.code, code)
        self.assertEqual(self.s.current, before)
        self.assertEqual(self.source.read_bytes(), native())
        return error.exception

    def test_dop_b_family_and_profile_mismatch_refused(self):
        foreign = bytearray(native())
        foreign[6:10] = b'DPSB'
        with self.assertRaises(AgentError) as error:
            Project(bytes(foreign))
        self.assertEqual(error.exception.code, 'FAMILY')
        p = profile()
        p['family'] = 'dop-b'
        with self.assertRaises(AgentError) as error:
            self.s.open_project('source.dpa', digest(native()), p, digest(canonical(p)))
        self.assertEqual(error.exception.code, 'PROFILE')
        self.assertEqual(self.s.current, native())

    def test_picture_bank_import_copy_and_prune_refused(self):
        for operation in ('picture_import', 'picture_copy', 'picture_prune'):
            with self.subTest(operation=operation):
                self.refuse({'op': operation}, 'OPERATION_FIELDS')
        self.assertEqual(self.s.capabilities()['picture_bank_write'], 'DISCOVERED_UNQUALIFIED')

    def test_unimplemented_runtime_families_have_no_generic_builder(self):
        requested = ('enhanced_recipe', 'alarm_history', 'trend_chart', 'security_account',
                     'multilingual_render', 'system_keypad', 'popup_lifecycle', 's7_db_mapping', 'rasterize_icon')
        for operation in requested:
            with self.subTest(operation=operation):
                self.refuse({'op': operation}, 'OPERATION_FIELDS')
        self.assertEqual(self.s.validate()['runtime'], 'NOT_RUN')

    def test_unknown_operation_members_and_properties_fail_closed(self):
        self.refuse({'op': 'set_text', 'page_id': 1, 'element_id': 10, 'state_value': 0,
                     'text': 'Neutral', 'unrecognized_option': True}, 'OPERATION_FIELDS')
        self.refuse({'op': 'set_property', 'page_id': 1, 'element_id': 10,
                     'field': 'UnqualifiedNativeField', 'value': 1}, 'PROPERTY_NOT_QUALIFIED')

    def test_alarm_marker_is_not_a_history_decoder_or_health_proof(self):
        data = wrap(payload().replace(b'[END]\r\n', b'[Alarm]\r\nUninterpreted=0\r\n[END]\r\n'))
        self.source.write_bytes(data)
        self.s = Session(self.root)
        p = profile()
        self.s.open_project('source.dpa', digest(data), p, digest(canonical(p)))
        view = self.s.inspect('alarms')
        self.assertTrue(view['presence_marker_only'])
        self.assertFalse(view['history_decoder'])
        self.assertEqual(view['support'], 'DISCOVERED_UNQUALIFIED')

    def test_atomic_mode_and_automatic_reconnect_replay_are_not_supplied(self):
        self.refuse({'op': 'atomic_mode_selection'}, 'OPERATION_FIELDS')
        self.refuse({'op': 'reconnect_replay'}, 'OPERATION_FIELDS')
        self.assertEqual(self.s.capabilities()['runtime_heartbeat'], 'ROLLED_BACK_NOT_DEFAULT')
        self.assertEqual(self.s.validate()['runtime'], 'NOT_RUN')

    def test_missing_tag_is_not_invented_feedback_or_a_polling_counter(self):
        self.refuse({'op': 'rebind', 'page_id': 1, 'element_id': 10, 'field': 'ReadVar',
                     'expected_address': 'DIA_TAG@{Link1}0.Main.Start',
                     'address': 'DIA_TAG@{Link1}0.Main.NotPublished'}, 'SYMBOL_MISSING')
        self.refuse({'op': 'event_polling_counter'}, 'OPERATION_FIELDS')
        empty = evaluate_status({}, {'schema_version': 1,
                                     'fault': {'active': 'active', 'code': 'code', 'fresh': 'fresh'},
                                     'reference': {'valid': 'reference', 'physical_home': 'sensor'}})
        self.assertEqual(empty['fault']['state'], 'UNKNOWN')
        self.assertFalse(empty['fault']['healthy_claim'])
        self.assertIsNone(empty['reference']['valid'])
        self.assertIsNone(empty['reference']['physical_home'])
        self.assertFalse(empty['reference']['start_permit_inferred'])

    def test_dynamic_gradient_and_transparency_are_not_flattened(self):
        # This neutral source opts into the exact flat-v1 property subset. It is
        # not a normalization pass on an unqualified proprietary native file.
        body = payload().replace(b'FillType=6\r\n', b'FillType=1\r\n').replace(b'FillAngle=', b'FillAngleArg=')
        q = Project(wrap(body))
        p = profile()
        self.assertEqual(render_preview(q, p)['level'], 'OFFLINE_MODEL_ONLY')
        for key, value in (('TransEffect', 1), ('FgFillEndColor', 1)):
            original = q.element(1, 10).states[0].one(key)
            mutated = body[:original.start] + encode_token(original, value, body) + body[original.end:]
            with self.subTest(field=key), self.assertRaises(AgentError) as error:
                render_preview(Project(wrap(mutated)), p)
            self.assertEqual(error.exception.code, 'UNSUPPORTED_RENDER')
        transparent = body.replace(b'Style=0\r\n', b'Style=3\r\n')
        view = render_preview(Project(wrap(transparent)), p)
        self.assertEqual(view['level'], 'OFFLINE_MODEL_ONLY')
        self.assertTrue(any(i['code'] == 'FONT_METRICS_NOT_VERIFIED' for i in view['issues']))

    def test_stale_compiled_artifact_and_receipt_are_refused(self):
        artifact = self.root / 'observation.cin'
        data = b'neutral caller-linked observation'
        artifact.write_bytes(data)
        receipt = {'artifact_sha256': digest(data), 'source_sha256': digest(native()), 'candidate_sha256': digest(native())}
        observed = self.s.inspect_compiled('observation.cin', digest(data), digest(native()), digest(native()), receipt)
        self.assertFalse(observed['full_cin_acceptance'])
        self.assertEqual(observed['compile_acceptance'], 'NOT_ESTABLISHED')
        artifact.write_bytes(data + b'changed')
        with self.assertRaises(AgentError) as error:
            self.s.inspect_compiled('observation.cin', digest(data), digest(native()), digest(native()), receipt)
        self.assertEqual(error.exception.code, 'COMPILED_IDENTITY')
        artifact.write_bytes(data)
        wrong = dict(receipt, candidate_sha256='0' * 64)
        with self.assertRaises(AgentError) as error:
            self.s.inspect_compiled('observation.cin', digest(data), digest(native()), digest(native()), wrong)
        self.assertEqual(error.exception.code, 'COMPILED_RECEIPT')

    def test_documented_schema_operation_set_matches_runtime(self):
        schema = json.loads((ROOT / 'profiles/operations.schema.json').read_text('utf8'))
        branches = schema['items']['oneOf']
        documented = {branch['properties']['op']['const']: branch for branch in branches}
        self.assertEqual(set(documented), set(OP_FIELDS))
        for name, fields in OP_FIELDS.items():
            self.assertFalse(documented[name]['additionalProperties'])
            self.assertEqual(set(documented[name]['properties']) - {'op', 'operation_id'}, fields)
        prof = json.loads((ROOT / 'profiles/profile.schema.json').read_text('utf8'))
        self.assertTrue(set(profile()) <= set(prof['properties']))
        self.assertEqual(prof['properties']['family']['const'], 'diascreen-dop100')
        self.assertIn('interface_contract', prof['properties'])
        self.assertIn('catalog_bindings', prof['properties'])
        self.assertIn('binding_types', prof['properties'])

    def test_demo_is_neutral_fresh_and_never_overwrites(self):
        destination = self.root / 'demo'
        command = [sys.executable, '-B', str(ROOT / 'examples/create_demo.py'), str(destination)]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        receipt = json.loads((destination / 'IDENTITY.json').read_text('utf8'))
        generated = (destination / 'source.dpa').read_bytes()
        p = json.loads((destination / 'profile.json').read_text('utf8'))
        self.assertEqual(p['panel'], {'width': 400, 'height': 240})
        self.assertEqual(generated, native())
        self.assertEqual(receipt['source_sha256'], digest(generated))
        self.assertEqual(receipt['profile_sha256'], digest(canonical(p)))
        self.assertEqual(receipt['scope'], 'SYNTHETIC_FILE_EXAMPLE_ONLY')
        again = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual((destination / 'source.dpa').read_bytes(), generated)


if __name__ == '__main__':
    unittest.main()
