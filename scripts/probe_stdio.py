"""Exercise all nine file tools through the real gateway and backend pipes.

The deliberately invented native fixture is NOT a vendor/panel qualification.
Run with the installed gateway interpreter, --config <host configuration>.
"""
import argparse
import asyncio
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import uuid
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from delta_hmi.config import GatewayConfig

def wide(key, text):
    blob=text.encode('utf-16-le')+b'\0\0'
    return key.encode()+b'='+str(len(blob)).encode()+b'\r\n'+blob+b'\r\n'

def fixture():
    header=bytearray(54);header[:2]=b'BM'
    struct.pack_into('<I',header,10,54);struct.pack_into('<I',header,14,40);struct.pack_into('<I',header,34,4)
    body=(b'[Application]\r\nModelName=SYNTHETIC\r\nVersion=0.0\r\nUnknown=preserve\r\n'
          b'[Screen]\r\nVER=16\r\nID=1\r\n'+wide('wTextLen','Main')+
          b'DocSizeX=800\r\nDocSizeY=480\r\nPanelSizeX=800\r\nPanelSizeY=480\r\n'
          b'[AuxKeyElement]\r\n[Element]\r\nnPartsID=1\r\nType=1\r\nSubType=1\r\n'
          b'X=10\r\nY=20\r\nWidth=30\r\nHeight=20\r\nReadVar=!D1\r\nReadLink=1\r\nReadMemType=0\r\n'
          b'WriteVar=!M1\r\nWriteLink=1\r\nWriteMemType=0\r\nBeforeExecMacroLen=0\r\n'
          b'[State]\r\nValue=0\r\nFontColor=0\r\nBgColor=1122867\r\n'+wide('wTextLen0','OFF')+
          b'[State]\r\nValue=1\r\nFontColor=1\r\nBgColor=39253\r\n'+wide('wTextLen0','ON')+
          b'[SubMacro]\r\nOpaque sentinel\0\xff\r\n')
    return bytes(header)+b'PIXL'+gzip.compress(bytes(b^0x64 for b in bytes(range(41))+body),mtime=0),body

async def probe(config_path):
    cfg=GatewayConfig.load(config_path);workspace=cfg.backends['dop_b'].workspace
    folder=workspace/('gateway-probe-'+uuid.uuid4().hex);folder.mkdir()
    source,body=fixture();(folder/'source.dps').write_bytes(source)
    rel=folder.relative_to(workspace).as_posix()
    design={'schema_version':1,'project_id':'neutral_probe','profile_id':'synthetic_dopsoft2',
        'screens':[{'id':'main','native_id':'1','name':'Main','width':800,'height':480,'elements':[
            {'id':'switch','native_id':'1','kind':'button','x':10,'y':20,'width':30,'height':20,
             'behavior':'maintained','role':'request','binding':{'read':'state','write':'command'},
             'states':[{'value':0,'text':'OFF','fill':'#112233'},{'value':1,'text':'ON','fill':'#009955'}]}]}],
        'tags':[dict(id=tag,address=address,data_type='BOOL',access=access,channel='SIM',station='0',
            byte_order='little',word_order='little',native_binding={'link':'1','mem_type':'0'})
            for tag,address,access in [('state','!D1','Read'),('command','!M1','ReadWrite')]],'macros':[],'alarms':[]}
    params=StdioServerParameters(command=sys.executable,args=['-I','-B','-m','delta_hmi.cli','serve','--config',str(config_path)])
    calls=[]
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            listed={t.name for t in (await client.list_tools()).tools}
            assert len(listed)==10,listed
            async def call(name,**args):
                response=await client.call_tool('dop_b__'+name,args)
                assert not response.is_error,str(response)
                calls.append(name)
                return response.structured_content
            caps=await call('capabilities',profile_id='synthetic_dopsoft2')
            sid=(await call('open_project',profile_id='synthetic_dopsoft2',source_path=rel+'/source.dps'))['session_id']
            assert sid.startswith('dop_b:'),sid
            await call('inspect',session_id=sid)
            plan=await call('plan_changes',session_id=sid,design=design,idempotency_key='probe',operations=[
                dict(op='set_property',screen_id='1',element_id='1',key='behavior',value='maintained')])
            pid=plan['plan_id'];await call('preview',session_id=sid,plan_id=pid)
            validation=await call('validate',session_id=sid,plan_id=pid)
            assert validation['offline_pass'],validation
            approval={k:v for k,v in plan.items() if k.endswith('_sha256')}
            approval.update(approved=True,authority='neutral_fixture_qualification',purpose='qualification_only')
            (folder/'approval.json').write_text(json.dumps(approval),encoding='utf8')
            await call('apply_plan',session_id=sid,plan_id=pid,approval_path=rel+'/approval.json')
            saved=await call('save_as',session_id=sid,output_path=rel+'/candidate.dps')
            difference=await call('diff',session_id=sid)
            candidate=(folder/'candidate.dps').read_bytes()
            assert hashlib.sha256(candidate).hexdigest()==saved['sha256']==difference['candidate_sha256']
            decoded=bytes(b^0x64 for b in gzip.decompress(candidate[58:]))[41:]
            assert decoded==body.replace(b'SubType=1\r\n',b'SubType=2\r\n',1)
            assert (folder/'source.dps').read_bytes()==source
            denied=await client.call_tool('dop_100__inspect',{'session_id':sid})
            assert denied.is_error
            wrong=await client.call_tool('dop_b__capabilities',{'profile_id':'synthetic_diascreen'})
            assert wrong.is_error
    return {'status':'PASS','scope':'Real gateway/backend stdio; ORIGINAL SYNTHETIC transaction only',
            'file_tools':sorted(set(calls)),'tool_count':len(listed),'source_preserved':True,
            'candidate_sha256':hashlib.sha256(candidate).hexdigest(),'independent_payload_comparison':'PASS',
            'dop_100':'DISABLED_PENDING_SEPARATE_BACKEND','vendor':'NOT_RUN','physical':'NOT_RUN'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True,type=Path)
    args=parser.parse_args();print(json.dumps(asyncio.run(probe(args.config.resolve())),indent=2))
