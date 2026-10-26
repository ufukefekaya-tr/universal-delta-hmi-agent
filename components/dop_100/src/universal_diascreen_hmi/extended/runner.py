# SPDX-License-Identifier: Apache-2.0
import argparse,json,sys
from pathlib import Path
from .hmi4_bootstrap import *
from .hmi4_service import Service
from .transport import cli,install,AgentError
class Output:
    def write(self,b):
        r=json.loads(b)
        if 'serverInfo' in r.get('result',{}):r['result']['serverInfo']=dict(name='universal-diascreen-hmi',version=VERSION)
        sys.stdout.buffer.write((json.dumps(r,ensure_ascii=False)+'\n').encode('utf8'))
    def flush(self):sys.stdout.buffer.flush()
def main(argv=None):
    sys.stdout.reconfigure(encoding='utf8');sys.stderr.reconfigure(encoding='utf8',errors='backslashreplace')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,default=Path.cwd()/'.hmi-workspace');p.add_argument('--read-root',action='append',default=[]);p.add_argument('--allow-write',action='store_true');p.add_argument('--check',action='store_true');p.add_argument('--batch',action='store_true');p.add_argument('--call');a=p.parse_args(argv)
    verified=verify_release()
    if a.check:print(json.dumps(dict(**verified,vendor_qualified=False)));return 0
    no_links(a.workspace);a.workspace.mkdir(parents=True,exist_ok=True);session=Service(a.workspace,allow_write=a.allow_write,read_roots=a.read_root);install()
    if a.call:
        args=json.loads(sys.stdin.buffer.read(cli.MAX_MESSAGE+1));print(json.dumps(cli.call_tool(session,a.call,args),ensure_ascii=False));return 0
    if a.batch:
        for n,line in enumerate(sys.stdin.buffer):
            require(n<1024 and len(line)<=cli.MAX_MESSAGE,'MESSAGE_LIMIT','Bounded CLI input required');r=json.loads(line);require(set(r)=={'name','arguments'},'PARAMETERS','Exact CLI request required')
            try:result=cli.call_tool(session,r['name'],r['arguments']);print(json.dumps(result,ensure_ascii=False),flush=True)
            except AgentError as error:print(json.dumps(dict(error=error.as_dict()),ensure_ascii=False),flush=True);return 2
        return 0
    return cli.serve(session,outgoing=Output())
if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,AgentError) as error:print('HMI startup/call refused: '+str(error),file=sys.stderr);raise SystemExit(2)
