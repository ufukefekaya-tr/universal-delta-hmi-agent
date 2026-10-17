from contextlib import asynccontextmanager
import json
from pathlib import Path
import tempfile
import unittest

from mcp import types
from delta_hmi.config import ConfigurationError, GatewayConfig, sha256
from delta_hmi.gateway import Gateway, JOB_TOOLS, result
try:
    from test_config import make_config
except ImportError:
    from tests.test_config import make_config


class JobSession:
    async def list_tools(self):
        return types.ListToolsResult(tools=[])
    async def call_tool(self, name, arguments):
        return result({"job_id": "a" * 32, "status": "WAITING_REVIEWS", "operation": name, "arguments": arguments})


class JobsGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.path, self.data = make_config(self.base)
        self.launched = []
        @asynccontextmanager
        async def connector(cfg):
            yield JobSession()
        @asynccontextmanager
        async def jobs(cfg):
            self.launched.append(cfg.family)
            yield JobSession()
        self.connector, self.jobs = connector, jobs
        self.gateway = Gateway(self.path, connector=connector, job_connector=jobs)

    async def asyncTearDown(self):
        await self.gateway.close()
        self.temp.cleanup()

    async def configure(self):
        await self.gateway.close()
        for name in ("delivery", "reviews"):
            (self.base / name).mkdir(exist_ok=True)
        policy = self.base / "job-policy.json"
        policy.write_text(json.dumps({"workspace": str(self.base / "dop_b/workspace"), "profiles_root": str(self.base / "dop_b/profiles"), "output_root": str(self.base / "delivery"), "reviews_root": str(self.base / "reviews")}))
        self.data["backends"]["dop_b"].update(job_policy="job-policy.json", job_policy_sha256=sha256(policy))
        self.path.write_text(json.dumps(self.data))
        self.gateway = Gateway(self.path, connector=self.connector, job_connector=self.jobs)

    async def test_discovery_never_starts_jobs_and_reports_missing_authority(self):
        names = {tool.name for tool in await self.gateway.list_tools()}
        self.assertTrue({"dop_b__" + name for name in JOB_TOOLS}.issubset(names))
        self.assertEqual(self.launched, [])
        self.assertFalse(self.gateway.catalog()["backends"]["dop_b"]["headless_jobs_authorized"])
        response = await self.gateway.call_tool("dop_b__submit_job", {"idempotency_key": "one", "job": {"profile_id": "sample"}})
        self.assertTrue(response.is_error)
        self.assertEqual(self.launched, [])

    async def test_configured_discovery_still_has_no_queue_side_effect(self):
        await self.configure()
        await self.gateway.list_tools()
        self.gateway.catalog()
        self.assertEqual(self.launched, [])

    async def test_policy_bound_job_identifier_survives_gateway_restart(self):
        await self.configure()
        submitted = await self.gateway.call_tool("dop_b__submit_job", {"idempotency_key": "one", "job": {"profile_id": "sample"}})
        self.assertFalse(submitted.is_error, submitted)
        token = submitted.structured_content["job_id"]
        self.assertEqual(submitted.structured_content["backend_job_id"], "a" * 32)
        await self.gateway.close()
        self.gateway = Gateway(self.path, connector=self.connector, job_connector=self.jobs)
        for name in ("job_status", "job_result", "cancel_job"):
            response = await self.gateway.call_tool("dop_b__" + name, {"job_id": token})
            self.assertFalse(response.is_error, response)
            self.assertEqual(response.structured_content["job_id"], token)
            self.assertEqual(response.structured_content["arguments"]["job_id"], "a" * 32)

    async def test_foreign_policy_family_and_raw_job_identifiers_rejected(self):
        await self.configure()
        for token in ("a" * 32, "dop_100:job:" + "a" * 32, "dop_b:job:" + "0" * 64 + ":" + "a" * 32):
            response = await self.gateway.call_tool("dop_b__job_status", {"job_id": token})
            self.assertTrue(response.is_error)
        self.assertEqual(self.launched, [])

    async def test_changed_authority_and_job_command_fields_rejected(self):
        await self.configure()
        response = await self.gateway.call_tool("dop_b__submit_job", {"idempotency_key": "one", "job": {"profile_id": "sample"}, "command": "arbitrary"})
        self.assertTrue(response.is_error)
        (self.base / "job-policy.json").write_text('{}')
        self.assertFalse(self.gateway.catalog()["backends"]["dop_b"]["headless_jobs_authorized"])
        response = await self.gateway.call_tool("dop_b__preflight_job", {"job": {"profile_id": "sample"}})
        self.assertTrue(response.is_error)
        self.assertEqual(self.launched, [])

    async def test_cross_family_job_output_root_rejected(self):
        await self.configure()
        policy = self.base / "job-policy.json"
        data = json.loads(policy.read_text())
        data["output_root"] = str(self.base / "dop_100/workspace")
        policy.write_text(json.dumps(data))
        self.data["backends"]["dop_b"]["job_policy_sha256"] = sha256(policy)
        self.path.write_text(json.dumps(self.data))
        with self.assertRaises(ConfigurationError):
            GatewayConfig.load(self.path)


if __name__ == "__main__": unittest.main()
