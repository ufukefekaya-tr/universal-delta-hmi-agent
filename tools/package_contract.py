"""Positive membership for source/offline archives and the original MIT skill."""
import argparse
import gzip
import hashlib
import io
import json
import re
import stat
import struct
import tarfile
from pathlib import Path, PurePosixPath, PureWindowsPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GENERATED = {'.git','.agent-state','.local','.venv','__pycache__','build','dist'}
TOP = {'src','docs','prompts','scripts','templates','tests','tools','reports','components','.github','examples','goals','skills','projects'}
FLAT = {'LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','AGENTS.md','SYSTEM_PROMPT.md','INDEX.md','README.md','CONTRIBUTING.md','SECURITY.md','CHANGELOG.md','pyproject.toml','.gitignore','.gitattributes','MANIFEST.in','requirements.lock'}
SKILL = {'SKILL.md','references/dop-b.md','references/dop-100.md','compatibility.json','agents/openai.yaml','LICENSE'}
VERSIONS = dict(gateway='0.4.0',dop_b='0.2.1',dop_100='0.5.0',skill='0.1.0')
MAX_ARCHIVE=256*1024*1024
MAX_TAR=256*1024*1024
MAX_DIRECTORY=4*1024*1024

def digest(raw):return hashlib.sha256(raw).hexdigest()

def pairs(rows):
    result={}
    for key,value in rows:
        if key in result:raise ValueError('Duplicate JSON key')
        result[key]=value
    return result

def document(raw):return json.loads(raw,object_pairs_hook=pairs)

def name(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value or '\0' in value:raise ValueError('Unsafe member name')
    p=PurePosixPath(value)
    if p.is_absolute() or PureWindowsPath(value).drive or p.as_posix()!=value or any(x in {'','..','.'} or x.endswith((' ','.')) for x in value.split('/')):raise ValueError('Unsafe member path')
    if any(x.casefold() in GENERATED or x.casefold().endswith('.egg-info') for x in p.parts) or p.suffix.lower() in {'.pyc','.dps','.dpa','.project','.sqlite3','.db','.ttf','.otf'}:raise ValueError('Private/native/generated member forbidden')
    return value

def no_links(path):
    path=Path(path).absolute()
    for part in (path,*path.parents):
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):raise ValueError('Linked package path')
    if path.is_file() and path.stat().st_nlink!=1:raise ValueError('Hardlinked package file')
    return path

def source_entries():
    """Never walk or read inventory-external files."""
    no_links(ROOT)
    key='reports/IMPLEMENTATION_MANIFEST.json';raw=no_links(ROOT/key).read_bytes()
    rows=list(document(raw)['files'])+[dict(path=key,sha256=digest(raw))]
    names=[name(r['path']) for r in rows]
    if len(names)!=len({p.casefold() for p in names}):raise ValueError('Duplicate/case alias in root inventory')
    controls=[r for r in rows if r['path']=='templates/component_files.json']
    if len(controls)!=1:raise ValueError('Pinned component control membership required')
    control_raw=no_links(ROOT/'templates/component_files.json').read_bytes()
    if digest(control_raw)!=controls[0]['sha256']:raise ValueError('Pinned component control drift')
    components=document(control_raw)['components']
    if set(components)!={'dop_b','dop_100'}:raise ValueError('Both isolated component inventories required')
    for family,data in components.items():
        if not data['files']:raise ValueError('Empty component inventory')
        rows.extend(dict(path='components/'+family+'/'+r['path'],sha256=r['sha256']) for r in data['files'])
    entries={};folded=set()
    for row in rows:
        key=name(row['path'])
        if key.split('/')[0] not in TOP and key not in FLAT:raise ValueError('Unapproved top-level member')
        if key.casefold() in folded or re.fullmatch('[0-9a-f]{64}',row['sha256']) is None:raise ValueError('Duplicate/case alias or invalid pin')
        folded.add(key.casefold());raw=no_links(ROOT/key).read_bytes()
        if digest(raw)!=row['sha256']:raise ValueError('Reviewed member drift: '+key)
        entries[key]=raw
    if {p.removeprefix('skills/delta-hmi/') for p in entries if p.startswith('skills/delta-hmi/')}!=SKILL:raise ValueError('Six-file skill inventory required')
    return entries

def output_file(output):
    output=no_links(Path(output).absolute());boundary=no_links(ROOT/'dist').absolute()
    if not output.is_relative_to(boundary) or output==boundary:raise ValueError('Output must be inside repository dist')
    if output.exists():raise FileExistsError('Existing artifact preserved')
    output.parent.mkdir(parents=True,exist_ok=True);no_links(output.parent)
    return output

def stage_source(destination,component=None):
    """Build/install staging has the same positive membership as the release."""
    entries=source_entries();destination=no_links(destination)
    if component not in (None,'dop_b','dop_100'):raise ValueError('Explicit component required')
    prefix='components/'+component+'/' if component else ''
    selected={p[len(prefix):]:raw for p,raw in entries.items() if p.startswith(prefix)}
    if not selected:raise ValueError('Empty source staging')
    destination.mkdir(parents=False,exist_ok=False)
    for key,raw in selected.items():
        p=destination/key;p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as stream:stream.write(raw)
    return destination

def read_archive(path):
    path=Path(path);entries={};folded=set();total=0
    if path.stat().st_size>MAX_ARCHIVE:raise ValueError('Physical archive bound exceeded')
    def add(key,regular,size,reader):
        nonlocal total
        name(key)
        if not regular or key.casefold() in folded:raise ValueError('Nonregular/duplicate/case-alias member')
        total+=size
        if size<0 or size>256*1024*1024 or total>512*1024*1024 or len(entries)>=10000:raise ValueError('Archive bounds exceeded')
        folded.add(key.casefold());raw=reader()
        if len(raw)!=size:raise ValueError('Archive member length mismatch')
        entries[key]=raw
    if str(path).endswith('.tar.gz'):
        # Account for headers, PAX and longname records before the TAR parser.
        with gzip.open(path,'rb') as stream:expanded=stream.read(MAX_TAR+1)
        if len(expanded)>MAX_TAR:raise ValueError('Decompressed TAR metadata/payload bound exceeded')
        with tarfile.open(fileobj=io.BytesIO(expanded),mode='r:') as z:
            for r in z:add(r.name,r.isfile(),r.size,lambda:z.extractfile(r).read())
    else:
        # Our bounded release/wheel format has no comments, multipart or ZIP64.
        # Inspect EOCD before ZipFile expands the central directory in memory.
        with path.open('rb') as stream:
            if path.stat().st_size<22:raise ValueError('ZIP header missing')
            stream.seek(-22,2);end=stream.read(22)
        if end[:4]!=b'PK\x05\x06':raise ValueError('Bounded ZIP EOCD required')
        disk,start,count,total_count,size,offset,comment=struct.unpack('<HHHHIIH',end[4:])
        if disk or start or comment or count!=total_count or count>=65535 or count>10000 or size>MAX_DIRECTORY or offset+size+22!=path.stat().st_size:raise ValueError('ZIP directory metadata bound/format exceeded')
        with zipfile.ZipFile(path) as z:
            for r in z.infolist():add(r.filename,not r.is_dir() and stat.S_IFMT(r.external_attr>>16) in (0,stat.S_IFREG),r.file_size,lambda:z.read(r))
    return entries

def write_archive(output,entries):
    output=output_file(output)
    if str(output).endswith('.tar.gz'):
        with output.open('xb') as stream,gzip.GzipFile(fileobj=stream,mode='wb',mtime=0) as gz,tarfile.open(fileobj=gz,mode='w') as z:
            for key,raw in sorted(entries.items()):
                r=tarfile.TarInfo(key);r.size=len(raw);r.mode=0o644;r.mtime=1793491200;z.addfile(r,io.BytesIO(raw))
    elif output.suffix=='.zip':
        with output.open('xb') as stream,zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for key,raw in sorted(entries.items()):
                r=zipfile.ZipInfo(key,(2026,11,1,0,0,0));r.compress_type=zipfile.ZIP_DEFLATED;r.external_attr=0o100644<<16;z.writestr(r,raw)
    else:raise ValueError('Only ZIP/TAR.GZ supported')
    if read_archive(output)!=entries:raise ValueError('Exact archive membership/readback mismatch')
    return dict(path=str(output),sha256=digest(output.read_bytes()),files=len(entries),bytes=output.stat().st_size)

def build(output,archive=None,linux_archive=None,skill=False):
    entries=source_entries()
    if skill:
        if archive or linux_archive:raise ValueError('Skill is instructions only')
        return dict(write_archive(output,{'delta-hmi/'+p:entries['skills/delta-hmi/'+p] for p in SKILL}),status='SIX_FILE_MIT_SKILL')
    lock=document(entries['templates/releases.lock.json'])['dop_b']
    for path,key,pin,size in ((archive,'archive','sha256','bytes'),(linux_archive,'linux_archive','linux_sha256',None)):
        if path:
            raw=no_links(path).read_bytes()
            if digest(raw)!=lock[pin] or (size and len(raw)!=lock[size]):raise ValueError('Pinned backend archive mismatch')
            entries['bundles/'+lock[key]]=raw
    manifest=dict(scope='TWO_FAMILY_FILE_MCP_OFFLINE',versions=VERSIONS,files=[dict(path=p,sha256=digest(raw),bytes=len(raw)) for p,raw in sorted(entries.items())])
    entries['PACKAGE_MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    return dict(write_archive(output,entries),status=manifest['scope'])

def audit(path):
    entries=read_archive(path);approved=source_entries()
    if 'PACKAGE_MANIFEST.json' not in entries:
        if set(entries)!={'delta-hmi/'+p for p in SKILL} or any(raw!=approved['skills/'+p] for p,raw in entries.items()):raise ValueError('Wrong skill members/prefix/bytes')
    else:
        manifest=document(entries['PACKAGE_MANIFEST.json']);rows=manifest['files']
        if manifest.get('scope')!='TWO_FAMILY_FILE_MCP_OFFLINE' or manifest.get('versions')!=VERSIONS:raise ValueError('Archive scope/version mismatch')
        if len(rows)!=len({r['path'].casefold() for r in rows}) or set(entries)!={r['path'] for r in rows}|{'PACKAGE_MANIFEST.json'}:raise ValueError('Manifest membership mismatch')
        if any(digest(entries[r['path']])!=r['sha256'] or len(entries[r['path']])!=r['bytes'] for r in rows):raise ValueError('Manifest content mismatch')
        extra=set(entries)-set(approved)-{'PACKAGE_MANIFEST.json'};lock=document(approved['templates/releases.lock.json'])['dop_b']
        pins={'bundles/'+lock['archive']:lock['sha256'],'bundles/'+lock['linux_archive']:lock['linux_sha256']}
        if extra-pins.keys() or any(digest(entries[p])!=pins[p] for p in extra):raise ValueError('Unapproved bundled artifact')
        if any(entries.get(p)!=raw for p,raw in approved.items()):raise ValueError('Archive differs from approved source')
    return dict(status='PASS',sha256=digest(Path(path).read_bytes()),members=len(entries))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--audit',type=Path);p.add_argument('--source-check',action='store_true');p.add_argument('--dop-b-archive',type=Path);p.add_argument('--dop-b-linux-archive',type=Path);p.add_argument('--skill',action='store_true');a=p.parse_args()
    if sum((bool(a.output),bool(a.audit),a.source_check))!=1:p.error('Choose exactly --output, --audit or --source-check')
    if a.source_check:
        print(json.dumps(dict(status='PASS',source_members=len(source_entries()))));return
    print(json.dumps(audit(a.audit) if a.audit else build(a.output,a.dop_b_archive,a.dop_b_linux_archive,a.skill),indent=2))

if __name__=='__main__':main()
