"""Deterministic clean umbrella archive, optionally with the pinned DOP-B bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DIRS=('src','docs','prompts','scripts','templates','tests','tools','reports')
FILES=('LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','AGENTS.md','SYSTEM_PROMPT.md','INDEX.md','README.md','pyproject.toml','.gitignore','.gitattributes','projects/README.md')

def build(output, archive=None):
    output=Path(output).resolve()
    if not output.is_relative_to((ROOT/'dist').resolve()):
        raise ValueError('Package output must be inside this repository dist directory')
    if output.exists():
        raise FileExistsError('Existing package is preserved')
    entries={name:(ROOT/name).read_bytes() for name in FILES}
    for folder in DIRS:
        for path in sorted((ROOT/folder).rglob('*')):
            if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
                raise ValueError('Linked source is forbidden')
            if path.is_file() and '__pycache__' not in path.parts and path.suffix in {'.py','.md','.json','.ps1','.sh'}:
                entries[path.relative_to(ROOT).as_posix()]=path.read_bytes()
    if archive:
        raw=Path(archive).read_bytes();lock=json.loads((ROOT/'templates/releases.lock.json').read_bytes())['dop_b']
        if hashlib.sha256(raw).hexdigest()!=lock['sha256'] or len(raw)!=lock['bytes']:
            raise ValueError('Pinned DOP-B archive mismatch')
        entries['bundles/'+lock['archive']]=raw
    manifest={'scope':'UMBRELLA_PRERELEASE_DIASCREEN_PENDING','files':[
        {'path':p,'sha256':hashlib.sha256(v).hexdigest(),'bytes':len(v)} for p,v in sorted(entries.items())]}
    entries['PACKAGE_MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted(entries.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,10,17,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16;z.writestr(info,raw)
    with zipfile.ZipFile(output) as z:
        for item in manifest['files']:
            if hashlib.sha256(z.read(item['path'])).hexdigest()!=item['sha256']:
                raise ValueError('Reopened archive hash mismatch')
    return {'path':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'files':len(entries),'bytes':output.stat().st_size,'status':manifest['scope']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--dop-b-archive',type=Path)
    a=p.parse_args();print(json.dumps(build(a.output,a.dop_b_archive),indent=2))
