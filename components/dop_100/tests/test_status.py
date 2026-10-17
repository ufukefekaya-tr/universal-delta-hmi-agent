# SPDX-License-Identifier: Apache-2.0
import unittest
from universal_diascreen_hmi.contracts import evaluate_status, validate_aesthetic_receipts, design_ledger
from universal_diascreen_hmi.errors import AgentError, digest
from universal_diascreen_hmi.native import Project
from tests.fixtures import native


class StatusTests(unittest.TestCase):
    def test_r19_active_fault_zero_and_unknown_raw_never_healthy(self):
        contract = {'schema_version': 1, 'fault': {'active': 'A', 'code': 'C', 'fresh': 'F', 'catalog': {'7': 'Example fault'}}}
        for code in (0, 7, 999999):
            result = evaluate_status({'A': 1, 'C': code, 'F': 1}, contract)['fault']
            self.assertEqual(result['state'], 'FAULT'); self.assertFalse(result['healthy_claim']); self.assertEqual(result['raw_code'], code)
        self.assertEqual(evaluate_status({'A': 0, 'C': 0, 'F': 0}, contract)['fault']['state'], 'UNKNOWN')
        self.assertEqual(evaluate_status({}, contract)['fault']['state'], 'UNKNOWN')

    def test_reference_latch_separate_from_sensor_and_start_permission(self):
        c = {'schema_version': 1, 'reference': {'valid': 'R', 'physical_home': 'H'}}
        value = evaluate_status({'R': 1, 'H': 0}, c)['reference']
        self.assertTrue(value['valid']); self.assertFalse(value['physical_home']); self.assertFalse(value['start_permit_inferred'])
        c['reference']['physical_home'] = 'R'
        with self.assertRaises(AgentError): evaluate_status({}, c)

    def test_drive_request_ack_fresh_status_frequency_not_conflated(self):
        c = {'schema_version': 1, 'drive': dict(request='Q', ack='A', status='S', fresh='F', frequency='H')}
        value = evaluate_status({'Q': 1, 'A': 0, 'S': 0, 'F': 0, 'H': 50}, c)['drive']
        self.assertTrue(value['request']); self.assertEqual(value['ack'], 0); self.assertIsNone(value['frequency']); self.assertFalse(value['working_inferred'])

    def test_transfer_draft_fresh_readback_terminal_result_distinct(self):
        c = {'schema_version': 1, 'transfer': dict(draft='D', readback='R', fresh='F', request='Q', terminal_result='T')}
        value = evaluate_status({'D': 100, 'R': 80, 'F': 0, 'Q': 1, 'T': 0}, c)['transfer']
        self.assertEqual(value['draft'], 100); self.assertEqual(value['readback'], 80); self.assertFalse(value['applied_inferred'])
        c['transfer']['draft'] = 'R'
        with self.assertRaises(AgentError): evaluate_status({}, c)

    def test_sequential_visual_reviews_challenge_first_and_producer(self):
        a = {'reviewer': 'critic-a', 'candidate_sha256': 'x', 'review_sha256': 'first', 'open_important_findings': False, 'scope': 'visual-only'}
        b = dict(a, reviewer='critic-b', review_sha256='second', challenges_review_sha256='first')
        self.assertEqual(validate_aesthetic_receipts('x', 'maker', [a, b])['runtime'], 'NOT_ESTABLISHED')
        for bad in ([b, a], [a, dict(b, reviewer='maker')], [a, dict(b, candidate_sha256='y')], [a, dict(b, open_important_findings=True)]):
            with self.assertRaises(AgentError): validate_aesthetic_receipts('x', 'maker', bad)

    def test_design_csv_is_native_reference_not_vendor_import(self):
        value = design_ledger(Project(native()))
        self.assertEqual(len(value['rows']), 4); self.assertIn('GainValue', value['technical_csv'])
        self.assertFalse(value['vendor_import'])
        self.assertEqual(value['source_sha256'], digest(native()))
        self.assertEqual(value['source_payload_sha256'], digest(Project(native()).file.payload))


if __name__ == '__main__': unittest.main()
