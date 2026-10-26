"""A small stdio router. Native implementations stay in separate processes."""
import asyncio
from contextlib import asynccontextmanager
import copy
import json
import os
from pathlib import Path
import re
import secrets
import hashlib

from mcp import ClientSession, types
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from .config import ConfigurationError, GatewayConfig, FAMILIES, PACKAGES


FILE_TOOLS = frozenset({"open_project", "capabilities", "inspect", "plan_changes", "preview", "validate", "apply_plan", "save_as", "diff"})
IDENTIFIERS = frozenset({"session_id", "plan_id", "job_id"})
DIA_TOOLS = FILE_TOOLS | frozenset({"register_donor", "rollback", "pending_changes", "inspect_compiled", "evaluate_status", "list_screens", "layout", "element", "find", "addresses", "macros", "alarms", "set_property", "set_text", "rebind", "save", "screenshot_text", "clone_element", "clone_screen", "delete_element", "set_state_text"})
DIA_TOOLS = DIA_TOOLS | frozenset(['apply_contract_rebind', 'apply_offline_package', 'check_text_fit', 'configure_native_service', 'configure_numeric_fields', 'create_alarm_catalog', 'create_element', 'create_screen', 'import_symbol_catalog', 'import_tags', 'inspect_affine_scale', 'inspect_artifact_plan', 'inspect_endpoint', 'inspect_multilingual_text', 'inspect_native_catalog', 'inspect_native_plan', 'inspect_navigation', 'inspect_numeric_bindings', 'inspect_numeric_fields', 'inspect_offline_package', 'inspect_operation', 'plan_contract_rebind', 'plan_native_update', 'plan_offline_package', 'plan_register_import', 'preview_native_page', 'restore_candidate', 'restore_plan', 'save_new', 'validate_bindings', 'validate_native_candidate', 'validate_register_contract', 'verify_symbol_contract', 'vendor_open_save_reopen', 'vendor_compile', 'offline_simulator', 'build_transfer_package', 'inspect_transfer_package'])
DIA_TOOLS = DIA_TOOLS | {'reconcile_operation'}
JOB_TOOLS = frozenset({"preflight_job", "submit_job", "job_status", "job_result", "cancel_job"})
MAX_DIA_SESSIONS = 8


def job_tools():
    definitions = {
        "preflight_job": ({"job": {"type": "object"}}, ["job"]),
        "submit_job": ({"job": {"type": "object"}, "idempotency_key": {"type": "string"}}, ["job", "idempotency_key"]),
        **{name: ({"job_id": {"type": "string"}}, ["job_id"]) for name in ("job_status", "job_result", "cancel_job")},
    }
    return [types.Tool(name="dop_b__" + name, description="Persistent DOP-B job. Requires a trusted configured policy; discovery never starts its dispatcher.", input_schema={"type": "object", "properties": fields, "required": required, "additionalProperties": False}) for name, (fields, required) in definitions.items()]


class RoutingError(ValueError):
    pass


def result(data, error=False):
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))], structured_content=data, is_error=error)


@asynccontextmanager
async def connect_backend(config, *, job_mode=False):
    # No shell, arbitrary module, inherited PYTHONPATH or GUI. Job authority comes
    # exclusively from host configuration and never from a tool argument.
    env = {key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "HOME", "USERPROFILE", "LANG", "LC_ALL"}}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    args = ["-I", "-B", "-m", PACKAGES[config.family] + ".cli"]
    if config.family == "dop_b":
        args += ["--profiles", str(config.profiles), "serve", "--workspace", str(config.workspace)]
        if job_mode:
            config.verify_job_policy()
            args += ["--job-policy", str(config.job_policy), "--job-state", str(config.state)]
    else:
        if job_mode:
            raise RoutingError("DIAScreen has no DOP-B job dispatcher")
        # Trusted host configuration only; tool arguments cannot supply environment.
        for key in ("DIA_HMI_REFERENCE_ROOT", "DIA_HMI_FONT_ROOT"):
            if key in os.environ:
                env[key] = os.environ[key]
        args += ["--workspace", str(config.workspace), "--read-root", str(config.profiles)]
        if config.allow_write:
            args += ["--allow-write"]
    params = StdioServerParameters(command=str(config.python), args=args, cwd=str(config.root), env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


class BackendHandle:
    """Own a subprocess context in a single task (also on cancellation)."""
    def __init__(self, config, connector, timeout=30):
        self.config, self.connector, self.timeout = config, connector, timeout
        self.queue = asyncio.Queue()
        self.task = None
        self.instance = 0
        self.ready = None
        self.last_error = ""

    async def start(self):
        if self.task is None or self.task.done():
            self.instance += 1
            self.ready = asyncio.get_running_loop().create_future()
            self.task = asyncio.create_task(self._run())
        try:
            await asyncio.wait_for(asyncio.shield(self.ready), self.timeout)
        except Exception:
            await self.close()
            raise

    async def _run(self):
        current = None
        try:
            async with self.connector(self.config) as session:
                self.last_error = ""
                self.ready.set_result(True)
                while True:
                    method, args, current = await self.queue.get()
                    if current.cancelled():
                        current = None
                        continue
                    response = await getattr(session, method)(**args)
                    if not current.done():
                        current.set_result(response)
                    current = None
        except BaseException as exc:
            failure = RoutingError("Backend process unavailable: " + type(exc).__name__)
            if not isinstance(exc, asyncio.CancelledError):
                self.last_error = str(failure)
            if not self.ready.done():
                self.ready.set_exception(failure)
            if current is not None and not current.done():
                current.set_exception(failure)
            while not self.queue.empty():
                _, _, future = self.queue.get_nowait()
                if not future.done():
                    future.set_exception(failure)

    async def request(self, method, *, expected_instance=None, **kwargs):
        await self.start()
        if expected_instance is not None and expected_instance != self.instance:
            raise RoutingError("Backend restarted during request; identifiers are stale")
        future = asyncio.get_running_loop().create_future()
        await self.queue.put((method, kwargs, future))
        try:
            return await asyncio.wait_for(future, self.timeout)
        except asyncio.CancelledError:
            # A cancelled caller must not leave its queued mutation executing
            # invisibly. Closing the process also invalidates native sessions.
            await self.close()
            raise
        except (TimeoutError, RoutingError) as exc:
            self.last_error = "Backend request failed: " + type(exc).__name__
            await self.close()
            raise

    async def close(self):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None


class Gateway:
    def __init__(self, config, *, connector=connect_backend, job_connector=None, timeout=30):
        self.config = config if isinstance(config, GatewayConfig) else GatewayConfig.load(config)
        self.handles = {name: BackendHandle(cfg, connector, timeout) for name, cfg in self.config.backends.items() if cfg.enabled}
        self.tokens = {}
        self.reverse = {}
        self.connector, self.timeout = connector, timeout
        self.dia_sessions = {}
        self.dia_open_lock = asyncio.Lock()
        self.job_handle = None
        self.job_connector = job_connector or (lambda cfg: connect_backend(cfg, job_mode=True))

    def catalog(self):
        entries = {}
        for name, cfg in self.config.backends.items():
            row = {"family": FAMILIES[name], "enabled": cfg.enabled, "namespace": name + "__", "available": False, "reason": cfg.reason, "headless_jobs_exposed": name == "dop_b", "headless_jobs_authorized": cfg.job_policy is not None, "allow_write": cfg.allow_write if name == "dop_100" else "backend exact-approval contract", "session_isolation": "one process per open project" if name == "dop_100" else "explicit backend session identifiers"}
            if cfg.enabled:
                try:
                    cfg.verify()
                    row.update(available=True, reason="Pinned file backend; vendor/physical qualification is profile-specific")
                    if name == "dop_b" and cfg.job_policy is not None:
                        try:
                            self.config.verify_jobs()
                        except Exception as exc:
                            row.update(headless_jobs_authorized=False, job_reason=str(exc))
                    if self.handles[name].last_error:
                        row.update(available=False, reason=self.handles[name].last_error)
                except Exception as exc:
                    row["reason"] = str(exc)
            entries[name] = row
        return {"backends": entries, "automatic_fallback": False, "isolation": "Separate processes, not an OS security sandbox"}

    async def list_tools(self):
        tools = [types.Tool(name="delta_catalog", description="Report exact family availability and scope; never auto-fallback.", input_schema={"type": "object", "properties": {}, "additionalProperties": False})]
        if self.config.backends["dop_b"].enabled:
            tools.extend(job_tools())
        for family, handle in self.handles.items():
            try:
                handle.config.verify()
                listing = await handle.request("list_tools")
                if listing.next_cursor:
                    raise RoutingError("Paginated backend catalogs are not supported")
                for tool in listing.tools:
                    allowed = FILE_TOOLS if family == "dop_b" else DIA_TOOLS
                    if tool.name in allowed:
                        value = tool.model_copy(deep=True)
                        value.name = family + "__" + tool.name
                        if family == "dop_100":
                            value.output_schema = None
                            if tool.name == "open_project":
                                value.input_schema = {"type": "object", "properties": {"path": {"type": "string"}, "source_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "profile_id": {"type": "string"}}, "required": ["path", "source_sha256", "profile_id"], "additionalProperties": False}
                                value.description = (value.description or "") + " Opens a NEW isolated process and returns session_id; profile is selected only from the pinned registry."
                            elif tool.name != "capabilities":
                                value.input_schema.setdefault("properties", {})["session_id"] = {"type": "string"}
                                value.input_schema.setdefault("required", []).append("session_id")
                        tools.append(value)
                if family == "dop_100":
                    tools.append(types.Tool(name="dop_100__close_session", description="Close one isolated project session; source and saved outputs remain unchanged.", input_schema={"type": "object", "properties": {"session_id": {"type": "string"}}, "required": ["session_id"], "additionalProperties": False}))
            except Exception:
                # Catalog remains callable and the other family keeps working.
                continue
        return tools

    @staticmethod
    def _session_result(response, session_id):
        output = response.model_copy(deep=True)
        if isinstance(output.structured_content, dict):
            output.structured_content["session_id"] = session_id
        for block in output.content:
            if block.type == "text":
                try:
                    data = json.loads(block.text)
                except (ValueError, TypeError):
                    continue
                if isinstance(data, dict):
                    data["session_id"] = session_id
                    block.text = json.dumps(data, ensure_ascii=False)
        return output

    async def _diascreen(self, operation, arguments, cfg):
        if operation == "capabilities":
            if arguments:
                raise RoutingError("DIAScreen capabilities accepts no project/profile arguments")
            response = await self.handles["dop_100"].request("call_tool", name=operation, arguments={})
        elif operation == "open_project":
            if set(arguments) != {"path", "source_sha256", "profile_id"}:
                raise RoutingError("DIAScreen opening requires exactly path, source_sha256 and trusted profile_id")
            if not isinstance(arguments["path"], str) or Path(arguments["path"]).suffix.lower() != ".dpa":
                raise RoutingError("DIAScreen opening requires a DPA source; backend checks actual native bytes")
            profile = cfg.profile(arguments["profile_id"])
            profile_sha = hashlib.sha256(json.dumps(profile, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf8")).hexdigest()
            forwarded = {"path": arguments["path"], "source_sha256": arguments["source_sha256"], "profile": profile, "profile_sha256": profile_sha}
            async with self.dia_open_lock:
                if len(self.dia_sessions) >= MAX_DIA_SESSIONS:
                    raise RoutingError("DIAScreen session limit reached; close an existing session explicitly")
                handle = BackendHandle(cfg, self.connector, self.timeout)
                try:
                    response = await handle.request("call_tool", name=operation, arguments=forwarded)
                    cfg.verify()
                    if response.is_error:
                        await handle.close()
                        return response
                    token = "dop_100:session_id:" + secrets.token_hex(20)
                    self.dia_sessions[token] = (handle, handle.instance)
                    return self._session_result(response, token)
                except BaseException:
                    await handle.close()
                    raise
        else:
            token = arguments.pop("session_id", None)
            if not isinstance(token, str) or token not in self.dia_sessions:
                raise RoutingError("Unknown, stale or cross-family DIAScreen session_id")
            handle, instance = self.dia_sessions[token]
            if operation == "close_session":
                if arguments:
                    raise RoutingError("close_session accepts only session_id")
                del self.dia_sessions[token]
                await handle.close()
                return result({"closed": True, "session_id": token})
            if handle.task is None or handle.task.done() or handle.instance != instance:
                raise RoutingError("DIAScreen process ended; open a new isolated session")
            response = await handle.request("call_tool", expected_instance=instance, name=operation, arguments=arguments)
        cfg.verify()
        return response

    def _job_token(self, native):
        if not isinstance(native, str) or re.fullmatch("[0-9a-f]{32}", native) is None:
            raise RoutingError("Invalid native job identifier")
        return "dop_b:job:" + self.config.backends["dop_b"].job_policy_sha256 + ":" + native

    def _job_native(self, token):
        prefix = "dop_b:job:" + self.config.backends["dop_b"].job_policy_sha256 + ":"
        if not isinstance(token, str) or not token.startswith(prefix):
            raise RoutingError("Job identifier belongs to another family or policy")
        native = token[len(prefix):]
        if self._job_token(native) != token:
            raise RoutingError("Invalid job identifier")
        return native

    async def _jobs(self, operation, arguments, cfg):
        self.config.verify_jobs()
        required = {"job"} if operation == "preflight_job" else {"job", "idempotency_key"} if operation == "submit_job" else {"job_id"}
        if set(arguments) != required:
            raise RoutingError("Job arguments do not match the fixed tool contract")
        if "job" in arguments:
            job = arguments["job"]
            if not isinstance(job, dict):
                raise RoutingError("Job must be an object")
            cfg.profile(job.get("profile_id"))
        if "job_id" in arguments:
            arguments["job_id"] = self._job_native(arguments["job_id"])
        if self.job_handle is None:
            self.job_handle = BackendHandle(cfg, self.job_connector, self.timeout)
        response = await self.job_handle.request("call_tool", name=operation, arguments=arguments)
        cfg.verify()
        self.config.verify_jobs()
        output = response.model_copy(deep=True)
        def patch(data):
            if isinstance(data, dict) and "job_id" in data:
                data["backend_job_id"] = data["job_id"]
                data["job_id"] = self._job_token(data["job_id"])
        patch(output.structured_content)
        for block in output.content:
            if block.type == "text":
                try:
                    data = json.loads(block.text)
                except (ValueError, TypeError):
                    continue
                patch(data)
                block.text = json.dumps(data, ensure_ascii=False)
        return output

    def _unwrap(self, value, family, instance, kind):
        stored = self.tokens.get(value) if isinstance(value, str) else None
        if stored is None or stored[:3] != (family, instance, kind):
            raise RoutingError("Unknown, stale or cross-family " + kind)
        return stored[3]

    def _wrap(self, value, family, instance, kind):
        if not isinstance(value, str):
            raise RoutingError("Backend returned non-string identifier")
        key = (family, instance, kind, value)
        if key not in self.reverse:
            opaque = family + ":" + kind + ":" + secrets.token_hex(20)
            self.reverse[key] = opaque
            self.tokens[opaque] = key
        return self.reverse[key]

    def _response(self, response, family, instance):
        # Only protocol-defined top-level fields are handles. Never rewrite design/tag strings.
        output = response.model_copy(deep=True)
        structured = output.structured_content
        if isinstance(structured, dict):
            for kind in IDENTIFIERS:
                if kind in structured:
                    structured[kind] = self._wrap(structured[kind], family, instance, kind)
        for block in output.content:
            if block.type == "text":
                try:
                    data = json.loads(block.text)
                except (ValueError, TypeError):
                    continue
                if isinstance(data, dict):
                    for kind in IDENTIFIERS:
                        if kind in data:
                            data[kind] = self._wrap(data[kind], family, instance, kind)
                    block.text = json.dumps(data, ensure_ascii=False)
        return output

    async def call_tool(self, name, arguments=None):
        try:
            arguments = {} if arguments is None else copy.deepcopy(arguments)
            if not isinstance(arguments, dict):
                raise RoutingError("Tool arguments must be an object")
            if name == "delta_catalog":
                if arguments:
                    raise RoutingError("delta_catalog accepts no arguments")
                return result(self.catalog())
            if "__" not in name:
                raise RoutingError("An explicit family namespace is required")
            family, operation = name.split("__", 1)
            if family not in self.config.backends:
                raise RoutingError("Unknown or unsupported family operation")
            cfg = self.config.backends[family]
            cfg.verify()
            if family == "dop_100":
                if operation not in DIA_TOOLS | {"close_session"}:
                    raise RoutingError("Unknown or unaudited DIAScreen operation")
                return await self._diascreen(operation, arguments, cfg)
            if operation in JOB_TOOLS:
                return await self._jobs(operation, arguments, cfg)
            if operation not in FILE_TOOLS:
                raise RoutingError("Unknown or unsupported family operation")
            if operation in {"open_project", "capabilities"}:
                cfg.profile(arguments.get("profile_id"))
            if operation == "open_project" and arguments.get("source_path") is not None:
                source = arguments["source_path"]
                if not isinstance(source, str) or Path(source).suffix.lower() != {"dop_b": ".dps", "dop_100": ".dpa"}[family]:
                    raise RoutingError("Source suffix does not match route; native backend also checks content")
            handle = self.handles[family]
            await handle.start()
            instance = handle.instance
            for kind in IDENTIFIERS:
                if kind in arguments:
                    arguments[kind] = self._unwrap(arguments[kind], family, instance, kind)
            if "design" in arguments:
                design = arguments["design"]
                if not isinstance(design, dict):
                    raise RoutingError("Design must be an object")
                profile_id = design.get("profile_id")
                if profile_id is not None:
                    cfg.profile(profile_id)
            response = await handle.request("call_tool", expected_instance=instance, name=operation, arguments=arguments)
            cfg.verify()
            return self._response(response, family, instance)
        except Exception as exc:
            return result({"error": "DELTA_ROUTE", "detail": str(exc), "tool": name}, True)

    async def close(self):
        handles = list(self.handles.values()) + [item[0] for item in self.dia_sessions.values()] + ([self.job_handle] if self.job_handle is not None else [])
        await asyncio.gather(*(handle.close() for handle in handles))
        self.dia_sessions.clear()


def create_server(gateway):
    async def list_tools(context, params):
        return types.ListToolsResult(tools=await gateway.list_tools())

    async def call_tool(context, params):
        return await gateway.call_tool(params.name, params.arguments)

    return Server("universal-delta-hmi-agent", version="0.3.0", on_list_tools=list_tools, on_call_tool=call_tool)


async def serve(config_path):
    gateway = Gateway(config_path)
    server = create_server(gateway)
    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        await gateway.close()
