"""Exercise installed family backends through real gateway stdio pipes.

Uses only original synthetic fixtures. Never vendor, runtime or panel acceptance.
The optional --jobs phase creates a separate trusted TEST-ONLY policy/config and
checks missing-review rejection, durable IDs and cancellation; it never writes
fake reviewer approvals. No existing workspace, profile or policy is replaced.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from delta_hmi.config import GatewayConfig, sha256, tree_sha256
from delta_hmi.gateway import DIA_TOOLS, FILE_TOOLS, JOB_TOOLS

# -I intentionally excludes the script directory from import search. Load only
# this explicitly named, repository-owned neutral fixture helper.
_fixture_spec = importlib.util.spec_from_file_location("neutral_probe_fixture", Path(__file__).with_name("probe_stdio.py"))
_fixture_module = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(_fixture_module)
dopb_fixture = _fixture_module.fixture


@asynccontextmanager
async def gateway_client(config):
    params = StdioServerParameters(command=sys.executable, args=["-I", "-B", "-m", "delta_hmi.cli", "serve", "--config", str(config)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            yield client


async def call(client, family, name, **arguments):
    response = await client.call_tool(family + "__" + name, arguments, read_timeout_seconds=120)
    if response.is_error:
        raise AssertionError(f"{family} {name}: {response}")
    return response.structured_content


def design():
    return {"schema_version": 1, "project_id": "neutral_probe", "profile_id": "synthetic_dopsoft2",
        "screens": [{"id": "main", "native_id": "1", "name": "Main", "width": 800, "height": 480, "elements": [
            {"id": "switch", "native_id": "1", "kind": "button", "x": 10, "y": 20, "width": 30, "height": 20,
             "behavior": "maintained", "role": "request", "binding": {"read": "state", "write": "command"},
             "states": [{"value": 0, "text": "OFF", "fill": "#112233"}, {"value": 1, "text": "ON", "fill": "#009955"}]}]}],
        "tags": [dict(id=tag, address=address, data_type="BOOL", access=access, channel="SIM", station="0", byte_order="little", word_order="little", native_binding={"link": "1", "mem_type": "0"})
                 for tag, address, access in [("state", "!D1", "Read"), ("command", "!M1", "ReadWrite")]], "macros": [], "alarms": []}


async def probe_files(config_path, dia_demo="neutral-demo", dia_profile="synthetic_diascreen"):
    cfg = GatewayConfig.load(config_path)
    if not all(entry.enabled for entry in cfg.backends.values()):
        raise ValueError("Both actual backends must be installed and enabled")
    b = cfg.backends["dop_b"]
    d = cfg.backends["dop_100"]
    folder = b.workspace / ("neutral-gateway-" + uuid.uuid4().hex)
    folder.mkdir()
    source, body = dopb_fixture()
    (folder / "source.dps").write_bytes(source)
    relative = folder.relative_to(b.workspace).as_posix()
    dia_relative = dia_demo + "/source.dpa"
    dia_path = d.workspace / dia_relative
    dia_source = dia_path.read_bytes()
    output_name = "neutral-candidate-" + uuid.uuid4().hex + ".dpa"
    tools_called = set()
    async with gateway_client(config_path) as client:
        listed = {tool.name for tool in (await client.list_tools()).tools}
        required = {"delta_catalog", "dop_100__close_session"} | {"dop_b__" + name for name in FILE_TOOLS | JOB_TOOLS} | {"dop_100__" + name for name in DIA_TOOLS}
        assert listed == required, (sorted(required - listed), sorted(listed - required))
        async def invoke(family, name, **arguments):
            data = await call(client, family, name, **arguments)
            tools_called.add(family + "__" + name)
            return data
        await invoke("dop_b", "capabilities", profile_id="synthetic_dopsoft2")
        b_sid = (await invoke("dop_b", "open_project", profile_id="synthetic_dopsoft2", source_path=relative + "/source.dps"))["session_id"]
        await invoke("dop_b", "inspect", session_id=b_sid)
        plan = await invoke("dop_b", "plan_changes", session_id=b_sid, design=design(), idempotency_key="neutral-probe", operations=[dict(op="set_property", screen_id="1", element_id="1", key="behavior", value="maintained")])
        await invoke("dop_b", "preview", session_id=b_sid, plan_id=plan["plan_id"])
        assert (await invoke("dop_b", "validate", session_id=b_sid, plan_id=plan["plan_id"]))["offline_pass"]
        approval = {key: value for key, value in plan.items() if key.endswith("_sha256")}
        approval.update(approved=True, authority="neutral_fixture_qualification", purpose="qualification_only")
        (folder / "approval.json").write_text(json.dumps(approval), encoding="utf8")
        await invoke("dop_b", "apply_plan", session_id=b_sid, plan_id=plan["plan_id"], approval_path=relative + "/approval.json")
        saved = await invoke("dop_b", "save_as", session_id=b_sid, output_path=relative + "/candidate.dps")
        difference = await invoke("dop_b", "diff", session_id=b_sid)
        candidate = (folder / "candidate.dps").read_bytes()
        assert hashlib.sha256(candidate).hexdigest() == saved["sha256"] == difference["candidate_sha256"]
        assert bytes(byte ^ 0x64 for byte in gzip.decompress(candidate[58:]))[41:] == body.replace(b"SubType=1\r\n", b"SubType=2\r\n", 1)
        assert (folder / "source.dps").read_bytes() == source
        await invoke("dop_100", "capabilities")
        d_sid = (await invoke("dop_100", "open_project", path=dia_relative, source_sha256=sha256(dia_path), profile_id=dia_profile))["session_id"]
        d_other = (await invoke("dop_100", "open_project", path=dia_relative, source_sha256=sha256(dia_path), profile_id=dia_profile))["session_id"]
        assert d_sid != d_other
        await invoke("dop_100", "inspect", session_id=d_sid, view="project")
        proposed = await invoke("dop_100", "plan_changes", session_id=d_sid, operations=[{"op": "set_text", "page_id": 1, "element_id": 10, "state_value": 1, "text": "AÇIK"}])
        digest = proposed["plan_sha256"]
        preview = await invoke("dop_100", "preview", session_id=d_sid, plan_sha256=digest, gallery=True)
        assert "AÇIK" in json.dumps(preview, ensure_ascii=False), "Proposed candidate preview did not show new caption"
        await invoke("dop_100", "validate", session_id=d_sid, plan_sha256=digest)
        wrong = await client.call_tool("dop_100__apply_plan", {"session_id": d_sid, "plan_sha256": digest, "approval_sha256": "0" * 64})
        assert wrong.is_error
        await invoke("dop_100", "apply_plan", session_id=d_sid, plan_sha256=digest, approval_sha256=digest)
        await invoke("dop_100", "save_as", session_id=d_sid, path=output_name, candidate_sha256=proposed["candidate_sha256"])
        d_diff = await invoke("dop_100", "diff", session_id=d_sid)
        dia_candidate = (d.workspace / output_name).read_bytes()
        assert hashlib.sha256(dia_candidate).hexdigest() == proposed["candidate_sha256"] == d_diff["candidate_sha256"]
        # Independently decode XOR/gzip framing; compare the ENTIRE native payload.
        source_offset = dia_source.index(b"\x1f\x8b")
        candidate_offset = dia_candidate.index(b"\x1f\x8b")
        source_decoded = bytes(value ^ 100 for value in gzip.decompress(dia_source[source_offset:]))
        candidate_decoded = bytes(value ^ 100 for value in gzip.decompress(dia_candidate[candidate_offset:]))
        old = "START ON".encode("utf-16-le") + b"\0\0"
        new = "AÇIK".encode("utf-16-le") + b"\0\0"
        old_record = b"wTextLen0=" + str(len(old)).encode() + b"\r\n" + old
        new_record = b"wTextLen0=" + str(len(new)).encode() + b"\r\n" + new
        expected_payload = source_decoded[41:].replace(old_record, new_record, 1)
        assert candidate_decoded[41:] == expected_payload
        assert dia_path.read_bytes() == dia_source
        other = await invoke("dop_100", "diff", session_id=d_other)
        assert other["candidate_sha256"] == hashlib.sha256(dia_source).hexdigest(), "Separate DIA process state was overwritten"
        # Real legacy aliases preserve read/catalog behavior; edit aliases only propose.
        for name, args in (("list_screens", {}), ("layout", {"page_id": 1}), ("element", {"page_id": 1, "element_id": 10}), ("find", {"query": "Start"}), ("addresses", {}), ("macros", {}), ("alarms", {}), ("screenshot_text", {}), ("pending_changes", {})):
            await invoke("dop_100", name, session_id=d_sid, **args)
        await invoke("dop_100", "rollback", session_id=d_sid)
        for family, token in (("dop_b", d_sid), ("dop_100", b_sid)):
            denied = await client.call_tool(family + "__inspect", {"session_id": token})
            assert denied.is_error
        await invoke("dop_100", "close_session", session_id=d_sid)
        await invoke("dop_100", "close_session", session_id=d_other)
    return {"status": "PASS", "scope": "Two real family processes, original synthetic file transactions only", "tools_discovered": sorted(listed), "tools_invoked_successfully": sorted(tools_called), "dop_b_candidate_sha256": hashlib.sha256(candidate).hexdigest(), "dop_100_candidate_sha256": hashlib.sha256(dia_candidate).hexdigest(), "independent_payload_comparison": "PASS_BOTH", "separate_diascreen_session_state": "PASS", "source_preserved": True, "vendor": "NOT_RUN", "physical": "NOT_RUN"}


JOB_FIXTURE_SCRIPT = r'''
import json,shutil,sys
from pathlib import Path
sys.dont_write_bytecode=True
snapshot,base=map(Path,sys.argv[1:3])
sys.path.insert(0,str(snapshot/'tests'))
from test_job_runner import JobFixture
from universal_hmi.job_policy import digest,canonical,tree_digest
fixture=JobFixture();fixture.setUp()
try:
    for name,source in [('workspace',fixture.workspace),('profiles',fixture.registry)]:
        shutil.copytree(source,base/name)
    for name in ('state','delivery','reviews'):(base/name).mkdir()
    policy=dict(fixture.policy)
    policy.update(reference='EXPLICIT NEUTRAL GATEWAY INTEGRATION TEST ONLY; NO PRODUCTION AUTHORITY',workspace=str(base/'workspace'),profiles_root=str(base/'profiles'),output_root=str(base/'delivery'),reviews_root=str(base/'reviews'),profile_tree_sha256=tree_digest(base/'profiles'))
    (base/'policy.json').write_bytes(canonical(policy)+b'\n')
    (base/'job.json').write_bytes(canonical(fixture.job)+b'\n')
finally:fixture.doCleanups()
'''


async def probe_jobs(config_path, snapshot):
    cfg = GatewayConfig.load(config_path)
    folder = config_path.parent / ("job-integration-" + uuid.uuid4().hex)
    folder.mkdir()
    subprocess.run([str(cfg.backends["dop_b"].python), "-I", "-B", "-c", JOB_FIXTURE_SCRIPT, str(snapshot.resolve()), str(folder)], check=True, timeout=60)
    data = json.loads(config_path.read_text(encoding="utf8"))
    b = data["backends"]["dop_b"]
    for key in ("workspace", "profiles", "state"):
        b[key] = (folder / key).relative_to(config_path.parent).as_posix()
    b["profiles_sha256"] = tree_sha256(folder / "profiles")
    b["job_policy"] = (folder / "policy.json").relative_to(config_path.parent).as_posix()
    b["job_policy_sha256"] = sha256(folder / "policy.json")
    job_config = config_path.parent / (folder.name + ".json")
    job_config.write_text(json.dumps(data), encoding="utf8")
    job = json.loads((folder / "job.json").read_text())
    token = None
    async with gateway_client(job_config) as client:
        await client.list_tools()
        assert not (folder / "state/jobs.sqlite3").exists(), "Discovery started job queue"
        await call(client, "dop_b", "preflight_job", job=job)
        submitted = await call(client, "dop_b", "submit_job", idempotency_key="neutral-route", job=job)
        token = submitted["job_id"]
        try:
            await call(client, "dop_b", "job_status", job_id=token)
            withheld = await client.call_tool("dop_b__job_result", {"job_id": token})
            assert withheld.is_error, "Unreviewed job was published"
        finally:
            await call(client, "dop_b", "cancel_job", job_id=token)
    async with gateway_client(job_config) as restarted:
        state = await call(restarted, "dop_b", "job_status", job_id=token)
        assert state["job_id"] == token
        assert state["status"] == "CANCELLED", state
    return {"status": "PASS", "tools": sorted(JOB_TOOLS), "discovery_side_effects": False, "restart_job_identity": "PASS", "missing_review_publication": "REJECTED", "terminal_state": "CANCELLED", "independent_review_acceptance": "NOT_FABRICATED", "scope": "Routing/persistence/cancellation only; not a completed reviewed job"}


async def run(args):
    answer = await probe_files(args.config.resolve(), args.dia_demo, args.dia_profile)
    if args.jobs:
        answer["jobs"] = await probe_jobs(args.config.resolve(), args.dopb_snapshot)
    else:
        answer["jobs"] = "NOT_RUN: invoke --jobs with the original public DOP-B fixture snapshot"
    return answer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--jobs", action="store_true")
    parser.add_argument("--dia-demo", default="neutral-demo", help="Neutral fixture directory relative to the configured DIA workspace")
    parser.add_argument("--dia-profile", default="synthetic_diascreen", help="Pinned neutral fixture profile ID")
    parser.add_argument("--dopb-snapshot", type=Path, default=Path(__file__).resolve().parents[1] / "components/dop_b")
    print(json.dumps(asyncio.run(run(parser.parse_args())), ensure_ascii=False, indent=2))
