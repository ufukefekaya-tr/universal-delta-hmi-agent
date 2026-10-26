import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mcp import types
from delta_hmi.config import GatewayConfig
from delta_hmi.gateway import DIA_TOOLS, Gateway, connect_backend, result
try:
    from test_config import make_config
except ImportError:
    from tests.test_config import make_config


class DiaSession:
    def __init__(self):
        self.opened = None
        self.calls = []

    async def list_tools(self):
        return types.ListToolsResult(tools=[types.Tool(name=name, input_schema={"type": "object", "properties": {"plan_sha256": {"type": "string"}} if name == "preview" else {}, "additionalProperties": False}) for name in DIA_TOOLS | {"execute_shell"}])

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "open_project":
            self.opened = arguments["path"]
            return result({"source_sha256": arguments["source_sha256"], "profile_sha256": arguments["profile_sha256"]})
        return result({"source": self.opened, "operation": name, "arguments": arguments})


class DiascreenGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.path, self.data = make_config(self.base, ("dop_100",))
        self.created = []
        @asynccontextmanager
        async def connector(cfg):
            session = DiaSession()
            self.created.append(session)
            yield session
        self.gateway = Gateway(self.path, connector=connector)

    async def asyncTearDown(self):
        await self.gateway.close()
        self.temp.cleanup()

    async def open(self, path):
        response = await self.gateway.call_tool("dop_100__open_project", {"path": path, "source_sha256": "1" * 64, "profile_id": "sample"})
        self.assertFalse(response.is_error, response)
        return response.structured_content["session_id"]

    async def test_all_audited_tools_and_dynamic_schema_retained(self):
        listed = {tool.name: tool for tool in await self.gateway.list_tools()}
        self.assertEqual(len(DIA_TOOLS), 70)
        self.assertEqual(set(listed), {"delta_catalog", "dop_100__close_session"} | {"dop_100__" + name for name in DIA_TOOLS})
        opening = listed["dop_100__open_project"].input_schema
        self.assertEqual(set(opening["properties"]), {"profile_id", "path", "source_sha256"})
        preview = listed["dop_100__preview"].input_schema
        self.assertIn("plan_sha256", preview["properties"])
        self.assertIn("session_id", preview["required"])

    async def test_allowlist_matches_independent_component_integration_inventory(self):
        source = Path(__file__).resolve().parents[1] / "components/dop_100/INTEGRATION.json"
        declared = json.loads(source.read_text(encoding="utf8"))
        expected = set(declared["common_tools"]) | set(declared["extra_tools"]) | set(declared["legacy_names"])
        self.assertEqual(DIA_TOOLS, expected)
        self.assertEqual(declared["family"], "diascreen-dop100")
        self.assertEqual(declared["python_module"], "universal_diascreen_hmi.cli")

    async def test_two_project_sessions_cannot_overwrite_each_other(self):
        a, b = await self.open("a.dpa"), await self.open("b.dpa")
        self.assertNotEqual(a, b)
        for token, expected in ((a, "a.dpa"), (b, "b.dpa"), (a, "a.dpa")):
            response = await self.gateway.call_tool("dop_100__inspect", {"session_id": token})
            self.assertFalse(response.is_error)
            self.assertEqual(response.structured_content["source"], expected)

    async def test_profile_is_host_selected_canonical_and_cannot_be_replaced(self):
        await self.open("a.dpa")
        sent = self.created[-1].calls[0][1]
        expected = hashlib.sha256(json.dumps(sent["profile"], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        self.assertEqual(sent["profile_sha256"], expected)
        invalid = await self.gateway.call_tool("dop_100__open_project", {"path": "b.dpa", "source_sha256": "1" * 64, "profile_id": "sample", "profile": {"family": "anything"}})
        self.assertTrue(invalid.is_error)
        self.assertEqual(len(self.created), 1)

    async def test_all_aliases_forward_only_exact_arguments(self):
        token = await self.open("a.dpa")
        for name in DIA_TOOLS - {"capabilities", "open_project", "intake_source_profile"}:
            response = await self.gateway.call_tool("dop_100__" + name, {"session_id": token, "sentinel": name})
            self.assertFalse(response.is_error, name)
            self.assertEqual(self.created[-1].calls[-1], (name, {"sentinel": name}))
        self.assertTrue((await self.gateway.call_tool("dop_100__execute_shell", {"session_id": token})).is_error)

    async def test_fresh_intake_is_stateless_and_never_injects_profile_authority(self):
        args=dict(path='source.dpa',source_sha256='1'*64,expected_link='Link1',expected_station=1)
        response=await self.gateway.call_tool('dop_100__intake_source_profile',args)
        self.assertFalse(response.is_error);self.assertEqual(self.created[-1].calls[-1],('intake_source_profile',args))
        self.assertEqual(self.gateway.dia_sessions,{})
        for extra in ({'profile':{}},{'session_id':'foreign'},{'command':'arbitrary'}):
            self.assertTrue((await self.gateway.call_tool('dop_100__intake_source_profile',{**args,**extra})).is_error)
        listing={t.name:t for t in await self.gateway.list_tools()}
        self.assertNotIn('session_id',listing['dop_100__intake_source_profile'].input_schema['properties'])

    async def test_missing_foreign_closed_and_failed_sessions_rejected(self):
        token = await self.open("a.dpa")
        for value in (None, "dop_b:session_id:abc", "unrecognized"):
            self.assertTrue((await self.gateway.call_tool("dop_100__inspect", {"session_id": value})).is_error)
        handle, _ = self.gateway.dia_sessions[token]
        await handle.close()
        self.assertTrue((await self.gateway.call_tool("dop_100__inspect", {"session_id": token})).is_error)
        closed = await self.gateway.call_tool("dop_100__close_session", {"session_id": token})
        self.assertFalse(closed.is_error)
        self.assertTrue((await self.gateway.call_tool("dop_100__inspect", {"session_id": token})).is_error)

    async def test_session_limit_never_silently_evicts_existing_project(self):
        with patch("delta_hmi.gateway.MAX_DIA_SESSIONS", 2):
            first, second = await self.open("one.dpa"), await self.open("two.dpa")
            failed = await self.gateway.call_tool("dop_100__open_project", {"path": "three.dpa", "source_sha256": "1" * 64, "profile_id": "sample"})
            self.assertTrue(failed.is_error)
            self.assertEqual(set(self.gateway.dia_sessions), {first, second})

    async def test_real_launch_arguments_readonly_and_write_config(self):
        observed = []
        @asynccontextmanager
        async def stdio(params):
            observed.append(params)
            yield (None, None)
        class Session:
            def __init__(self, *args): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def initialize(self): pass
        for allowed in (False, True):
            self.data["backends"]["dop_100"]["allow_write"] = allowed
            self.path.write_text(json.dumps(self.data))
            cfg = GatewayConfig.load(self.path).backends["dop_100"]
            host={"DIA_HMI_REFERENCE_ROOT":"trusted-reference","DIA_HMI_FONT_ROOT":"trusted-fonts","UNTRUSTED_JOB_ENV":"secret-not-forwarded"}
            with patch.dict(os.environ,host), patch("delta_hmi.gateway.stdio_client", stdio), patch("delta_hmi.gateway.ClientSession", Session):
                async with connect_backend(cfg): pass
            self.assertEqual(observed[-1].env['DIA_HMI_REFERENCE_ROOT'],host['DIA_HMI_REFERENCE_ROOT'])
            self.assertEqual(observed[-1].env['DIA_HMI_FONT_ROOT'],host['DIA_HMI_FONT_ROOT'])
            self.assertNotIn('UNTRUSTED_JOB_ENV',observed[-1].env)
            self.assertIn("universal_diascreen_hmi.cli", observed[-1].args)
            self.assertNotIn("serve", observed[-1].args)
            self.assertNotIn("--profiles", observed[-1].args)
            self.assertEqual("--allow-write" in observed[-1].args, allowed)
            self.assertIn("--read-root", observed[-1].args)


if __name__ == "__main__": unittest.main()
