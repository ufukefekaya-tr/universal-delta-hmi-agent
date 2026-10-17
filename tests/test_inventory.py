"""Prevent silent omissions from the delegated legacy extraction checklist."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class InventoryTests(unittest.TestCase):
    def test_every_discovered_feature_has_explicit_pending_or_evidenced_disposition(self):
        doc=json.loads((ROOT/'docs/FEATURE_MIGRATION.json').read_text('utf8'))
        rows=doc['features'];ids=[r['id'] for r in rows]
        self.assertEqual(set(ids),{f'D{i:02}' for i in range(1,45)}|{f'U{i:02}' for i in range(1,10)})
        self.assertEqual(len(ids),len(set(ids)))
        for row in rows:
            self.assertTrue(row['legacy_evidence'])
            self.assertTrue(row['required_disposition'])
            if row['migration_status']=='PORTED_AND_TESTED':
                self.assertTrue(row['implementation']);self.assertTrue(row['test_evidence'])
            else:
                self.assertIn(row['migration_status'],{'PENDING_DIASCREEN_REPOSITORY','PENDING_EXPLICIT_DISPOSITION','EXPLICITLY_UNSUPPORTED','BACKEND_DISPOSITION_VERIFIED'})

    def test_gui_exclusion_is_explicit_and_file_tools_are_not_lost(self):
        rows=json.loads((ROOT/'docs/FEATURE_MIGRATION.json').read_text('utf8'))['legacy_tools']
        names=[r['name'] for r in rows];self.assertEqual(len(names),22);self.assertEqual(len(set(names)),22)
        excluded={r['name'] for r in rows if r['status']=='INTENTIONALLY_EXCLUDED'}
        self.assertEqual(excluded,{'editor_windows','close_in_editor','open_in_editor','reload_in_editor'})
        self.assertIn('set_state_text',names);self.assertIn('macros',names);self.assertIn('addresses',names)

    def test_rollback_and_unqualified_history_not_promoted(self):
        rows={r['id']:r for r in json.loads((ROOT/'docs/FEATURE_MIGRATION.json').read_text('utf8'))['features']}
        self.assertEqual(rows['D28']['required_disposition'],'ROLLED_BACK_NOT_DEFAULT')
        self.assertEqual(rows['U02']['required_disposition'],'DISCOVERED_UNQUALIFIED')

    def test_actual_failure_regressions_remain_named(self):
        rows=json.loads((ROOT/'docs/REGRESSIONS.json').read_text('utf8'))['required_regressions']
        self.assertEqual(len(rows),21)
        self.assertEqual(len({r['id'] for r in rows}),21)
        self.assertTrue(all(r['scenario'] and r['status'] for r in rows))

    def test_delivered_dispositions_match_the_frozen_component_without_support_promotion(self):
        source=json.loads((ROOT/'components/dop_100/docs/SUPPORT_MATRIX.json').read_text('utf8'))
        public=json.loads((ROOT/'docs/FEATURE_MIGRATION.json').read_text('utf8'))
        expected={row['id']:row for row in source['features']}
        for row in public['features']:
            self.assertEqual(row['migration_status'],'BACKEND_DISPOSITION_VERIFIED')
            for a,b in [('support_level','support_level'),('implementation','implementation'),('test_evidence','planned_tests'),('limitations','limits')]:
                self.assertEqual(row[a],expected[row['id']][b])
        self.assertEqual(len(source['required_regressions']),21)
