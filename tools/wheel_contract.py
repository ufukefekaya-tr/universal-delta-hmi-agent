"""Build from positive staging and audit every wheel member against source."""
import argparse
import base64
import configparser
import csv
from email.parser import BytesParser
from email.utils import formataddr
from collections import Counter
import fnmatch
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import zipfile

ROOT=Path(__file__).resolve().parents[1]
_spec=importlib.util.spec_from_file_location('wheel_source_contract',ROOT/'tools/package_contract.py')
contract=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(contract)
FAMILIES={ 'gateway':('', 'delta_hmi'), 'dop_b':('components/dop_b/','universal_hmi'), 'dop_100':('components/dop_100/','universal_diascreen_hmi') }

def metadata_contract(info,project,source,prefix,license_files):
    p=project['project']
    expected={'Metadata-Version':['2.4'],'Name':[p['name']],'Version':[p['version']],'Summary':[p['description']],'License-Expression':[p['license']],'Requires-Python':[p['requires-python']],'License-File':sorted(license_files),'Dynamic':['license-file']}
    if p.get('urls'):expected['Project-URL']=[k+', '+v for k,v in p['urls'].items()]
    if p.get('classifiers'):expected['Classifier']=p['classifiers']
    if p.get('authors'):
        names=[a['name'] for a in p['authors'] if 'email' not in a];emails=[formataddr((a.get('name',''),a['email'])) for a in p['authors'] if 'email' in a]
        if names:expected['Author']=[', '.join(names)]
        if emails:expected['Author-email']=[', '.join(emails)]
    deps=list(p.get('dependencies',[]));extras=p.get('optional-dependencies',{})
    if extras:expected['Provides-Extra']=list(extras)
    for extra,requirements in extras.items():
        for requirement in requirements:
            if ';' in requirement:raise ValueError('Conditional extra metadata needs separate qualification')
            deps.append(requirement+'; extra == "'+extra+'"')
    if deps:expected['Requires-Dist']=deps
    readme=p.get('readme');body=b''
    if readme:
        if not isinstance(readme,str) or not readme.endswith('.md'):raise ValueError('Unqualified readme format')
        body=source[prefix+readme];expected['Description-Content-Type']=['text/markdown']
    actual=Counter((k.casefold(),str(v)) for k,v in info.items())
    wanted=Counter((k.casefold(),v) for k,values in expected.items() for v in values)
    if info.defects or actual!=wanted:raise ValueError('Wheel semantic metadata differs from declared project')
    if (info.get_payload(decode=True) or b'').replace(b'\r\n',b'\n')!=body.replace(b'\r\n',b'\n'):raise ValueError('Wheel metadata body differs from declared readme')

def audit(path,family):
    prefix,package=FAMILIES[family];source=contract.source_entries();files=contract.read_archive(path)
    project=tomllib.loads(source[prefix+'pyproject.toml'].decode('utf8'))
    roots={p.split('/')[0] for p in files if '.dist-info/' in p}
    if len(roots)!=1:raise ValueError('One wheel metadata owner required')
    meta=next(iter(roots));info=BytesParser().parsebytes(files[meta+'/METADATA'])
    if info['Name']!=project['project']['name'] or info['Version']!=project['project']['version'] or info['License-Expression']!='Apache-2.0':raise ValueError('Wheel identity/license mismatch')
    stem=project['project']['name'].replace('-','_')+'-'+project['project']['version']
    if meta!=stem+'.dist-info':raise ValueError('Wheel metadata path mismatch')
    package_data=project.get('tool',{}).get('setuptools',{}).get('package-data',{})
    expected={}
    for p,raw in source.items():
        if not p.startswith(prefix+'src/'+package+'/'):continue
        member=p[len(prefix+'src/'):]
        selected=member.endswith('.py')
        for owner,patterns in package_data.items():
            folder=owner.replace('.','/')+'/'
            if member.startswith(folder) and any(fnmatch.fnmatchcase(member[len(folder):],pattern) for pattern in patterns):selected=True
        if selected:expected[member]=raw
    license_files=set()
    for pattern in project['project'].get('license-files',[]):
        for p,raw in source.items():
            if p.startswith(prefix) and fnmatch.fnmatchcase(p[len(prefix):],pattern):
                expected[meta+'/licenses/'+p[len(prefix):]]=raw;license_files.add(p[len(prefix):])
    metadata_contract(info,project,source,prefix,license_files)
    for destination,patterns in project.get('tool',{}).get('setuptools',{}).get('data-files',{}).items():
        for pattern in patterns:
            for p,raw in source.items():
                if p.startswith(prefix) and fnmatch.fnmatchcase(p[len(prefix):],pattern):expected[stem+'.data/data/'+destination+'/'+Path(p).name]=raw
    generated={meta+'/'+p for p in ('METADATA','WHEEL','entry_points.txt','top_level.txt','RECORD')}
    if set(files)!=set(expected)|generated:raise ValueError('Wheel membership differs from reviewed package/data/licenses: '+str(sorted(set(files)^(set(expected)|generated))))
    if any(files[p]!=raw for p,raw in expected.items()):raise ValueError('Wheel authored member bytes differ')
    wheel=BytesParser().parsebytes(files[meta+'/WHEEL'])
    headers=Counter((k.casefold(),str(v)) for k,v in wheel.items())
    if wheel.defects or wheel.get_payload(decode=True) or headers!=Counter({('wheel-version','1.0'):1,('generator','setuptools (84.0.0)'):1,('root-is-purelib','true'):1,('tag','py3-none-any'):1}):raise ValueError('Unexpected wheel build/platform metadata')
    if files[meta+'/top_level.txt'].replace(b'\r\n',b'\n')!=package.encode()+b'\n':raise ValueError('Wrong import owner metadata')
    canonical='[console_scripts]\n'+''.join(k+' = '+v+'\n' for k,v in sorted(project['project'].get('scripts',{}).items()))
    if files[meta+'/entry_points.txt'].replace(b'\r\n',b'\n')!=canonical.encode():raise ValueError('Unreviewed entrypoint metadata bytes')
    cfg=configparser.ConfigParser();cfg.read_string(files[meta+'/entry_points.txt'].decode('utf8'))
    if cfg.sections()!=['console_scripts'] or dict(cfg['console_scripts'])!=project['project'].get('scripts',{}):raise ValueError('Unexpected executable entrypoint')
    records=list(csv.reader(io.StringIO(files[meta+'/RECORD'].decode('utf8'))))
    if len(records)!=len(files) or {r[0] for r in records}!=set(files):raise ValueError('Wheel RECORD coverage mismatch')
    for name,pin,size in records:
        if name==meta+'/RECORD':
            if pin or size:raise ValueError('Self RECORD must be unhashed')
        else:
            actual=base64.urlsafe_b64encode(bytes.fromhex(contract.digest(files[name]))).decode().rstrip('=')
            if pin!='sha256='+actual or size!=str(len(files[name])):raise ValueError('Wheel RECORD byte mismatch')
    return dict(status='PASS',family=family,version=info['Version'],sha256=contract.digest(Path(path).read_bytes()),members=len(files),authored_members=len(expected),license='Apache-2.0')

def build(output,dop_b_archive):
    output=contract.no_links(Path(output).absolute())
    if not output.is_relative_to(contract.no_links(ROOT/'dist').absolute()):raise ValueError('Wheel output must be inside repository dist')
    source=contract.source_entries();lock=contract.document(source['templates/releases.lock.json'])['dop_b']
    archive=contract.no_links(dop_b_archive).read_bytes()
    if contract.digest(archive)!=lock['sha256']:raise ValueError('Pinned DOP-B archive mismatch')
    output.mkdir(parents=True,exist_ok=False)
    results={}
    # Rebuild the standalone B wheel from the unchanged canonical source export.
    # The historical pinned runtime bundle retains its original wheel/CRLF bytes.
    for family in ('dop_b','gateway','dop_100'):
        with tempfile.TemporaryDirectory(prefix='delta-wheel-build-') as tmp:
            staged=contract.stage_source(Path(tmp)/'source',None if family=='gateway' else family)
            subprocess.run([sys.executable,'-I','-B','-m','pip','wheel','--no-deps','--no-index','--no-build-isolation','--wheel-dir',str(output),str(staged)],check=True)
        prefix,_=FAMILIES[family];project=tomllib.loads(source[prefix+'pyproject.toml'].decode())['project'];p=output/(project['name'].replace('-','_')+'-'+project['version']+'-py3-none-any.whl')
        results[family]=dict(path=str(p),**audit(p,family))
    return results

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--dop-b-archive',type=Path);p.add_argument('--audit',type=Path);p.add_argument('--family',choices=FAMILIES);a=p.parse_args()
    if a.audit:
        if not a.family:p.error('--family required')
        print(json.dumps(audit(a.audit,a.family),indent=2))
    else:
        if not a.output or not a.dop_b_archive:p.error('--output and --dop-b-archive required')
        print(json.dumps(build(a.output,a.dop_b_archive),indent=2))
