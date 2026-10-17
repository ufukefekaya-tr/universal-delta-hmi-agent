"""Portable source CI; native vendor tests are deliberately separate."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(*args,cwd=ROOT,env=None):
    subprocess.run([str(a) for a in args],cwd=cwd,check=True,env=env)

def test_environment():
    """Use canonical Windows temp names without changing guards/assertions."""
    env=dict(os.environ)
    if os.name=='nt':
        directory=str(Path(tempfile.gettempdir()).resolve(strict=True))
        env.update(TMPDIR=directory,TEMP=directory,TMP=directory)
        tempfile.tempdir=directory
    return env
def main():
    action=sys.argv[1]
    if action=='install':
        lock=json.loads((ROOT/'components/dop_b/scripts/bootstrap.lock.json').read_text('utf8'))
        with tempfile.TemporaryDirectory() as tmp:
            req=Path(tmp)/'requirements.txt'
            req.write_text('\n'.join(d['requirement']+' '+ ' '.join('--hash=sha256:'+w['sha256'] for w in d['wheels']) for d in lock['dependencies'])+'\n',encoding='utf8')
            run(sys.executable,'-m','pip','install','--require-hashes','-r',req)
        for part in (ROOT,ROOT/'components/dop_b',ROOT/'components/dop_100'):
            with tempfile.TemporaryDirectory(prefix='delta-source-build-') as scratch:
                staged=Path(scratch)/'source'
                shutil.copytree(part,staged,ignore=shutil.ignore_patterns('.git','.agent-state','.local','.venv','*.egg-info','build','dist','__pycache__'))
                run(sys.executable,'-I','-B','-m','pip','install','--no-deps','--no-build-isolation',staged)
    elif action=='test':
        env=test_environment()
        run(sys.executable,'-B',ROOT/'tools/check_snapshots.py',env=env)
        run(sys.executable,'-B','-m','unittest','discover','-s','tests','-v',env=env)
        for family in ('dop_b','dop_100'):
            run(sys.executable,'-B','-m','unittest','discover','-s','tests','-v',cwd=ROOT/'components'/family,env=env)
    else:raise ValueError('Use install or test')
if __name__=='__main__':main()
