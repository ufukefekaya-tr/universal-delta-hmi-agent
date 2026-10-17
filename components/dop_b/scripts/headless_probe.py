"""Real stdio preflight/submit/status/result probe; never manufactures review PASS."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def probe(args):
    policy=json.loads(Path(args.policy).read_bytes())
    params=StdioServerParameters(command=sys.executable,args=['-m','universal_hmi.cli','--profiles',policy['profiles_root'],
        'serve','--workspace',policy['workspace'],'--job-policy',str(Path(args.policy).resolve()),
        '--job-state',str(Path(args.state).resolve())])
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            names=sorted(t.name for t in (await client.list_tools()).tools)
            assert len(names)==14,names
            async def call(name,**data):
                result=await client.call_tool(name,data)
                if result.is_error:raise RuntimeError(str(result))
                return result.structured_content
            job=json.loads(Path(args.job).read_bytes())
            preflight=await call('preflight_job',job=job)
            submitted=await call('submit_job',idempotency_key=args.key,job=job)
            job_id=submitted['job_id'];deadline=time.monotonic()+args.wait
            status=await call('job_status',job_id=job_id)
            while time.monotonic()<deadline and status['status'] not in ('COMPLETED','FAILED','CANCELLED'):
                await asyncio.sleep(.5)
                status=await call('job_status',job_id=job_id)
            result=await call('job_result',job_id=job_id) if status['status']=='COMPLETED' else None
            return dict(transport='REAL_STDIO',tools=names,preflight=preflight,status=status,result=result,
                        vendor='NOT_RUN',physical='NOT_RUN')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('policy','state','job','key','output'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--wait',type=float,default=5)
    args=parser.parse_args()
    result=asyncio.run(probe(args))
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status']['status'],'job_id':result['status']['job_id'],'output':args.output}))
    return 2 if result['status']['status'] in ('FAILED','CANCELLED') else 0

if __name__=='__main__':raise SystemExit(main())
