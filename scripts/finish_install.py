"""Complete a hash-verified, already-extracted DOP-B release installation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    base = ROOT / '.local'
    backend = base / 'backends/dop_b'
    config_file = base / 'gateway.json'
    if config_file.exists():
        raise ValueError('Existing configuration is preserved; use a new installation directory')
    python = backend / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    # Create an independent gateway environment with the pinned backend runtime.
    subprocess.run([str(python), '-m', 'venv', '--copies', str(ROOT/'.venv')], check=True)
    gateway_python = ROOT / ('.venv/Scripts/python.exe' if os.name=='nt' else '.venv/bin/python')
    lock = json.loads((backend/'scripts/bootstrap.lock.json').read_text('utf8'))
    requirements = base/'pins/gateway-requirements.lock'
    requirements.parent.mkdir(parents=True,exist_ok=True)
    requirements.write_text('\n'.join(d['requirement']+' '+ ' '.join(
        '--hash=sha256:'+w['sha256'] for w in d['wheels']) for d in lock['dependencies'])+'\n',encoding='utf8')
    subprocess.run([str(gateway_python), '-m', 'pip', 'install', '--no-index', '--require-hashes',
                    '--find-links', str(backend/'wheelhouse'), '-r', str(requirements)], check=True)
    subprocess.run([str(gateway_python), '-m', 'pip', 'install', '--no-deps', '--no-build-isolation',
                    '--no-index', str(ROOT)], check=True)
    sys.path.insert(0, str(ROOT/'src'))
    from delta_hmi.config import tree_files, tree_sha256, GatewayConfig
    package = Path(subprocess.check_output([str(python), '-I','-c',
        'import universal_hmi,pathlib; print(pathlib.Path(universal_hmi.__file__).parent)'],text=True).strip())
    if not package.resolve().is_relative_to(backend.resolve()):
        raise ValueError('Backend package escaped its installation')
    roots = {key:base/('families/dop_b/'+key) for key in ('workspace','profiles','state')}
    for path in roots.values():
        path.mkdir(parents=True,exist_ok=False)
    profile_source = package/'data/profiles'
    # Nested authority contracts are preserved, but only same-family top-level profiles are published.
    for item in profile_source.iterdir():
        if item.is_dir():
            shutil.copytree(item, roots['profiles']/item.name)
        elif item.suffix=='.json':
            data = json.loads(item.read_text('utf8'))
            if data.get('family')=='delta_dopsoft2':
                shutil.copy2(item, roots['profiles']/item.name)
    # POSIX venv launchers are often links; use a real local executable so the
    # gateway's no-link authority check remains identical on both platforms.
    if python.is_symlink():
        binary = python.read_bytes()
        python.unlink()
        python.write_bytes(binary)
        python.chmod(0o755)
    manifest = base/'pins/dop_b.json'; manifest.parent.mkdir(parents=True,exist_ok=True)
    prefix = package.relative_to(backend).as_posix()
    imports=['.venv','.runtime/python']
    manifest.write_text(json.dumps({'package_prefix':prefix,'import_roots':imports,'files':[
        {'path':directory+'/'+name,'sha256':sha}
        for directory in imports for name,sha in tree_files(backend/directory).items()
    ]},indent=2)+'\n',encoding='utf8')
    rel = lambda p:p.relative_to(base).as_posix()
    value = {'schema_version':1,'backends':{
        'dop_b':{'enabled':True,'root':rel(backend),'python':rel(python),
            'python_sha256':digest(python),'source_manifest':rel(manifest),
            'source_manifest_sha256':digest(manifest),'profiles_sha256':tree_sha256(roots['profiles']),
            **{key:rel(path) for key,path in roots.items()}},
        'dop_100':{'enabled':False,'reason':'Independent DIAScreen extraction and integration qualification pending; no DOP-B fallback.'}
    }}
    config_file.write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')
    config = GatewayConfig.load(config_file)
    config.backends['dop_b'].verify()
    print(json.dumps({'status':'DOP_B_GATEWAY_INSTALLED','dop_100':'PENDING_SEPARATE_BACKEND',
                     'configuration':str(config_file),'python':str(gateway_python)}))

if __name__=='__main__':
    main()
