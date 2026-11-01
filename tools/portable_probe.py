"""Install a relocated exact source archive; probe both real stdio backends.

The host Python packages source only. Installation and all MCP calls use the
forced, pinned bundled interpreters. No vendor program or device is accessed.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
_spec=importlib.util.spec_from_file_location('portable_source_contract',ROOT/'tools/package_contract.py')
contract=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(contract)

def run(args,cwd,log):
    result=subprocess.run([str(a) for a in args],cwd=cwd,capture_output=True,text=True,encoding='utf8',errors='strict',env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    log.write_text(result.stdout+'\nSTDERR\n'+result.stderr,encoding='utf8',newline='\n')
    if result.returncode:
        print(result.stdout[-5000:]);print(result.stderr[-5000:],file=sys.stderr)
        raise RuntimeError('Portable stage failed; see isolated stage log')
    return result.stdout

def qualify(destination,backend_archive=None):
    destination=contract.no_links(Path(destination).absolute())
    if destination.exists():raise FileExistsError('Fresh destination required')
    archive=ROOT/'dist'/('portable-source-'+os.name+'-'+uuid.uuid4().hex+'.zip')
    built=contract.build(archive);contract.audit(archive)
    entries=contract.read_archive(archive);destination.mkdir(parents=False,exist_ok=False)
    for name,raw in entries.items():
        path=destination/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(raw)
    evidence=destination/'.agent-state/portable-probe';evidence.mkdir(parents=True)
    if os.name=='nt':
        cmd=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',destination/'scripts/bootstrap.ps1']
        if backend_archive:cmd+=['-Offline','-BackendArchive',Path(backend_archive).resolve()]
        python=destination/'.venv/Scripts/python.exe'
    else:
        cmd=['sh',destination/'scripts/bootstrap.sh']
        if backend_archive:cmd.append(Path(backend_archive).resolve())
        python=destination/'.venv/bin/python'
    run(cmd,destination,evidence/'bootstrap.log')
    config=destination/'.local/gateway.json'
    doctor=json.loads(run([python,'-I','-B','-m','delta_hmi.cli','doctor','--config',config],destination,evidence/'doctor.log'))
    if set(doctor)!={'dop_b','dop_100'} or any(r['status']!='CONFIG_VERIFIED' for r in doctor.values()):raise ValueError('Both installed backends must verify')
    probe=json.loads(run([python,'-I','-B',destination/'scripts/probe_both.py','--config',config,'--jobs'],destination,evidence/'stdio.log'))
    if probe['status']!='PASS' or probe['source_preserved'] is not True:raise ValueError('Actual file probe failed')
    for name,raw in entries.items():
        if (destination/name).read_bytes()!=raw:raise ValueError('Installer/probe changed public source: '+name)
    report=dict(status='PASS',platform=sys.platform,source_archive_sha256=built['sha256'],source_members=built['files'],fresh_relocated_install=True,forced_bundled_runtimes=True,doctor=doctor,stdio=probe,source_bytes_unchanged=True,vendor='NOT_RUN',physical='NOT_RUN')
    (evidence/'REPORT.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8',newline='\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--destination',required=True,type=Path);p.add_argument('--backend-archive',type=Path);a=p.parse_args()
    print('PORTABLE_REPORT_JSON='+json.dumps(qualify(a.destination,a.backend_archive),separators=(',',':')))
