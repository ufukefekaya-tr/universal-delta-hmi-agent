from copy import deepcopy
from universal_hmi.errors import HmiError
from universal_hmi.job_policy import TaskPolicy, relative_file, read_object
from universal_hmi.job_runner import write_json
from test_job_runner import JobFixture


class JobPolicyTests(JobFixture):
    def test_policy_and_input_changes_revoke_authority(self):
        (self.workspace/'source.dps').write_bytes(b'changed')
        with self.assertRaises(HmiError):self.runner.preflight(self.job)

    def test_unpinned_workspace_asset_rejected(self):
        (self.workspace/'unexpected.txt').write_text('new')
        with self.assertRaises(HmiError):self.runner.preflight(self.job)

    def test_job_cannot_inject_policy_and_malformed_paths(self):
        for value in ([],{},'../source.dps'):
            job=deepcopy(self.job);job['source_path']=value
            with self.assertRaises(HmiError):self.runner.preflight(job)
        job=deepcopy(self.job);job['policy']={}
        with self.assertRaises(HmiError):self.runner.preflight(job)

    def test_no_self_review_or_writable_authority(self):
        for key,value in [('reviewers',dict(self.policy['reviewers'],aesthetic_first='test-author')),
                          ('reviews_root',str(self.workspace))]:
            policy=deepcopy(self.policy);policy[key]=value;write_json(self.policy_path,policy)
            with self.assertRaises(HmiError):TaskPolicy(self.policy_path)

    def test_path_and_json_ambiguity_rejected(self):
        for path in ('../x','a//b','a/./b','NUL.txt','C:/x','a\\b','a:b','x.','/x'):
            with self.assertRaises(HmiError):relative_file(self.workspace,path)
        p=self.base/'duplicate.json';p.write_text('{"a":1,"a":2}')
        with self.assertRaises(HmiError):read_object(p)
