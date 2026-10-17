"""Verify clean component snapshots without trusting private checkout locations."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
GENERATED={'.git','.agent-state','.local','.venv','build','dist','__pycache__'}
def ignored(path):
    return any(part in GENERATED or part.endswith('.egg-info') for part in path.parts) or path.suffix=='.pyc'
def check():
    manifest=json.loads((ROOT/'templates/component_files.json').read_text('utf8'))
    for family,data in manifest['components'].items():
        base=ROOT/'components'/family
        expected={row['path']:row['sha256'] for row in data['files']}
        actual={}
        for path in base.rglob('*'):
            if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):raise ValueError('Linked component file')
            relative=path.relative_to(base)
            if not ignored(relative) and path.is_file():actual[relative.as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
        if actual!=expected:raise ValueError('Component snapshot drift: '+family)
    return {'status':'PASS','components':{key:len(value['files']) for key,value in manifest['components'].items()}}
if __name__=='__main__':print(json.dumps(check()))
