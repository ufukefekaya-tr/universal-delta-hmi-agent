"""Retain exact upstream wheel/runtime notices; does not execute downloaded code."""
from pathlib import Path
import argparse, email, hashlib, io, json, tarfile, zipfile

ROOT = Path(__file__).resolve().parents[1]
def digest(raw): return hashlib.sha256(raw).hexdigest()
def notice(name):
    leaf = Path(name).name.lower()
    return leaf.startswith(('license', 'copying', 'copyright', 'notice', 'authors')) and not leaf.endswith(('.py','.pyc'))
def retain(base, name, raw):
    path = ROOT/'licenses/texts'/(digest(raw)+'.txt')
    path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(raw)
    return {'path':path.relative_to(ROOT).as_posix(),'source_member':name,'sha256':digest(raw),'bytes':len(raw)}

def audit(archive, runtime_full):
    lock=json.loads((ROOT/'scripts/bootstrap.lock.json').read_bytes());out=ROOT/'licenses';out.mkdir(exist_ok=True)
    allowed={w['filename']:w for d in lock['dependencies'] for w in d['wheels']}
    result={'schema_version':1,'original_license':'Apache-2.0','wheels':[],'runtimes':[]}
    with zipfile.ZipFile(archive) as bundle:
        for n in sorted(bundle.namelist()):
            if not n.startswith('wheelhouse/'):continue
            raw=bundle.read(n);name=Path(n).name;spec=allowed[name]
            if digest(raw)!=spec['sha256']:raise ValueError('Wheel hash mismatch')
            with zipfile.ZipFile(io.BytesIO(raw)) as w:
                meta=email.message_from_bytes(w.read(next(p for p in w.namelist() if p.endswith('.dist-info/METADATA'))))
                entries=[retain(out/'wheels'/name,p,w.read(p)) for p in w.namelist() if not p.endswith('/') and notice(p)]
                if not entries:raise ValueError('Missing wheel license')
                result['wheels'].append({'artifact':name,'sha256':spec['sha256'],'source':spec['url'],'license':meta.get('License-Expression') or meta.get('License'),'notices':entries})
        for key,spec in lock['runtimes'].items():
            raw=bundle.read('runtime-bundle/'+spec['filename'])
            if digest(raw)!=spec['sha256']:raise ValueError('Runtime hash mismatch')
            with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as t:
                entries=[retain(out/'runtimes'/key/'install',m.name,t.extractfile(m).read()) for m in t if m.isfile() and notice(m.name)]
            result['runtimes'].append({'profile':key,'artifact':spec['filename'],'sha256':spec['sha256'],'source':spec['url'],'notices':entries})
    sources=json.loads((runtime_full/'sources.json').read_bytes())
    for rec in result['runtimes']:
        token='windows' if rec['profile'].startswith('windows') else 'linux'
        source=next(s for s in sources if token in s['name']);path=runtime_full/source['name']
        if digest(path.read_bytes())!=source['sha256'] or source['github_digest']!='sha256:'+source['sha256']:raise ValueError('Full build upstream digest mismatch')
        with tarfile.open(path,'r:zst') as t:
            metadata=json.load(t.extractfile('python/PYTHON.json'))
            rec['full_build_notice_source']=source
            rec['python_licenses']=metadata['licenses']
            rec['linked_library_licenses']=[]
            def walk(v):
                if isinstance(v,dict):
                    if 'licenses' in v: rec['linked_library_licenses'].append({k:v[k] for k in ('name','licenses','license_paths','license_path','system') if k in v})
                    for x in v.values():walk(x)
                elif isinstance(v,list):
                    for x in v:walk(x)
            walk(metadata['build_info'])
            for m in t:
                if m.isfile() and m.name.startswith('python/licenses/'):
                    rec['notices'].append(retain(out/'runtimes'/rec['profile']/'upstream',m.name,t.extractfile(m).read()))
    for rec in result['runtimes']:
        for extra in json.loads((out/'runtime-supplemental-sources.json').read_bytes()):
            p=ROOT/extra['retained_path']
            raw=p.read_bytes()
            if digest(raw)!=extra['notice_sha256']: raise ValueError('Supplemental license drift')
            rec['notices'].append({'path':p.relative_to(ROOT).as_posix(),'sha256':digest(raw),'bytes':len(raw),'source_member':'python/licenses/'+extra['notice_file']})
        for component in rec['linked_library_licenses']:
            for name in component.get('license_paths',[]):
                if 'python/'+name not in {n['source_member'] for n in rec['notices']}:
                    raise ValueError('Runtime linked-library license missing: '+name)
    names={x['artifact'] for x in result['wheels']}
    if not names or any(not names.intersection(w['filename'] for w in d['wheels']) for d in lock['dependencies']):raise ValueError('Missing bundled dependency')
    (out/'inventory.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'wheels':len(names),'runtimes':len(result['runtimes']),'notice_files':sum(len(x['notices']) for group in ('wheels','runtimes') for x in result[group])}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True,type=Path);p.add_argument('--runtime-full',required=True,type=Path);a=p.parse_args();audit(a.archive,a.runtime_full)
