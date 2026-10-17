"""The intentionally small, stdio-only MCP surface."""
from mcp.server import MCPServer
from typing import Any
from functools import wraps
import json
from mcp.server.mcpserver.exceptions import ToolError
from .errors import HmiError
from .service import FileService
from . import __version__


def tool_errors(fn):
    @wraps(fn)
    def guarded(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HmiError as exc:
            raise ToolError(json.dumps(exc.as_dict(), ensure_ascii=False)) from exc
        except (FileNotFoundError, FileExistsError, json.JSONDecodeError) as exc:
            raise ToolError(str(exc)) from exc
    return guarded


def create_server(workspace, profiles_dir, *, job_policy=None, job_state=None):
    service = FileService(workspace, profiles_dir)
    jobs = None
    if job_policy is not None:
        if job_state is None:
            raise HmiError("JOB_POLICY", "Trusted job state directory required")
        from .job_runner import JobRunner
        jobs = JobRunner(job_policy, job_state)
        if jobs.policy.workspace != service.workspace or jobs.policy.profiles_root != service.profiles_dir:
            raise HmiError("JOB_POLICY", "MCP workspace/registry must match trusted task policy")
        if jobs.store.has_unfinished():
            jobs.start_dispatcher()
    server = MCPServer("universal-hmi-agents", version=__version__,
                       instructions="File-only tools. Legacy transactions require exact design approval. Configured headless jobs use host task-start authority and independent reviews. No vendor or physical acceptance is implied.")

    @server.tool(structured_output=True)
    @tool_errors
    def open_project(profile_id: str, source_path: str | None = None) -> dict[str, Any]:
        """Open an immutable relative source, or a conceptual design session."""
        return service.open_project(profile_id, source_path)

    @server.tool(structured_output=True)
    @tool_errors
    def capabilities(profile_id: str) -> dict[str, Any]:
        """Return exact profile capabilities and evidence limitations."""
        return service.capabilities(profile_id)

    @server.tool(structured_output=True)
    @tool_errors
    def inspect(session_id: str) -> dict[str, Any]:
        """Read actual decoded source fields, screens, text and bindings."""
        return {"inventory": service.inspect(session_id)}

    @server.tool(structured_output=True)
    @tool_errors
    def plan_changes(session_id: str, design: dict, idempotency_key: str,
                     operations: list[dict] | None = None) -> dict[str, Any]:
        """Prepare an exact change receipt; omitted operations compile calibrated design patches."""
        return service.plan_changes(session_id, design, operations, idempotency_key)

    @server.tool(structured_output=True)
    @tool_errors
    def preview(session_id: str, plan_id: str, output_path: str | None = None,
                values: dict | None = None, states: dict | None = None, valid: bool = True) -> dict[str, Any]:
        """Render conceptual IR with visible example/stale states, never live values."""
        return service.preview(session_id, plan_id, output_path, values, states, valid)

    @server.tool(structured_output=True)
    @tool_errors
    def validate(session_id: str, plan_id: str) -> dict[str, Any]:
        """Validate geometry, behavior, typed addresses and calibrated native gate."""
        return service.validate(session_id, plan_id)

    @server.tool(structured_output=True)
    @tool_errors
    def apply_plan(session_id: str, plan_id: str, approval_path: str) -> dict[str, Any]:
        """Apply exact approved operations in memory; source bytes remain immutable."""
        return service.apply_plan(session_id, plan_id, approval_path)

    @server.tool(structured_output=True)
    @tool_errors
    def save_as(session_id: str, output_path: str) -> dict[str, Any]:
        """Create a new candidate atomically, then reopen and cross-check it."""
        return service.save_as(session_id, output_path)

    @server.tool(structured_output=True)
    @tool_errors
    def diff(session_id: str) -> dict[str, Any]:
        """Show byte hashes and controlled operations alongside decoded output."""
        return service.diff(session_id)

    if jobs is not None:
        @server.tool(structured_output=True)
        @tool_errors
        def preflight_job(job: dict) -> dict[str, Any]:
            """Check a complete DOP-B job against host authority and native feature gates."""
            return jobs.preflight(job)

        @server.tool(structured_output=True)
        @tool_errors
        def submit_job(idempotency_key: str, job: dict) -> dict[str, Any]:
            """Persist a job and launch the fixed headless worker. No command supplied by job."""
            record = jobs.submit(idempotency_key, job)
            jobs.launch(record['job_id'])
            return record

        @server.tool(structured_output=True)
        @tool_errors
        def job_status(job_id: str) -> dict[str, Any]:
            """Read durable state. WAITING_REVIEWS identifies artifact-bound reviewer work."""
            return jobs.status(job_id)

        @server.tool(structured_output=True)
        @tool_errors
        def job_result(job_id: str) -> dict[str, Any]:
            """Return only a completed, still intact package with final review evidence."""
            return jobs.result(job_id)

        @server.tool(structured_output=True)
        @tool_errors
        def cancel_job(job_id: str) -> dict[str, Any]:
            """Cancel unpublished work; do not delete any completed delivery."""
            return jobs.store.cancel(job_id)

    return server
