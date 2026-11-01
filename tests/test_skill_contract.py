"""Skill integrity/compatibility gates; actual agent decisions are tested separately."""
import importlib.util
import json
from pathlib import Path
import shutil,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('check_skill',ROOT/'tools/check_skill.py')
skill_check=importlib.util.module_from_spec(spec);spec.loader.exec_module(skill_check)

class SkillContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.skill=Path(self.tmp.name)/'delta-hmi';shutil.copytree(ROOT/'skills/delta-hmi',self.skill)
    def change(self,fn):
        p=self.skill/'compatibility.json';v=json.loads(p.read_bytes());fn(v);p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
    def test_current_skill_matches_accepted_source_and_actual_schema_capture(self):
        result=skill_check.validate(self.skill);self.assertEqual(result['status'],'PASS');self.assertEqual(result['files'],6);self.assertEqual(result['behavioral_acceptance'],'SEPARATE_G4')
    def test_version_source_schema_and_family_projection_drift_refuse(self):
        for change in (lambda v:v['mcp'].update(umbrella_version='0.3.4'),lambda v:v['mcp']['components']['dop_b'].update(version='9.0.0'),lambda v:v['mcp']['components']['dop_100'].update(input_schema_sha256='0'*64),lambda v:v['mcp'].update(gateway_source_sha256='0'*64),lambda v:v['gateway_contract'].update(dop_b_prefix='dop_100__')):
            original=(self.skill/'compatibility.json').read_bytes();self.change(change)
            with self.assertRaises(ValueError):skill_check.validate(self.skill)
            (self.skill/'compatibility.json').write_bytes(original)
    def test_no_extra_code_or_native_customer_payload_is_packaged(self):
        (self.skill/'extra.dpa').write_bytes(b'not a distributable native seed')
        with self.assertRaises(ValueError):skill_check.validate(self.skill)
    def test_frontmatter_does_not_evaluate_yaml_tags_or_duplicate_keys(self):
        for header in ('---\nname: delta-hmi\nname: other\ndescription: "Example"\n---\n', '---\nname: delta-hmi\ndescription: !!python/object/apply:os.system ["untrusted"]\n---\n'):
            with self.assertRaises(ValueError):skill_check.frontmatter(header.encode())
    def test_missing_reference_and_implicit_policy_change_refuse(self):
        path=self.skill/'agents/openai.yaml';original=path.read_bytes();path.write_bytes(original.replace(b'allow_implicit_invocation: true',b'allow_implicit_invocation: false'))
        with self.assertRaises(ValueError):skill_check.validate(self.skill)
        path.write_bytes(original);(self.skill/'references/dop-b.md').unlink()
        with self.assertRaises(ValueError):skill_check.validate(self.skill)

if __name__=='__main__':unittest.main()
