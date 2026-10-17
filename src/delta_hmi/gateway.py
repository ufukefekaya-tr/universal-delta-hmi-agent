"""A small stdio router. Native implementations stay in separate processes."""
import asyncio
from contextlib import asynccontextmanager
import copy
import json
import os
from pathlib import Path
import secrets

from mcp import ClientSession, types
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from .config import ConfigurationError, GatewayConfig, FAMILIES, PACKAGES


FILE_TOOLS = frozenset({"open_project", "capabilities", "inspect", "plan_changes", "preview", "validate", "apply_plan", "save_as", "diff"})
IDENTIFIERS = frozenset({"session_id", "plan_id", "job_id"})


class RoutingError(ValueError):
    pass


def result(data, error=False):
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))], structured_content=data, is_error=error)


@asynccontextmanager
async def connect_backend(config):
    # Deliberately no shell, arbitrary module, inherited PYTHONPATH, job-policy or GUI.
    env = {key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "HOME", "USERPROFILE", "LANG", "LC_ALL"}}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    params = StdioServerParameters(command=str(config.python), args=["-I", "-B", "-m", PACKAGES[config.family] + ".cli", "--profiles", str(config.profiles), "serve", "--workspace", str(config.workspace)], cwd=str(config.root), env=env)
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
    def __init__(self, config, *, connector=connect_backend, timeout=30):
        self.config = config if isinstance(config, GatewayConfig) else GatewayConfig.load(config)
        self.handles = {name: BackendHandle(cfg, connector, timeout) for name, cfg in self.config.backends.items() if cfg.enabled}
        self.tokens = {}
        self.reverse = {}

    def catalog(self):
        entries = {}
        for name, cfg in self.config.backends.items():
            row = {"family": FAMILIES[name], "enabled": cfg.enabled, "namespace": name + "__", "available": False, "reason": cfg.reason, "headless_jobs_exposed": False}
            if cfg.enabled:
                try:
                    cfg.verify()
                    row.update(available=True, reason="Pinned file backend; vendor/physical qualification is profile-specific")
                    if self.handles[name].last_error:
                        row.update(available=False, reason=self.handles[name].last_error)
                except Exception as exc:
                    row["reason"] = str(exc)
            entries[name] = row
        return {"backends": entries, "automatic_fallback": False, "isolation": "Separate processes, not an OS security sandbox"}

    async def list_tools(self):
        tools = [types.Tool(name="delta_catalog", description="Report exact family availability and scope; never auto-fallback.", input_schema={"type": "object", "properties": {}, "additionalProperties": False})]
        for family, handle in self.handles.items():
            try:
                handle.config.verify()
                listing = await handle.request("list_tools")
                if listing.next_cursor:
                    raise RoutingError("Paginated backend catalogs are not supported")
                for tool in listing.tools:
                    if tool.name in FILE_TOOLS:
                        value = tool.model_copy(deep=True)
                        value.name = family + "__" + tool.name
                        tools.append(value)
            except Exception:
                # Catalog remains callable and the other family keeps working.
                continue
        return tools

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
            if family not in self.config.backends or operation not in FILE_TOOLS:
                raise RoutingError("Unknown or unsupported family operation")
            cfg = self.config.backends[family]
            cfg.verify()
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
        await asyncio.gather(*(handle.close() for handle in self.handles.values()))


def create_server(gateway):
    async def list_tools(context, params):
        return types.ListToolsResult(tools=await gateway.list_tools())

    async def call_tool(context, params):
        return await gateway.call_tool(params.name, params.arguments)

    return Server("universal-delta-hmi-agent", version="0.1.0", on_list_tools=list_tools, on_call_tool=call_tool)


async def serve(config_path):
    gateway = Gateway(config_path)
    server = create_server(gateway)
    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        await gateway.close()
