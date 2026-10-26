# SPDX-License-Identifier: Apache-2.0
"""Original dependency-free, newline UTF-8 JSON-RPC MCP stdio server."""
import argparse
import inspect as introspection
import json
import sys

from .errors import AgentError
from .session import Session, sha

PROTOCOLS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')
MAX_MESSAGE = 16 * 1024 * 1024


def object_schema(properties=None, required=()):
    return {'type': 'object', 'properties': properties or {}, 'required': list(required), 'additionalProperties': False}


STRING = {'type': 'string'}
HASH = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
INTEGER = {'type': 'integer', 'minimum': 0}
OBJECT = {'type': 'object'}
SORT = {'type': 'string', 'enum': ['layer', 'coordinate']}
COMMON = {
    'open_project': object_schema({'path': STRING, 'source_sha256': HASH, 'profile': OBJECT, 'profile_sha256': HASH}, ('path', 'source_sha256', 'profile', 'profile_sha256')),
    'capabilities': object_schema(),
    'inspect': object_schema({'view': {'type': 'string', 'enum': ['project', 'screens', 'layout', 'element', 'find', 'addresses', 'macros', 'alarms', 'symbols', 'resources', 'text', 'design']}, 'page_id': INTEGER, 'element_id': INTEGER, 'query': STRING, 'sort': SORT}),
    'plan_changes': object_schema({'operations': {'type': 'array', 'minItems': 1, 'maxItems': 1000, 'items': OBJECT}}, ('operations',)),
    'preview': object_schema({'page_id': INTEGER, 'values': OBJECT, 'gallery': {'type': 'boolean'}, 'plan_sha256': HASH}),
    'validate': object_schema({'plan_sha256': HASH}),
    'apply_plan': object_schema({'plan_sha256': HASH, 'approval_sha256': HASH}, ('plan_sha256', 'approval_sha256')),
    'save_as': object_schema({'path': STRING, 'candidate_sha256': HASH}, ('path', 'candidate_sha256')),
    'diff': object_schema(),
    'evaluate_status': object_schema({'values': OBJECT}, ('values',)),
    'register_donor': object_schema({'donor_id': STRING, 'path': STRING, 'sha256': HASH}, ('donor_id', 'path', 'sha256')),
    'rollback': object_schema(), 'pending_changes': object_schema(),
    'inspect_compiled': object_schema({'path': STRING, 'artifact_sha256': HASH, 'source_sha256': HASH, 'candidate_sha256': HASH, 'receipt': OBJECT}, ('path', 'artifact_sha256', 'source_sha256', 'candidate_sha256', 'receipt')),
}
ALIASES = {'list_screens': 'screens', 'layout': 'layout', 'element': 'element', 'find': 'find',
           'addresses': 'addresses', 'macros': 'macros', 'alarms': 'alarms', 'screenshot_text': 'text'}
EDIT_ALIASES = {'set_property': 'set_property', 'set_text': 'set_text', 'set_state_text': 'set_text',
                'rebind': 'rebind', 'clone_element': 'clone_element', 'clone_screen': 'clone_screen', 'delete_element': 'delete_element'}


def tools_list():
    result = []
    for name, schema in COMMON.items():
        result.append({'name': name, 'description': 'File-only ' + name + '. Source/profile/plan pins and offline support boundaries apply.', 'inputSchema': schema})
    for name in ALIASES:
        props, required = {}, []
        if name in ('layout', 'element', 'find', 'screenshot_text'):
            props['page_id'] = INTEGER
        if name in ('layout', 'screenshot_text'):
            props['sort'] = SORT
        if name == 'element':
            props['element_id'] = INTEGER; required += ['page_id', 'element_id']
        if name == 'find':
            props['query'] = STRING; required += ['query']
        result.append({'name': name, 'description': 'Legacy name mapped to indexed-only inspect view; no GUI.', 'inputSchema': object_schema(props, required)})
    for name in EDIT_ALIASES:
        result.append({'name': name, 'description': 'Legacy name creates a proposal only. Provide one explicit operation object; use apply_plan separately.',
                       'inputSchema': object_schema({'operation': OBJECT}, ('operation',))})
    result.append({'name': 'save', 'description': 'Legacy name for new-only save_as. overwrite_source/reload_editor are excluded.', 'inputSchema': COMMON['save_as']})
    return result


def call_tool(session, name, arguments):
    if not isinstance(arguments, dict):
        raise AgentError('PARAMETERS', 'Tool arguments must be an object')
    if name in COMMON:
        if name in ('preview', 'validate') and 'plan_sha256' in arguments:
            sha(arguments['plan_sha256'], 'plan_sha256')
        method = getattr(session, name)
    elif name in ALIASES:
        return session.inspect(view=ALIASES[name], **arguments)
    elif name in EDIT_ALIASES:
        if set(arguments) != {'operation'} or not isinstance(arguments['operation'], dict):
            raise AgentError('PARAMETERS', 'Editing alias requires exactly one operation object')
        operation = dict(arguments['operation'])
        if operation.get('op', EDIT_ALIASES[name]) != EDIT_ALIASES[name]:
            raise AgentError('PARAMETERS', 'Alias operation name differs')
        operation['op'] = EDIT_ALIASES[name]
        return session.plan_changes([operation])
    elif name == 'save':
        method = session.save_as
    else:
        raise AgentError('TOOL_UNSUPPORTED', 'Unknown or excluded tool')
    try:
        introspection.signature(method).bind(**arguments)
    except TypeError as exc:
        raise AgentError('PARAMETERS', 'Tool arguments do not match the declared schema') from exc
    return method(**arguments)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def serve(session, incoming=None, outgoing=None):
    incoming = incoming or sys.stdin.buffer
    outgoing = outgoing or sys.stdout.buffer
    initialized = False
    for _ in range(1000000):
        raw = incoming.readline(MAX_MESSAGE + 1)
        if not raw:
            return 0
        identity = None
        try:
            if len(raw) > MAX_MESSAGE or not raw.endswith(b'\n'):
                raise ValueError('oversized or unterminated message')
            request = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
            if not isinstance(request, dict) or request.get('jsonrpc') != '2.0' or not isinstance(request.get('method'), str):
                raise ValueError('invalid JSON-RPC request')
            identity = request.get('id')
            if 'id' in request and (type(identity) not in (str, int) or isinstance(identity, bool)):
                raise ValueError('invalid id')
            method, params = request['method'], request.get('params', {})
            if not isinstance(params, dict):
                raise ValueError('params must be an object')
            if 'id' not in request:
                # Client notifications are not requests and receive no stdout response.
                continue
            if method == 'initialize':
                requested = params.get('protocolVersion')
                initialized = True
                result = {'protocolVersion': requested if requested in PROTOCOLS else PROTOCOLS[0],
                          'capabilities': {'tools': {'listChanged': False}},
                          'serverInfo': {'name': 'universal-diascreen-hmi', 'version': '0.4.0'},
                          'instructions': 'File workspace only. Inspect first. Proposals require exact plan approval and --allow-write. Vendor/runtime acceptance is separate.'}
            elif method == 'ping':
                result = {}
            elif not initialized:
                raise AgentError('NOT_INITIALIZED', 'Initialize the isolated MCP process first')
            elif method == 'tools/list':
                result = {'tools': tools_list()}
            elif method == 'tools/call':
                try:
                    value = call_tool(session, params.get('name'), params.get('arguments', {}))
                    structured = value if isinstance(value, dict) else {'value': value}
                    result = {'content': [{'type': 'text', 'text': _dump(value)}], 'structuredContent': structured, 'isError': False}
                except AgentError as exc:
                    result = {'content': [{'type': 'text', 'text': _dump(exc.as_dict())}], 'structuredContent': {'error': exc.as_dict()}, 'isError': True}
                except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError, OSError):
                    result = {'content': [{'type': 'text', 'text': _dump({'code': 'INVALID_OR_UNQUALIFIED', 'message': 'Input is malformed, unsupported, or unavailable; no write was applied'})}], 'isError': True}
            else:
                outgoing.write((_dump({'jsonrpc': '2.0', 'id': identity, 'error': {'code': -32601, 'message': 'Method not found'}}) + '\n').encode('utf-8')); outgoing.flush()
                continue
            reply = {'jsonrpc': '2.0', 'id': identity, 'result': result}
        except (ValueError, UnicodeError, RecursionError):
            reply = {'jsonrpc': '2.0', 'id': identity, 'error': {'code': -32700, 'message': 'Malformed bounded UTF-8 JSON-RPC message'}}
        except AgentError as exc:
            reply = {'jsonrpc': '2.0', 'id': identity, 'error': {'code': -32600, 'message': exc.message, 'data': exc.as_dict()}}
        outgoing.write((_dump(reply) + '\n').encode('utf-8')); outgoing.flush()
        if len(raw) > MAX_MESSAGE:
            return 1
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description='Portable file-only DIAScreen/DOP-100 MCP')
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--read-root', action='append', default=[])
    parser.add_argument('--allow-write', action='store_true')
    args = parser.parse_args(argv)
    try:
        from .extended.hmi4_service import Service
        from .extended.transport import install,cli as transport_cli
        install()
        session = Service(args.workspace, allow_write=args.allow_write, read_roots=args.read_root)
        return transport_cli.serve(session)
    except (AgentError, OSError) as exc:
        print('Workspace startup failed: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
