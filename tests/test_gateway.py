import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import tempfile
import unittest

from mcp import types
from delta_hmi.config import GatewayConfig
from delta_hmi.gateway import Gateway, result, create_server
try:
    from test_config import make_config
except ImportError:
    from tests.test_config import make_config


class FakeSession:
    def __init__(self, family):
        self.family, self.calls, self.fail = family, [], False

    async def list_tools(self):
        return types.ListToolsResult(tools=[types.Tool(name=name, input_schema={"type": "object"}) for name in ("open_project", "capabilities", "inspect", "plan_changes", "preview", "validate", "apply_plan", "save_as", "diff", "evil_shell")])

    async def call_tool(self, name, arguments):
        if self.fail:
            raise ConnectionError("gone")
        self.calls.append((name, arguments))
        if name == "open_project":
            return result({"session_id": "same-native-session", "family": self.family})
        if name == "plan_changes":
            return result({"plan_id": "same-native-plan", "design": {"session_id": "ordinary-design-value"}, "source_sha256": "native-hash"})
        return result({"family": self.family, "echo": arguments})


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.path, self.data = make_config(self.base)
        self.sessions = {}
        @asynccontextmanager
        async def connector(cfg):
            session = FakeSession(cfg.family)
            self.sessions[cfg.family] = session
            yield session
        self.gateway = Gateway(self.path, connector=connector)

    async def asyncTearDown(self):
        await self.gateway.close()
        self.temp.cleanup()

    async def open(self, family="dop_b"):
        value = await self.gateway.call_tool(family + "__open_project", {"profile_id": "sample"})
        self.assertFalse(value.is_error)
        return value.structured_content["session_id"]

    async def test_namespaced_catalog_and_allowlist(self):
        tools = await self.gateway.list_tools()
        self.assertEqual(len(tools), 19)
        self.assertFalse(any("evil_shell" in t.name for t in tools))
        self.assertIsNotNone(create_server(self.gateway))

    async def test_round_trip_and_cross_family_denial(self):
        one, two = await self.open(), await self.open("dop_100")
        self.assertNotEqual(one, two)
        bad = await self.gateway.call_tool("dop_100__inspect", {"session_id": one})
        self.assertTrue(bad.is_error)
        good = await self.gateway.call_tool("dop_b__inspect", {"session_id": one})
        self.assertFalse(good.is_error)
        self.assertEqual(self.sessions["dop_b"].calls[-1][1]["session_id"], "same-native-session")

    async def test_plan_identifier_and_domain_data_preserved(self):
        session = await self.open()
        planned = await self.gateway.call_tool("dop_b__plan_changes", {"session_id": session, "design": {"profile_id": "sample"}, "idempotency_key": "a"})
        payload = planned.structured_content
        self.assertEqual(payload["design"]["session_id"], "ordinary-design-value")
        self.assertEqual(payload["source_sha256"], "native-hash")
        self.assertEqual(json.loads(planned.content[0].text)["plan_id"], payload["plan_id"])
        validated = await self.gateway.call_tool("dop_b__validate", {"session_id": session, "plan_id": payload["plan_id"]})
        self.assertFalse(validated.is_error)
        self.assertEqual(self.sessions["dop_b"].calls[-1][1]["plan_id"], "same-native-plan")

    async def test_kind_mismatch_rejected(self):
        session = await self.open()
        value = await self.gateway.call_tool("dop_b__validate", {"session_id": session, "plan_id": session})
        self.assertTrue(value.is_error)

    async def test_stale_identifier_after_restart(self):
        session = await self.open()
        await self.gateway.handles["dop_b"].close()
        value = await self.gateway.call_tool("dop_b__inspect", {"session_id": session})
        self.assertTrue(value.is_error)

    async def test_backend_failure_isolation(self):
        one, two = await self.open(), await self.open("dop_100")
        self.sessions["dop_b"].fail = True
        failed = await self.gateway.call_tool("dop_b__inspect", {"session_id": one})
        healthy = await self.gateway.call_tool("dop_100__inspect", {"session_id": two})
        self.assertTrue(failed.is_error)
        self.assertFalse(healthy.is_error)
        self.assertFalse(self.gateway.catalog()["backends"]["dop_b"]["available"])

    async def test_hung_backend_timeout_and_healthy_peer(self):
        one, two = await self.open(), await self.open("dop_100")
        async def hanging(**kwargs):
            await asyncio.Event().wait()
        self.sessions["dop_b"].call_tool = hanging
        self.gateway.handles["dop_b"].timeout = .03
        failed = await self.gateway.call_tool("dop_b__inspect", {"session_id": one})
        healthy = await self.gateway.call_tool("dop_100__inspect", {"session_id": two})
        self.assertTrue(failed.is_error)
        self.assertFalse(healthy.is_error)

    async def test_process_restart_between_mapping_and_dispatch(self):
        from delta_hmi.gateway import RoutingError
        handle = self.gateway.handles["dop_b"]
        await handle.start()
        instance = handle.instance
        await handle.close()
        with self.assertRaises(RoutingError):
            await handle.request("call_tool", expected_instance=instance, name="inspect", arguments={"session_id": "native-old"})
        self.assertFalse(self.sessions["dop_b"].calls)

    async def test_backend_error_semantics_preserved(self):
        session = await self.open()
        async def denied(**kwargs):
            return result({"error": "APPROVAL_REQUIRED", "detail": "Exact human approval missing"}, True)
        self.sessions["dop_b"].call_tool = denied
        response = await self.gateway.call_tool("dop_b__inspect", {"session_id": session})
        self.assertTrue(response.is_error)
        self.assertEqual(response.structured_content["error"], "APPROVAL_REQUIRED")

    async def test_pin_checked_every_request(self):
        session = await self.open()
        (self.base / "dop_b/backend/runtime/site-packages/universal_hmi/__init__.py").write_text("changed")
        value = await self.gateway.call_tool("dop_b__inspect", {"session_id": session})
        self.assertTrue(value.is_error)
        tools = await self.gateway.list_tools()
        self.assertEqual(len(tools), 10)
        self.assertFalse(self.gateway.catalog()["backends"]["dop_b"]["available"])

    async def test_no_implicit_route_or_headless_command(self):
        for name in ("open_project", "dop_c__inspect", "dop_b__submit_job", "dop_b__evil_shell"):
            self.assertTrue((await self.gateway.call_tool(name, {})).is_error)

    async def test_wrong_suffix_and_unknown_profile(self):
        for args in ({"profile_id": "sample", "source_path": "file.dpa"}, {"profile_id": "../sample"}, {"profile_id": "missing"}):
            self.assertTrue((await self.gateway.call_tool("dop_b__open_project", args)).is_error)
        self.assertFalse(self.sessions)

    async def test_disabled_family_visible(self):
        self.data["backends"]["dop_100"] = {"enabled": False, "reason": "License not granted"}
        self.path.write_text(json.dumps(self.data))
        other = Gateway(self.path)
        try:
            catalog = await other.call_tool("delta_catalog")
            self.assertEqual(catalog.structured_content["backends"]["dop_100"]["reason"], "License not granted")
            self.assertTrue((await other.call_tool("dop_100__open_project", {"profile_id": "sample"})).is_error)
        finally:
            await other.close()

    async def test_concurrent_requests_stay_routed(self):
        handles = await asyncio.gather(*(self.open(family) for family in ("dop_b", "dop_100") * 5))
        self.assertEqual(len(set(handles)), 2)
        self.assertTrue(handles[0].startswith("dop_b:"))
        self.assertTrue(handles[1].startswith("dop_100:"))


if __name__ == "__main__":
    unittest.main()
