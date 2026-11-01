# SPDX-License-Identifier: Apache-2.0
"""Read-only packaging/compatibility checks, not a behavioral skill evaluator.

Uses the existing goal receipts. The authored YAML subset stays dependency-free;
the first-party skill validator is a separately recorded authoring check.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tomllib

ROOT=Path(__file__).resolve().parents[1]
FILES={'SKILL.md','LICENSE','compatibility.json','agents/openai.yaml','references/dop-b.md','references/dop-100.md'}


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()


def checked(path):
    path=Path(path)
    for p in (path,*path.parents):
        if p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()):raise ValueError('Linked skill member')
    if not path.is_file() or path.stat().st_nlink!=1 or path.stat().st_size>1024*1024:raise ValueError('Nonregular, hardlinked or oversized skill metadata')
    return path.read_bytes()


def frontmatter(raw):
    text=raw.decode('utf8');match=re.match(r'\A---\n(.*?)\n---\n',text,re.S)
    if not match:raise ValueError('Missing canonical skill frontmatter')
    fields={}
    for line in match[1].splitlines():
        key,sep,value=line.partition(': ')
        if not sep or key not in ('name','description') or key in fields:raise ValueError('Unsupported or duplicate frontmatter member')
        if key=='description' and not value.startswith('"'):raise ValueError('Authored descriptions use JSON-quoted YAML strings, never tags or expressions')
        fields[key]=json.loads(value) if value.startswith('"') else value
    if fields.get('name')!='delta-hmi' or not isinstance(fields.get('description'),str) or not 1<=len(fields['description'])<=1024:raise ValueError('Invalid skill identity/description')
    return text


def ui_metadata(raw):
    result={};section=None
    for line in raw.decode('utf8').splitlines():
        if line in ('interface:','policy:'):
            section=line[:-1]
            if section in result:raise ValueError('Duplicate UI section')
            result[section]={};continue
        if not section or not line.startswith('  '):raise ValueError('Unsupported UI YAML subset')
        key,sep,value=line[2:].partition(': ')
        if not sep or key in result[section]:raise ValueError('Duplicate UI field')
        result[section][key]=json.loads(value)
    if set(result)!={'interface','policy'} or set(result['interface'])!={'display_name','short_description','default_prompt'}:raise ValueError('Unexpected UI fields')
    interface=result['interface']
    if not all(isinstance(v,str) for v in interface.values()) or not 25<=len(interface['short_description'])<=64 or '$delta-hmi'not in interface['default_prompt']:raise ValueError('Invalid UI text')
    if result['policy']!={'allow_implicit_invocation':True}:raise ValueError('Implicit invocation was not requested to be disabled')
    return result


def validate(skill=None,repo=ROOT):
    repo=Path(repo).resolve();skill=Path(skill or repo/'skills/delta-hmi')
    for p in (skill,*skill.parents):
        if p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()):raise ValueError('Linked skill root')
    skill=skill.resolve()
    members={p.relative_to(skill).as_posix() for p in skill.rglob('*') if p.is_file() or p.is_symlink()}
    if members!=FILES:raise ValueError('Skill allowlist mismatch; no code, native assets or extra payloads permitted')
    blobs={name:checked(skill/name) for name in FILES};entry=frontmatter(blobs['SKILL.md']);ui_metadata(blobs['agents/openai.yaml'])
    for name in ('SKILL.md','references/dop-b.md','references/dop-100.md'):
        for link in re.findall(r'\]\(([^)]+)\)',blobs[name].decode('utf8')):
            path=Path(link)
            if path.is_absolute() or '..'in path.parts or ':'in link or not (skill/Path(name).parent/path).is_file():raise ValueError('Missing or unsafe local skill reference')
    if not blobs['LICENSE'].startswith(b'MIT License\n') or b'Permission is hereby granted'not in blobs['LICENSE']:raise ValueError('Original skill MIT license absent')
    record=json.loads(blobs['compatibility.json']);mcp=record['mcp']
    if record['schema']!='delta.hmi.companion-skill.v1' or record['skill']!=dict(name='delta-hmi',version='0.1.0',license='MIT'):raise ValueError('Unsupported companion contract')
    spec=importlib.util.spec_from_file_location('skill_goal_receipts',repo/'tools/check_goals.py');goals_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(goals_module)
    goals=json.loads(checked(repo/'goals/hmi-skill-transition.json'));goals_module.validate(goals,root=repo)
    if next(g for g in goals['goals'] if g['id']=='G2')['state']!='PASS':raise ValueError('MCP G2 is not accepted')
    project=tomllib.loads(checked(repo/'pyproject.toml').decode())['project'];version=project['version']
    if mcp['repository']!=project['urls']['Repository']:raise ValueError('Skill points at another repository')
    if mcp['umbrella_version']!=version or not re.fullmatch('[0-9a-f]{40}',mcp['accepted_source_commit']):raise ValueError('MCP version/source identity mismatch')
    if mcp['gateway_source_sha256']!=sha(checked(repo/'src/delta_hmi/gateway.py')):raise ValueError('Gateway contract source changed')
    if mcp['diascreen_source_manifest_sha256']!=sha(checked(repo/'components/dop_100/src/universal_diascreen_hmi/extended/RELEASE_MANIFEST.json')):raise ValueError('DIAScreen source release changed')
    snapshot=mcp['schema_snapshot'];snapshot_path=Path(snapshot['path'])
    if snapshot_path.as_posix()!='reports/hmi_skill/MCP_API_SCHEMAS.json':raise ValueError('Schema snapshot is not the approved neutral capture')
    raw=checked(repo/snapshot_path)
    if sha(raw)!=snapshot['sha256']:raise ValueError('Captured input schema drift')
    api=json.loads(raw)
    if api['source_commit']!=mcp['accepted_source_commit']:raise ValueError('Schema capture belongs to another accepted source')
    for family in ('dop_b','dop_100'):
        component=record['mcp']['components'][family];captured=api['families'][family];tools=captured['tools'];names=[t['name'] for t in tools]
        installed=tomllib.loads(checked(repo/'components'/family/'pyproject.toml').decode())['project']['version']
        if component['version']!=installed or captured['version']!=installed:raise ValueError('Family component version mismatch')
        if len(names)!=len(set(names)) or len(names)!=component['schema_tools'] or component['input_schema_sha256']!=sha(canonical(tools)):raise ValueError('Family input schema mismatch')
    expected={'dop_b_prefix':'dop_b__','dop_100_prefix':'dop_100__','dop_100_new_sessions':['open_project','open_delivery','create_project'],'dop_100_stateless':['capabilities','intake_source_profile','list_deliveries','current_delivery','inspect_parameters','get_reference_contract','inspect_template'],'dop_100_open_project_fields':['profile_id','path','source_sha256'],'dop_100_other_project_calls_require':'session_id','persistent_jobs':'DOP_B_ONLY_SEPARATE_HOST_POLICY'}
    if record['gateway_contract']!=expected:raise ValueError('Family/session authority projection mismatch')
    controls=record['control_documents']
    if [c['path'] for c in controls]!=['AGENTS.md','SYSTEM_PROMPT.md','INDEX.md']:raise ValueError('Control sources missing or reordered')
    for control in controls:
        if control['sha256']!=sha(checked(repo/control['path'])) or control['url']!=mcp['repository']+'/blob/'+mcp['accepted_source_commit']+'/'+control['path']:raise ValueError('Control source drift')
    return dict(status='PASS',skill='delta-hmi',version='0.1.0',mcp=version,source=mcp['accepted_source_commit'],files=len(members),behavioral_acceptance='SEPARATE_G4')


if __name__=='__main__':print(json.dumps(validate()))
