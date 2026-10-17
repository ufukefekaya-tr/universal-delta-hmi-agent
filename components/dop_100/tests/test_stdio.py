# SPDX-License-Identifier: Apache-2.0
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from universal_diascreen_hmi.errors import digest
from universal_diascreen_hmi.native import Project
from universal_diascreen_hmi.operations import canonical
from tests.fixtures import native, profile


class StdioTests(unittest.TestCase):
    def test_real_process_mutation_not_only_discovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'source.dpa').write_bytes(native())
            process = subprocess.Popen([sys.executable, '-B', '-X', 'utf8', '-m', 'universal_diascreen_hmi.cli',
                                        '--workspace', folder, '--allow-write'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            count = 0
            def rpc(method, params):
                nonlocal count
                count += 1
                request = {'jsonrpc': '2.0', 'id': count, 'method': method, 'params': params}
                process.stdin.write((json.dumps(request, ensure_ascii=False) + '\n').encode()); process.stdin.flush()
                line = process.stdout.readline()
                self.assertTrue(line, 'server closed stdout')
                result = json.loads(line)
                self.assertEqual(result['id'], count)
                return result['result']
            def call(name, **args): return rpc('tools/call', {'name': name, 'arguments': args})
            try:
                self.assertEqual(rpc('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'neutral', 'version': '1'}})['protocolVersion'], '2025-11-25')
                names = {x['name'] for x in rpc('tools/list', {})['tools']}
                self.assertTrue({'open_project', 'plan_changes', 'apply_plan', 'save_as', 'clone_element', 'alarms'} <= names)
                self.assertFalse({'open_in_editor', 'reload_in_editor', 'close_in_editor', 'editor_windows'} & names)
                p = profile()
                self.assertFalse(call('open_project', path='source.dpa', source_sha256=digest(native()), profile=p, profile_sha256=digest(canonical(p)))['isError'])
                self.assertFalse(call('inspect')['isError'])
                proposal = call('set_state_text', operation={'page_id': 1, 'element_id': 10, 'state_value': 1, 'text': 'AÇIK'})['structuredContent']
                self.assertFalse((root / 'candidate.dpa').exists())
                plan = proposal['plan_sha256']
                bad = call('apply_plan', plan_sha256=plan, approval_sha256='0' * 64); self.assertTrue(bad['isError'])
                self.assertFalse(call('apply_plan', plan_sha256=plan, approval_sha256=plan)['isError'])
                self.assertFalse(call('save_as', path='candidate.dpa', candidate_sha256=proposal['candidate_sha256'])['isError'])
                self.assertTrue(call('save', path='source.dpa', candidate_sha256=proposal['candidate_sha256'])['isError'])
                self.assertEqual((root / 'source.dpa').read_bytes(), native())
                q = Project((root / 'candidate.dpa').read_bytes())
                self.assertEqual(q.index.text(q.element(1, 10).states[1], 'wTextLen0'), 'AÇIK')
                self.assertEqual(call('diff')['structuredContent']['candidate_sha256'], proposal['candidate_sha256'])
                self.assertFalse(call('rollback')['isError'])
            finally:
                process.stdin.close(); process.wait(timeout=10)
                stdout, stderr = process.stdout.read(), process.stderr.read()
                process.stdout.close(); process.stderr.close()
                self.assertEqual(process.returncode, 0)
                self.assertEqual(stdout, b''); self.assertEqual(stderr, b'')

    def test_malformed_message_stdout_is_only_jsonrpc(self):
        with tempfile.TemporaryDirectory() as folder:
            input_bytes = b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\nnot-json\n'
            result = subprocess.run([sys.executable, '-B', '-m', 'universal_diascreen_hmi.cli', '--workspace', folder], input=input_bytes, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0); self.assertEqual(result.stderr, b'')
            messages = [json.loads(row) for row in result.stdout.splitlines()]
            self.assertEqual(len(messages), 2)
            self.assertTrue(all('error' in m for m in messages))


if __name__ == '__main__': unittest.main()
