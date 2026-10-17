"""Real SDK client/server pipe test, not a mocked tool registry."""
import asyncio
import json
import os
import shutil
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
import test_service as service_fixtures


class StdioTests(unittest.TestCase):
    def test_source_classified_entry_permission_over_nine_tools_and_raw_dependency_drift(self):
        fixture=service_fixtures.ExistingEntryPermissionServiceTests()
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        installation=fixture.root/'isolated_install'
        shutil.copytree(ROOT/'src/universal_hmi',installation/'src/universal_hmi')
        shutil.copytree(fixture.authority_dir,installation/'src/universal_hmi/data/profiles/existing_contracts', dirs_exist_ok=True)
        shutil.copytree(ROOT/'profiles/driver_contracts',installation/'src/universal_hmi/data/profiles/driver_contracts', dirs_exist_ok=True)
        design=fixture.changed()
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-m','universal_hmi.cli','--profiles',
                str(fixture.profile_dir),'serve','--workspace',str(fixture.root)],
                env={**os.environ,'PYTHONPATH':str(installation/'src'),'PYTHONUTF8':'1'},cwd=str(fixture.root))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize();self.assertEqual(len((await client.list_tools()).tools),9)
                    async def call(name,**args):
                        result=await client.call_tool(name,args);self.assertFalse(result.is_error,str(result));return result.structured_content
                    caps=await call('capabilities',profile_id='existing_edit_permission_v1')
                    self.assertEqual(caps['capabilities']['native_entry_permission'],'OFFLINE_PASS')
                    sid=(await call('open_project',profile_id='existing_edit_permission_v1',source_path='source.dps'))['session_id']
                    before=await call('inspect',session_id=sid);self.assertEqual(len(before['inventory']['screens']),3)
                    plan=await call('plan_changes',session_id=sid,design=design,idempotency_key='permission-composite')
                    self.assertEqual(sum(o['op']=='set_existing_entry_permission' for o in plan['operations']),3)
                    self.assertFalse((await call('validate',session_id=sid,plan_id=plan['plan_id']))['findings'])
                    preview=await call('preview',session_id=sid,plan_id=plan['plan_id'])
                    self.assertIn('UNKNOWN',preview['html']);self.assertIn('NATIVE CONTROLS NOT RENDERED',preview['html'])
                    self.assertEqual(preview['native_visual_acceptance'],'NOT_RUN')
                    approval=fixture.approve(plan)
                    applied=await call('apply_plan',session_id=sid,plan_id=plan['plan_id'],approval_path=approval)
                    self.assertEqual(applied['scope'],'SOURCE_PINNED_EXISTING_ENTRY_PERMISSION_STORED_ONLY')
                    saved=await call('save_as',session_id=sid,output_path='permission-sdk.dps')
                    self.assertEqual(saved['sha256'],(await call('diff',session_id=sid))['candidate_sha256'])
                    raw=(fixture.root/'permission-sdk.dps').read_bytes()
                    self.assertEqual(service_fixtures.NativeAdapter(raw,'delta_dopsoft2').envelope.body,fixture.expected_body())
                    sid2=(await call('open_project',profile_id='existing_edit_permission_v1',source_path='source.dps'))['session_id']
                    replay=await call('plan_changes',session_id=sid2,design=design,idempotency_key='replay')
                    self.assertEqual(replay['plan_id'],plan['plan_id'])
                    await call('apply_plan',session_id=sid2,plan_id=replay['plan_id'],approval_path=approval)
                    await call('save_as',session_id=sid2,output_path='permission-replay.dps')
                    self.assertEqual(raw,(fixture.root/'permission-replay.dps').read_bytes())
                    bad=service_fixtures.deepcopy(design)
                    fixture.owner(bad,'12','61')['entry_permission']['permission_address']='{Link2}0@X8'
                    refused=await client.call_tool('plan_changes',dict(session_id=sid,design=bad,idempotency_key='invalid-radix'))
                    self.assertTrue(refused.is_error)
                    dependency=fixture.root/'actions.json';dependency.write_bytes(dependency.read_bytes()+b' ')
                    drift=await client.call_tool('save_as',dict(session_id=sid,output_path='drift.dps'))
                    self.assertTrue(drift.is_error);self.assertIn('CALIBRATION_CHANGED',str(drift))
                    self.assertFalse((fixture.root/'drift.dps').exists())
                    self.assertEqual((fixture.root/'source.dps').read_bytes(),fixture.source)
        asyncio.run(exercise())

    def test_existing_word_numeric_and_same_owner_presentation_over_all_nine_tools(self):
        fixture=service_fixtures.ExistingIntegerNumericServiceTests()
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        installation=fixture.root/'isolated_install'
        shutil.copytree(ROOT/'src/universal_hmi',installation/'src/universal_hmi')
        shutil.copytree(fixture.authority_dir,installation/'src/universal_hmi/data/profiles/existing_contracts', dirs_exist_ok=True)
        design=fixture.changed()
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-m','universal_hmi.cli','--profiles',
                str(fixture.profile_dir),'serve','--workspace',str(fixture.root)],
                env={**os.environ,'PYTHONPATH':str(installation/'src'),'PYTHONUTF8':'1'},cwd=str(fixture.root))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize();self.assertEqual(len((await client.list_tools()).tools),9)
                    async def call(name,**args):
                        result=await client.call_tool(name,args);self.assertFalse(result.is_error,str(result));return result.structured_content
                    caps=await call('capabilities',profile_id='existing_edit_numeric_v1')
                    self.assertEqual(caps['capabilities']['native_integer_numeric'],'OFFLINE_PASS')
                    sid=(await call('open_project',profile_id='existing_edit_numeric_v1',source_path='source.dps'))['session_id']
                    before=await call('inspect',session_id=sid);self.assertEqual(len(before['inventory']['screens']),3)
                    plan=await call('plan_changes',session_id=sid,design=design,idempotency_key='numeric-composite')
                    self.assertEqual(sum(o['op']=='configure_existing_integer_numeric' for o in plan['operations']),2)
                    self.assertFalse((await call('validate',session_id=sid,plan_id=plan['plan_id']))['findings'])
                    preview=await call('preview',session_id=sid,plan_id=plan['plan_id'])
                    self.assertIn('NATIVE CONTROLS NOT RENDERED',preview['html']);self.assertIn('UNKNOWN',preview['html'])
                    self.assertEqual(preview['native_visual_acceptance'],'NOT_RUN')
                    approval=fixture.approve(plan)
                    applied=await call('apply_plan',session_id=sid,plan_id=plan['plan_id'],approval_path=approval)
                    self.assertEqual(applied['scope'],'SOURCE_PINNED_EXISTING_WORD_NUMERIC_PRESENTATION_BACKGROUND')
                    saved=await call('save_as',session_id=sid,output_path='numeric-sdk.dps')
                    self.assertEqual(saved['sha256'],(await call('diff',session_id=sid))['candidate_sha256'])
                    raw=(fixture.root/'numeric-sdk.dps').read_bytes()
                    candidate=service_fixtures.NativeAdapter(raw,'delta_dopsoft2')
                    self.assertEqual(candidate.envelope.body,fixture.expected_body())
                    sid2=(await call('open_project',profile_id='existing_edit_numeric_v1',source_path='source.dps'))['session_id']
                    replay=await call('plan_changes',session_id=sid2,design=design,idempotency_key='replay')
                    self.assertEqual(replay['plan_id'],plan['plan_id'])
                    await call('apply_plan',session_id=sid2,plan_id=replay['plan_id'],approval_path=approval)
                    await call('save_as',session_id=sid2,output_path='numeric-replay.dps')
                    self.assertEqual(raw,(fixture.root/'numeric-replay.dps').read_bytes())
                    bad=service_fixtures.deepcopy(design)
                    numeric=next(e for s in bad['screens'] for e in s['elements'] if e['native_id']=='34')['integer_numeric']
                    numeric.update(integer_digits=4,fractional_digits=1,raw_minimum=0,raw_maximum=100)
                    refused=await client.call_tool('plan_changes',dict(session_id=sid,design=bad,idempotency_key='fractional-input'))
                    self.assertTrue(refused.is_error)
                    book=installation/'src/universal_hmi/data/profiles/existing_contracts/dopsoft2_b10_integer_numeric.json'
                    book.write_bytes(book.read_bytes()+b' ')
                    drift=await client.call_tool('save_as',dict(session_id=sid,output_path='drift.dps'))
                    self.assertTrue(drift.is_error);self.assertIn('CALIBRATION_CHANGED',str(drift))
                    self.assertFalse((fixture.root/'drift.dps').exists())
                    self.assertEqual((fixture.root/'source.dps').read_bytes(),fixture.source)
        asyncio.run(exercise())

    def test_existing_presentation_background_over_nine_sdk_tools_and_saved_replay(self):
        fixture=service_fixtures.ExistingEditServiceTests()
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        installation=fixture.root/'isolated_install'
        shutil.copytree(ROOT/'src/universal_hmi',installation/'src/universal_hmi')
        shutil.copytree(fixture.authority_dir,installation/'src/universal_hmi/data/profiles/existing_contracts', dirs_exist_ok=True)
        design=fixture.changed()
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-m','universal_hmi.cli','--profiles',
                str(fixture.profile_dir),'serve','--workspace',str(fixture.root)],
                env={**os.environ,'PYTHONPATH':str(installation/'src'),'PYTHONUTF8':'1'},cwd=str(fixture.root))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize();self.assertEqual(len((await client.list_tools()).tools),9)
                    async def call(name,**args):
                        result=await client.call_tool(name,args);self.assertFalse(result.is_error,str(result));return result.structured_content
                    caps=await call('capabilities',profile_id='existing_edit_v1')
                    self.assertEqual(caps['capabilities'],{k:'OFFLINE_PASS' for k in ('native_preserved','native_presentation','native_background')})
                    sid=(await call('open_project',profile_id='existing_edit_v1',source_path='source.dps'))['session_id']
                    before=(await call('inspect',session_id=sid))['inventory']
                    plan=await call('plan_changes',session_id=sid,design=design,idempotency_key='mixed-edit')
                    self.assertEqual(len(plan['operations']),3)
                    self.assertFalse((await call('validate',session_id=sid,plan_id=plan['plan_id']))['findings'])
                    preview=await call('preview',session_id=sid,plan_id=plan['plan_id'])
                    self.assertIn('BACKGROUND ONLY',preview['html']);self.assertIn('NATIVE CONTROLS NOT RENDERED',preview['html'])
                    self.assertEqual(preview['native_visual_acceptance'],'NOT_RUN')
                    approval=fixture.approve(plan)
                    applied=await call('apply_plan',session_id=sid,plan_id=plan['plan_id'],approval_path=approval)
                    self.assertEqual(applied['scope'],'SOURCE_PINNED_EXISTING_PRESENTATION_BACKGROUND')
                    saved=await call('save_as',session_id=sid,output_path='edit-sdk.dps')
                    self.assertEqual(saved['sha256'],(await call('diff',session_id=sid))['candidate_sha256'])
                    candidate=service_fixtures.NativeAdapter((fixture.root/'edit-sdk.dps').read_bytes(),'delta_dopsoft2')
                    inventory=candidate.inspect()
                    self.assertEqual(sum(len(s['elements']) for s in before['screens'])-sum(len(s['elements']) for s in inventory['screens']),1)
                    owner=next(o for o in inventory['screens'][0]['elements'] if o['id']=='21')
                    self.assertEqual(owner['geometry'],dict(x=100,y=2,width=20,height=22))
                    self.assertEqual(owner['states'][0]['native_fields']['FgColor'],'1')
                    # Fresh subprocess-session replay, all original input hashes unchanged.
                    sid2=(await call('open_project',profile_id='existing_edit_v1',source_path='source.dps'))['session_id']
                    replay=await call('plan_changes',session_id=sid2,design=design,idempotency_key='replay')
                    self.assertEqual(replay['plan_id'],plan['plan_id'])
                    await call('apply_plan',session_id=sid2,plan_id=replay['plan_id'],approval_path=approval)
                    await call('save_as',session_id=sid2,output_path='edit-replay.dps')
                    self.assertEqual((fixture.root/'edit-sdk.dps').read_bytes(),(fixture.root/'edit-replay.dps').read_bytes())
                    (fixture.root/'background.png').write_bytes(b'changed after receipt')
                    rejected=await client.call_tool('save_as',dict(session_id=sid,output_path='edit-sdk.dps'))
                    self.assertTrue(rejected.is_error);self.assertIn('EXISTING_EDIT_ASSET',str(rejected))
                    invalid=await call('validate',session_id=sid,plan_id=plan['plan_id'])
                    self.assertFalse(invalid['offline_pass']);self.assertEqual(invalid['findings'][0]['code'],'EXISTING_EDIT_ASSET')
                    self.assertEqual((fixture.root/'source.dps').read_bytes(),fixture.source)
        asyncio.run(exercise())

    def test_existing_literal_deletion_over_all_nine_sdk_tools_and_fresh_session_replay(self):
        fixture = service_fixtures.ExistingProgramServiceTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        installation = fixture.root / 'isolated_install'
        shutil.copytree(ROOT / 'src/universal_hmi', installation / 'src/universal_hmi')
        shutil.copytree(fixture.authority_dir, installation / 'src/universal_hmi/data/profiles/existing_contracts', dirs_exist_ok=True)
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=['-m','universal_hmi.cli','--profiles',
                str(fixture.profile_dir),'serve','--workspace',str(fixture.root)],
                env={**os.environ,'PYTHONPATH':str(installation/'src'),'PYTHONUTF8':'1'},cwd=str(fixture.root))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize(); self.assertEqual(len((await client.list_tools()).tools),9)
                    async def call(name,**args):
                        result=await client.call_tool(name,args); self.assertFalse(result.is_error,str(result)); return result.structured_content
                    caps=await call('capabilities',profile_id='existing_program_v1')
                    self.assertEqual(caps['capabilities'],{'native_preserved':'OFFLINE_PASS'})
                    sid=(await call('open_project',profile_id='existing_program_v1',source_path='source.dps'))['session_id']
                    before=(await call('inspect',session_id=sid))['inventory']
                    self.assertEqual(len(before['screens']),3)
                    plan=await call('plan_changes',session_id=sid,design=fixture.design,idempotency_key='delete-inert')
                    self.assertEqual(len(plan['operations']),len(fixture.deleted))
                    self.assertFalse((await call('validate',session_id=sid,plan_id=plan['plan_id']))['findings'])
                    preview=await call('preview',session_id=sid,plan_id=plan['plan_id'])
                    self.assertEqual(preview['render_kind'],'CONCEPTUAL_IR'); self.assertEqual(preview['native_visual_acceptance'],'NOT_RUN')
                    approval=fixture.approve(plan)
                    applied=await call('apply_plan',session_id=sid,plan_id=plan['plan_id'],approval_path=approval)
                    self.assertFalse(applied['program_writer_complete']);self.assertEqual(applied['scope'],'SOURCE_PINNED_INERT_LITERAL_DELETION')
                    saved=await call('save_as',session_id=sid,output_path='inert-sdk.dps')
                    self.assertEqual(saved['sha256'],(await call('diff',session_id=sid))['candidate_sha256'])
                    native=service_fixtures.NativeAdapter((fixture.root/'inert-sdk.dps').read_bytes(),'delta_dopsoft2')
                    actual=native.inspect(); self.assertEqual(len(actual['screens']),3)
                    self.assertEqual(sum(len(s['elements']) for s in before['screens'])-sum(len(s['elements']) for s in actual['screens']),len(fixture.deleted))
                    # Independent root-unit subtraction and restoration proof.
                    source=service_fixtures.NativeAdapter(fixture.source,'delta_dopsoft2')
                    for screen in actual['screens']:
                        for owner in screen['elements']:
                            self.assertEqual(native.owner_extent_sha256(screen['id'],owner['id']),source.owner_extent_sha256(screen['id'],owner['id']))
                    self.assertEqual(native.document.tail,source.document.tail)
                    sid2=(await call('open_project',profile_id='existing_program_v1',source_path='source.dps'))['session_id']
                    replay=await call('plan_changes',session_id=sid2,design=fixture.design,idempotency_key='replay')
                    self.assertEqual(replay['plan_id'],plan['plan_id'])
                    await call('apply_plan',session_id=sid2,plan_id=replay['plan_id'],approval_path=approval)
                    await call('save_as',session_id=sid2,output_path='replay.dps')
                    self.assertEqual((fixture.root/'replay.dps').read_bytes(),(fixture.root/'inert-sdk.dps').read_bytes())
                    bad=service_fixtures.deepcopy(fixture.design)
                    next(s for s in bad['screens'] if s['elements'])['elements'].pop()
                    rejected=await client.call_tool('plan_changes',dict(session_id=sid,design=bad,idempotency_key='delete-live'))
                    self.assertTrue(rejected.is_error);self.assertIn('NONINERT_LITERAL',str(rejected))
                    self.assertEqual((fixture.root/'source.dps').read_bytes(),fixture.source)
        asyncio.run(exercise())

    def test_static_int16_conversion_over_all_nine_sdk_tools(self):
        fixture=service_fixtures.StaticIntegerStorageServiceTests()
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        installation=fixture.root/'isolated_install'
        shutil.copytree(ROOT/'src/universal_hmi',installation/'src/universal_hmi')
        shutil.copytree(fixture.authority_dir,installation/'src/universal_hmi/data/profiles/driver_contracts', dirs_exist_ok=True)
        shutil.copytree(fixture.numeric_authorities,installation/'src/universal_hmi/data/profiles/numeric_contracts', dirs_exist_ok=True)
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-m','universal_hmi.cli','--profiles',str(fixture.profile_dir),'serve','--workspace',str(fixture.root)],env={**os.environ,'PYTHONPATH':str(installation/'src'),'PYTHONUTF8':'1'},cwd=str(fixture.root))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize();self.assertEqual(len((await client.list_tools()).tools),9)
                    async def call(name,**args):
                        result=await client.call_tool(name,args);self.assertFalse(result.is_error,str(result));return result.structured_content
                    await call('capabilities',profile_id='blank_program_v1')
                    sid=(await call('open_project',profile_id='blank_program_v1',source_path='blank.dps'))['session_id']
                    self.assertFalse((await call('inspect',session_id=sid))['inventory']['screens'][0]['elements'])
                    plan=await call('plan_changes',session_id=sid,design=fixture.design,idempotency_key='signed')
                    self.assertEqual(sum(o['op']=='convert_numeric_storage' for o in plan['operations']),2)
                    self.assertFalse((await call('validate',session_id=sid,plan_id=plan['plan_id']))['findings'])
                    self.assertIn('CONCEPTUAL_IR',str(await call('preview',session_id=sid,plan_id=plan['plan_id'])))
                    await call('apply_plan',session_id=sid,plan_id=plan['plan_id'],approval_path=fixture.approve(plan))
                    saved=await call('save_as',session_id=sid,output_path='signed-sdk.dps')
                    self.assertEqual(saved['sha256'],(await call('diff',session_id=sid))['candidate_sha256'])
                    native=service_fixtures.NativeAdapter((fixture.root/'signed-sdk.dps').read_bytes(),'delta_dopsoft2')
                    self.assertEqual(native.inspect()['screens'][0]['elements'][4]['native_fields']['MemFmt'],'1')
                    bad=service_fixtures.deepcopy(fixture.design);bad['screens'][0]['elements'][4].update(fractional=1,value_model='integer_fixed_decimal')
                    rejected=await client.call_tool('plan_changes',dict(session_id=sid,design=bad,idempotency_key='signed-fractional'))
                    self.assertTrue(rejected.is_error);self.assertIn('UNQUALIFIED_FIXED_DECIMAL',str(rejected))
                    self.assertEqual((fixture.root/'blank.dps').read_bytes(),fixture.target)
        asyncio.run(exercise())

    def test_radix_direction_contract_over_all_nine_sdk_tools(self):
        fixture=service_fixtures.RadixNamespaceServiceTests()
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        installation=fixture.root/'isolated_install'
        shutil.copytree(ROOT/'src/universal_hmi',installation/'src/universal_hmi')
        shutil.copytree(fixture.authority_dir,installation/'src/universal_hmi/data/profiles/driver_contracts', dirs_exist_ok=True)
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=[
                '-m','universal_hmi.cli','--profiles',str(fixture.profile_dir),'serve','--workspace',str(fixture.root)],
                env={**os.environ,'PYTHONPATH':str(installation/'src'),'PYTHONUTF8':'1'},cwd=str(fixture.root))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize();self.assertEqual(len((await client.list_tools()).tools),9)
                    async def call(name,**args):
                        result=await client.call_tool(name,args);self.assertFalse(result.is_error,str(result));return result.structured_content
                    await call('capabilities',profile_id='blank_program_v1')
                    sid=(await call('open_project',profile_id='blank_program_v1',source_path='blank.dps'))['session_id']
                    self.assertFalse((await call('inspect',session_id=sid))['inventory']['screens'][0]['elements'])
                    plan=await call('plan_changes',session_id=sid,design=fixture.design,idempotency_key='radix')
                    self.assertFalse((await call('validate',session_id=sid,plan_id=plan['plan_id']))['findings'])
                    self.assertIn('CONCEPTUAL_IR',str(await call('preview',session_id=sid,plan_id=plan['plan_id'])))
                    await call('apply_plan',session_id=sid,plan_id=plan['plan_id'],approval_path=fixture.approve(plan))
                    saved=await call('save_as',session_id=sid,output_path='radix-sdk.dps')
                    self.assertEqual(saved['sha256'],(await call('diff',session_id=sid))['candidate_sha256'])
                    native=service_fixtures.NativeAdapter((fixture.root/'radix-sdk.dps').read_bytes(),'delta_dopsoft2')
                    self.assertEqual(native.inspect()['screens'][0]['elements'][2]['bindings']['write']['address'],'{Link2}1@Y10')
                    bad=service_fixtures.deepcopy(fixture.design);bad['tags'][0]['address']='{Link2}1@X0'
                    rejected=await client.call_tool('plan_changes',dict(session_id=sid,design=bad,idempotency_key='forged-x'))
                    self.assertTrue(rejected.is_error);self.assertIn('CONTROL_ADDRESS_SCOPE',str(rejected))
                    self.assertEqual((fixture.root/'blank.dps').read_bytes(),fixture.target)
        asyncio.run(exercise())

    def test_multipage_mixed_program_over_all_nine_sdk_tools(self):
        fixture=service_fixtures.MultipageProgramServiceTests()
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        # A separate installed package/registry fixture proves the subprocess
        # gate without mutating the real registered authority or adding a
        # runtime override for callers. All bytes here are original TEST ONLY.
        installation=fixture.root/'isolated_install'
        shutil.copytree(ROOT/'src/universal_hmi',installation/'src/universal_hmi')
        shutil.copytree(fixture.authority_dir,installation/'src/universal_hmi/data/profiles/layout_contracts', dirs_exist_ok=True)
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=[
                '-m','universal_hmi.cli','--profiles',str(fixture.profile_dir),'serve','--workspace',str(fixture.root)],
                env={**os.environ,'PYTHONPATH':str(installation/'src'),'PYTHONUTF8':'1'},cwd=str(fixture.root))
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize();self.assertEqual(len((await client.list_tools()).tools),9)
                    async def call(name,**args):
                        result=await client.call_tool(name,args);self.assertFalse(result.is_error,str(result));return result.structured_content
                    caps=await call('capabilities',profile_id='multipage_program_v1')
                    self.assertEqual(caps['capabilities']['indicator'],'OFFLINE_PASS')
                    opened=await call('open_project',profile_id='multipage_program_v1',source_path='blank.dps');sid=opened['session_id']
                    self.assertEqual((await call('inspect',session_id=sid))['inventory']['screens'][0]['elements'],[])
                    plan=await call('plan_changes',session_id=sid,design=fixture.design,idempotency_key='mixed')
                    self.assertFalse((await call('validate',session_id=sid,plan_id=plan['plan_id']))['findings'])
                    self.assertIn('ÖLÇÜM',(await call('preview',session_id=sid,plan_id=plan['plan_id']))['html'])
                    await call('apply_plan',session_id=sid,plan_id=plan['plan_id'],approval_path=fixture.approve(plan))
                    saved=await call('save_as',session_id=sid,output_path='mixed-sdk.dps')
                    self.assertEqual(saved['sha256'],(await call('diff',session_id=sid))['candidate_sha256'])
                    native=service_fixtures.NativeAdapter((fixture.root/'mixed-sdk.dps').read_bytes(),'delta_dopsoft2')
                    self.assertEqual([s['id'] for s in native.inspect()['screens']],['1','2','3'])
                    self.assertEqual([s['native_fields']['ScreenAction'] for s in native.inspect()['screens']][1:],['0','0'])
                    self.assertNotIn(b'HMIPortNr0=1660265583',native.envelope.body)
                    self.assertEqual((fixture.root/'blank.dps').read_bytes(),fixture.target)
        asyncio.run(exercise())

    def test_fixed_decimal_display_qualified_transaction_over_all_nine_sdk_tools(self):
        fixture=service_fixtures.FixedDecimalServiceTests()
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=[
                '-m','universal_hmi.cli','--profiles',str(fixture.profile_dir),'serve','--workspace',str(fixture.root)])
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize();self.assertEqual(len((await client.list_tools()).tools),9)
                    async def call(name,**args):
                        result=await client.call_tool(name,args);self.assertFalse(result.is_error,str(result));return result.structured_content
                    caps=await call('capabilities',profile_id='blank_program_v1')
                    self.assertEqual(caps['capabilities']['numeric_fixed_decimal_input'],'UNVERIFIED')
                    opened=await call('open_project',profile_id='blank_program_v1',source_path='blank.dps');sid=opened['session_id']
                    self.assertEqual((await call('inspect',session_id=sid))['inventory']['screens'][0]['elements'],[])
                    plan=await call('plan_changes',session_id=sid,design=fixture.design,idempotency_key='qualified-display')
                    self.assertFalse((await call('validate',session_id=sid,plan_id=plan['plan_id']))['findings'])
                    self.assertIn('integer_fixed_decimal',(await call('preview',session_id=sid,plan_id=plan['plan_id']))['html'])
                    await call('apply_plan',session_id=sid,plan_id=plan['plan_id'],approval_path=fixture.approve(plan))
                    saved=await call('save_as',session_id=sid,output_path='fixed-display-sdk.dps')
                    self.assertEqual(saved['sha256'],(await call('diff',session_id=sid))['candidate_sha256'])
                    native=service_fixtures.NativeAdapter((fixture.root/'fixed-display-sdk.dps').read_bytes(),'delta_dopsoft2')
                    fields=native.inspect()['screens'][0]['elements'][5]['native_fields']
                    self.assertEqual(fields['DotNum'],'2');self.assertNotIn('MinValue',fields);self.assertNotIn('MaxValue',fields)
                    self.assertEqual((fixture.root/'blank.dps').read_bytes(),fixture.target)
        asyncio.run(exercise())

    def test_distinct_driver_addresses_clean_program_over_all_nine_sdk_tools(self):
        fixture=service_fixtures.DriverNamespaceServiceTests()
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=[
                '-m','universal_hmi.cli','--profiles',str(fixture.profile_dir),'serve','--workspace',str(fixture.root)])
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize()
                    tools=await client.list_tools();self.assertEqual(len(tools.tools),9)
                    async def call(name,**args):
                        result=await client.call_tool(name,args)
                        self.assertFalse(result.is_error,str(result))
                        return result.structured_content
                    caps=await call('capabilities',profile_id='blank_program_v1')
                    self.assertEqual(caps['capabilities']['driver_address_namespace'],'OFFLINE_PASS')
                    opened=await call('open_project',profile_id='blank_program_v1',source_path='blank.dps')
                    sid=opened['session_id']
                    inventory=await call('inspect',session_id=sid)
                    self.assertEqual(inventory['inventory']['screens'][0]['elements'],[])
                    plan=await call('plan_changes',session_id=sid,design=fixture.design,idempotency_key='distinct-driver')
                    checked=await call('validate',session_id=sid,plan_id=plan['plan_id']);self.assertFalse(checked['findings'])
                    preview=await call('preview',session_id=sid,plan_id=plan['plan_id']);self.assertIn('html',preview)
                    applied=await call('apply_plan',session_id=sid,plan_id=plan['plan_id'],approval_path=fixture.approve(plan))
                    self.assertFalse(applied['program_writer_complete'])
                    saved=await call('save_as',session_id=sid,output_path='distinct-sdk.dps')
                    diff=await call('diff',session_id=sid);self.assertEqual(saved['sha256'],diff['candidate_sha256'])
                    self.assertEqual((fixture.root/'blank.dps').read_bytes(),fixture.target)
                    native=service_fixtures.NativeAdapter((fixture.root/'distinct-sdk.dps').read_bytes(),'delta_dopsoft2')
                    owners=native.inspect()['screens'][0]['elements']
                    self.assertEqual([v['bindings']['read']['address'] for v in owners],[v['address'] for v in fixture.design['tags']])
        asyncio.run(exercise())

    def test_source_observations_over_sdk_are_redacted_and_cannot_enable_emission(self):
        from test_native import CalibrationInventoryTests
        for family, suffix in [('delta_dopsoft2', '.dps'), ('delta_diascreen', '.dpa')]:
            with self.subTest(family=family):
                fixture = service_fixtures.ServiceTests()
                fixture.setUp()
                self.addCleanup(fixture.doCleanups)
                fixture.profile['family'] = family
                (fixture.profile_dir / (fixture.profile_id + '.json')).write_text(json.dumps(fixture.profile))
                source = CalibrationInventoryTests().source(family)
                (fixture.root / ('capture' + suffix)).write_bytes(source)
                async def exercise():
                    params = StdioServerParameters(command=sys.executable, args=[
                        '-m', 'universal_hmi.cli', '--profiles', str(fixture.profile_dir),
                        'serve', '--workspace', str(fixture.root)])
                    async with stdio_client(params) as (read, write):
                        async with ClientSession(read, write) as client:
                            await client.initialize()
                            opened = await client.call_tool('open_project', {'profile_id': fixture.profile_id, 'source_path': 'capture' + suffix})
                            self.assertFalse(opened.is_error, str(opened))
                            session = opened.structured_content['session_id']
                            result = await client.call_tool('inspect', {'session_id': session})
                            self.assertFalse(result.is_error, str(result))
                            facts = result.structured_content['inventory']['calibration_inventory']
                            self.assertEqual(facts['source_sha256'], service_fixtures.service_byte_hash(source))
                            self.assertEqual(facts['qualification'], 'UNVERIFIED')
                            self.assertFalse(facts['emission_authority'])
                            self.assertNotIn('DoNotExport123', json.dumps(facts))
                            self.assertNotIn('123456', json.dumps(facts))
                            self.assertNotIn('owners', facts)
                            self.assertEqual(facts['observed_owners'], 2)
                            self.assertEqual(len(facts['driver_blocks']), 1)
                            self.assertEqual((fixture.root / ('capture' + suffix)).read_bytes(), source)
                            (fixture.root / ('capture' + suffix)).write_bytes(b'changed source')
                            blocked = await client.call_tool('inspect', {'session_id': session})
                            self.assertTrue(blocked.is_error)
                            self.assertIn('SOURCE_CHANGED', str(blocked))
                asyncio.run(exercise())

    def test_appended_literal_page_generation_full_transaction_over_sdk_stdio(self):
        for family in ('delta_dopsoft2', 'delta_diascreen'):
            with self.subTest(family=family):
                fixture = service_fixtures.LiteralPageGenerationTests()
                fixture.setUp()
                self.addCleanup(fixture.doCleanups)
                if family != fixture.family:
                    fixture.configure(family)
                async def exercise():
                    params = StdioServerParameters(command=sys.executable, args=[
                        '-m', 'universal_hmi.cli', '--profiles', str(fixture.profile_dir), 'serve', '--workspace', str(fixture.root)])
                    async with stdio_client(params) as (read, write):
                        async with ClientSession(read, write) as client:
                            await client.initialize()
                            async def call(name, **args):
                                result = await client.call_tool(name, args)
                                self.assertFalse(result.is_error, str(result))
                                return result.structured_content
                            opened = await call('open_project', profile_id=fixture.profile_id, source_path='source' + fixture.extension)
                            session = opened['session_id']
                            receipt = await call('plan_changes', session_id=session, design=fixture.added(), idempotency_key='new-pages')
                            duplicate = await call('plan_changes', session_id=session, design=fixture.added(), idempotency_key='new-pages')
                            self.assertEqual(receipt, duplicate)
                            preview = await call('preview', session_id=session, plan_id=receipt['plan_id'])
                            self.assertIn('TEXT INTENT ONLY', preview['html'])
                            checked = await call('validate', session_id=session, plan_id=receipt['plan_id'])
                            self.assertEqual(checked['findings'], [])
                            self.assertEqual(checked['scope'], 'APPEND_LITERAL_PAGES')
                            applied = await call('apply_plan', session_id=session, plan_id=receipt['plan_id'], approval_path=fixture.approve(receipt))
                            self.assertEqual(applied['opaque_graph_dependencies'], 'UNKNOWN')
                            saved = await call('save_as', session_id=session, output_path='mcp-generated' + fixture.extension)
                            diff = await call('diff', session_id=session)
                            self.assertEqual(saved['sha256'], diff['candidate_sha256'])
                            self.assertEqual([s['id'] for s in diff['candidate_inventory']['screens']], ['1', '2', '3'])
                            self.assertFalse(applied['program_writer_complete'])
                            self.assertEqual((fixture.root / ('source' + fixture.extension)).read_bytes(), fixture.source)
                asyncio.run(exercise())

    def test_existing_owner_candidate_full_transaction_over_sdk_stdio(self):
        for family in ('delta_dopsoft2', 'delta_diascreen'):
            with self.subTest(family=family):
                fixture = service_fixtures.ExistingOwnerCandidateTests()
                fixture.setUp()
                self.addCleanup(fixture.doCleanups)
                fixture.configure(family, vendor_gate=True)
                async def exercise():
                    params = StdioServerParameters(command=sys.executable, args=[
                        '-m', 'universal_hmi.cli', '--profiles', str(fixture.profile_dir),
                        'serve', '--workspace', str(fixture.root)])
                    async with stdio_client(params) as (read, write):
                        async with ClientSession(read, write) as client:
                            await client.initialize()
                            async def call(name, **args):
                                response = await client.call_tool(name, args)
                                self.assertFalse(response.is_error, str(response))
                                return response.structured_content
                            opened = await call('open_project', profile_id=fixture.profile_id, source_path='source' + fixture.extension)
                            session = opened['session_id']
                            self.assertEqual(opened['evidence'], 'UNVERIFIED')
                            inventory = await call('inspect', session_id=session)
                            self.assertEqual(inventory['inventory']['model_id'], '-1106816944')
                            receipt = await call('plan_changes', session_id=session, design=fixture.changed(), idempotency_key='existing-owner')
                            self.assertEqual(receipt['findings'], [])
                            self.assertEqual(receipt['calibration_sha256'], fixture.profile['native_schema']['native_candidate']['sha256'])
                            preview = await call('preview', session_id=session, plan_id=receipt['plan_id'])
                            self.assertEqual(preview['render_kind'], 'CONCEPTUAL_IR')
                            self.assertIn('NATIVE NOT RENDERED', preview['html'])
                            validated = await call('validate', session_id=session, plan_id=receipt['plan_id'])
                            self.assertTrue(validated['offline_pass'])
                            self.assertFalse(validated['program_writer_complete'])
                            fixture.approve(receipt, vendor_gate=True)
                            applied = await call('apply_plan', session_id=session, plan_id=receipt['plan_id'], approval_path='approval.json')
                            self.assertEqual(applied['purpose'], 'OFFLINE_NATIVE_CANDIDATE')
                            self.assertEqual(applied['vendor'], 'NOT_RUN')
                            saved = await call('save_as', session_id=session, output_path='stdio-candidate' + fixture.extension)
                            diff = await call('diff', session_id=session)
                            self.assertEqual(saved['sha256'], diff['candidate_sha256'])
                            self.assertEqual(diff['candidate_inventory']['screens'][0]['elements'][0]['texts'][0]['text'], 'Ç')
                            self.assertEqual((fixture.root / ('source' + fixture.extension)).read_bytes(), fixture.source)
                            repeated = await call('save_as', session_id=session, output_path='stdio-candidate' + fixture.extension)
                            self.assertEqual(repeated, saved)
                            (fixture.root / 'calibration.json').write_bytes(b'{}')
                            blocked = await client.call_tool('save_as', {'session_id': session, 'output_path': 'stdio-candidate' + fixture.extension})
                            self.assertTrue(blocked.is_error)
                            self.assertIn('CALIBRATION_CHANGED', str(blocked))
                asyncio.run(exercise())

    def test_public_alarm_messages_and_preserved_views_over_actual_stdio(self):
        for family in ('delta_diascreen', 'delta_dopsoft2'):
            with self.subTest(family=family):
                fixture = service_fixtures.ServiceTests()
                fixture.setUp()
                self.addCleanup(fixture.doCleanups)
                extension = fixture.use_alarms(family)
                fixture.design['alarms'][0]['text'] = 'E001 — Kapak açık'
                async def exercise():
                    params = StdioServerParameters(command=sys.executable, args=[
                        '-m', 'universal_hmi.cli', '--profiles', str(fixture.profile_dir),
                        'serve', '--workspace', str(fixture.root)])
                    async with stdio_client(params) as (read, write):
                        async with ClientSession(read, write) as client:
                            await client.initialize()
                            async def call(name, **args):
                                response = await client.call_tool(name, args)
                                self.assertFalse(response.is_error, str(response))
                                return response.structured_content
                            session = (await call('open_project', profile_id=fixture.profile_id,
                                                  source_path=fixture.alarm_path))['session_id']
                            receipt = await call('plan_changes', session_id=session, design=fixture.design,
                                                 idempotency_key='alarm-wire')
                            self.assertEqual(receipt['findings'], [])
                            self.assertEqual([op['op'] for op in receipt['operations']], ['configure_alarm'])
                            preview = await call('preview', session_id=session, plan_id=receipt['plan_id'],
                                                 output_path='alarm-concept.html')
                            self.assertEqual(preview['render_kind'], 'CONCEPTUAL_IR')
                            self.assertTrue((await call('validate', session_id=session,
                                                        plan_id=receipt['plan_id']))['offline_pass'])
                            fixture.approve(receipt)
                            applied = await call('apply_plan', session_id=session, plan_id=receipt['plan_id'],
                                                 approval_path='approval.json')
                            saved = await call('save_as', session_id=session, output_path='alarm-wire' + extension)
                            diff = await call('diff', session_id=session)
                            self.assertEqual(saved['sha256'], diff['candidate_sha256'])
                            self.assertEqual(applied['production_native'], 'UNAVAILABLE')
                            self.assertEqual(applied['native_visual'], 'NOT_RUN')
                            self.assertEqual((fixture.root / fixture.alarm_path).read_bytes(), fixture.alarm_source)
                            changed = fixture.design
                            changed['alarms'][0]['text'] = 'Different approved text'
                            rejected = await call('plan_changes', session_id=session, design=changed,
                                operations=receipt['operations'], idempotency_key='wrong-wire-message')
                            blocked = await call('validate', session_id=session, plan_id=rejected['plan_id'])
                            self.assertFalse(blocked['offline_pass'])
                            self.assertIn('NATIVE_OPERATION_INTENT', [f['code'] for f in blocked['findings']])
                asyncio.run(exercise())

    def test_portable_defaults_from_unrelated_working_directory(self):
        async def exercise(cwd):
            params = StdioServerParameters(command=sys.executable, args=['-m', 'universal_hmi.cli', 'serve'], cwd=cwd)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    response = await client.call_tool('open_project', {'profile_id': 'synthetic_diascreen'})
                    self.assertFalse(response.is_error, str(response))
                    self.assertIn('session_id', response.structured_content)
        with tempfile.TemporaryDirectory(prefix='Independent MCP caller ') as cwd:
            asyncio.run(exercise(cwd))

    def test_actual_handshake_tools_and_calls(self):
        async def exercise(workspace):
            params = StdioServerParameters(command=sys.executable, args=[
                '-m', 'universal_hmi.cli', '--profiles', str(ROOT / 'profiles'),
                'serve', '--workspace', workspace], env={**os.environ, 'PYTHONPATH': str(ROOT / 'src')})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    response = await client.initialize()
                    self.assertEqual(response.server_info.name, 'universal-hmi-agents')
                    from universal_hmi import __version__
                    self.assertEqual(response.server_info.version, __version__)
                    tools = await client.list_tools()
                    self.assertEqual({tool.name for tool in tools.tools}, {
                        'open_project', 'capabilities', 'inspect', 'plan_changes', 'preview',
                        'validate', 'apply_plan', 'save_as', 'diff'})
                    capabilities = await client.call_tool('capabilities', {'profile_id': 'dop_b07s411_dopsoft2'})
                    self.assertFalse(capabilities.is_error)
                    self.assertIn('UNVERIFIED', str(capabilities))
                    opened = await client.call_tool('open_project', {'profile_id': 'synthetic_diascreen'})
                    self.assertFalse(opened.is_error)
                    structured = opened.structured_content
                    self.assertIn('session_id', structured)
                    bad = await client.call_tool('open_project', {'profile_id': '../escape'})
                    self.assertTrue(bad.is_error)
        with tempfile.TemporaryDirectory() as workspace:
            asyncio.run(exercise(workspace))

    def test_complete_transaction_over_actual_stdio(self):
        fixture = service_fixtures.ServiceTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=[
                '-m', 'universal_hmi.cli', '--profiles', str(fixture.profile_dir),
                'serve', '--workspace', str(fixture.root)], env={**os.environ, 'PYTHONPATH': str(ROOT / 'src')})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    async def call(name, **args):
                        response = await client.call_tool(name, args)
                        self.assertFalse(response.is_error, str(response))
                        return response.structured_content
                    opened = await call('open_project', profile_id=fixture.profile_id, source_path='source.dpa')
                    session = opened['session_id']
                    inventory = await call('inspect', session_id=session)
                    self.assertEqual(inventory['inventory']['model_id'], 'SYNTHETIC')
                    receipt = await call('plan_changes', session_id=session, design=fixture.design, operations=fixture.ops, idempotency_key='wire-once')
                    self.assertEqual(receipt['findings'], [])
                    preview = await call('preview', session_id=session, plan_id=receipt['plan_id'], output_path='concept.html')
                    self.assertEqual(preview['render_kind'], 'CONCEPTUAL_IR')
                    validation = await call('validate', session_id=session, plan_id=receipt['plan_id'])
                    self.assertTrue(validation['offline_pass'])
                    fixture.approve(receipt)
                    applied = await call('apply_plan', session_id=session, plan_id=receipt['plan_id'], approval_path='approval.json')
                    self.assertEqual(applied['production_native'], 'UNAVAILABLE')
                    saved = await call('save_as', session_id=session, output_path='wire.dpa')
                    diff = await call('diff', session_id=session)
                    self.assertEqual(saved['sha256'], diff['candidate_sha256'])
                    self.assertEqual(diff['candidate_inventory']['screens'][0]['elements'][0]['subtype'], '2')
        asyncio.run(exercise())

    def test_automatic_page_and_visual_contract_over_stdio(self):
        fixture = service_fixtures.ServiceTests()
        fixture.setUp()
        fixture.use_layout()
        self.addCleanup(fixture.doCleanups)
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=[
                '-m', 'universal_hmi.cli', '--profiles', str(fixture.profile_dir),
                'serve', '--workspace', str(fixture.root)])
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    async def call(name, **args):
                        response = await client.call_tool(name, args)
                        self.assertFalse(response.is_error, str(response))
                        return response.structured_content
                    session = (await call('open_project', profile_id=fixture.profile_id, source_path=fixture.layout_path))['session_id']
                    design = fixture.design
                    design['screens'][1]['name'] = 'Settings'
                    design['screens'].append(dict(id='detail', native_id='3', name='Detail', width=100, height=80, elements=[]))
                    receipt = await call('plan_changes', session_id=session, design=design, idempotency_key='layout-wire')
                    self.assertEqual(receipt['findings'], [])
                    self.assertIn('clone_screen', [op['op'] for op in receipt['operations']])
                    self.assertTrue((await call('validate', session_id=session, plan_id=receipt['plan_id']))['offline_pass'])
                    fixture.approve(receipt)
                    applied = await call('apply_plan', session_id=session, plan_id=receipt['plan_id'], approval_path='approval.json')
                    self.assertEqual(applied['native_visual'], 'NOT_RUN')
                    self.assertEqual(applied['production_native'], 'UNAVAILABLE')
                    saved = await call('save_as', session_id=session, output_path='layout-wire.dpa')
                    diff = await call('diff', session_id=session)
                    self.assertEqual(saved['sha256'], diff['candidate_sha256'])
                    screens = diff['candidate_inventory']['screens']
                    self.assertEqual([s['id'] for s in screens], ['1', '2', '3'])
                    self.assertEqual(screens[0]['elements'][-1]['native_fields']['GoToScreenName'], 'Settings')
                    self.assertEqual((fixture.root / fixture.layout_path).read_bytes(), fixture.layout_source)
                    # The protocol must expose the same fail-closed caption gate.
                    design['screens'][0]['elements'][1].pop('text')
                    rejected = await client.call_tool('plan_changes', dict(session_id=session, design=design, idempotency_key='missing-label'))
                    self.assertTrue(rejected.is_error)
        asyncio.run(exercise())

    def test_automatic_numeric_transaction_over_stdio(self):
        fixture = service_fixtures.ServiceTests()
        fixture.setUp()
        fixture.use_numeric()
        self.addCleanup(fixture.doCleanups)
        async def exercise():
            params = StdioServerParameters(command=sys.executable,args=[
                '-m','universal_hmi.cli','--profiles',str(fixture.profile_dir),
                'serve','--workspace',str(fixture.root)])
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize()
                    tools=await client.list_tools()
                    schema=next(t.input_schema for t in tools.tools if t.name=='plan_changes')
                    self.assertNotIn('operations',schema.get('required',[]))
                    async def call(name,**args):
                        response=await client.call_tool(name,args)
                        self.assertFalse(response.is_error,str(response))
                        return response.structured_content
                    opened=await call('open_project',profile_id=fixture.profile_id,source_path=fixture.numeric_source_path)
                    receipt=await call('plan_changes',session_id=opened['session_id'],design=fixture.design,idempotency_key='auto-number')
                    self.assertEqual(receipt['planning_mode'],'COMPILED_FROM_DESIGN')
                    fixture.approve(receipt)
                    await call('apply_plan',session_id=opened['session_id'],plan_id=receipt['plan_id'],approval_path='approval.json')
                    saved=await call('save_as',session_id=opened['session_id'],output_path='auto-numeric.dpa')
                    diff=await call('diff',session_id=opened['session_id'])
                    self.assertEqual(saved['sha256'],diff['candidate_sha256'])
                    fields=diff['candidate_inventory']['screens'][0]['elements'][0]['native_fields']
                    self.assertEqual((fields['MinValue'],fields['MaxValue']),('-25.5','125.75'))
        asyncio.run(exercise())

    def test_linked_unit_contract_over_actual_stdio_both_envelopes(self):
        for family in ('delta_diascreen', 'delta_dopsoft2'):
            for kind in ('numeric_input', 'numeric_display'):
                with self.subTest(family=family, kind=kind):
                    fixture = service_fixtures.ServiceTests()
                    fixture.setUp()
                    extension = fixture.use_units(family, kind)
                    self.addCleanup(fixture.doCleanups)

                    async def exercise():
                        params = StdioServerParameters(command=sys.executable, args=[
                            '-m', 'universal_hmi.cli', '--profiles', str(fixture.profile_dir),
                            'serve', '--workspace', str(fixture.root)])
                        async with stdio_client(params) as (read, write):
                            async with ClientSession(read, write) as client:
                                await client.initialize()

                                async def call(name, **args):
                                    result = await client.call_tool(name, args)
                                    self.assertFalse(result.is_error, str(result))
                                    return result.structured_content

                                session = (await call('open_project', profile_id=fixture.profile_id,
                                                      source_path=fixture.numeric_source_path))['session_id']
                                receipt = await call('plan_changes', session_id=session, design=fixture.design,
                                                     idempotency_key='unit-wire')
                                self.assertEqual(receipt['findings'], [])
                                again = await call('plan_changes', session_id=session, design=fixture.design,
                                                   idempotency_key='unit-wire')
                                self.assertEqual(receipt, again)
                                self.assertNotIn('set_unit_caption', [op['op'] for op in receipt['operations']])
                                preview = await call('preview', session_id=session, plan_id=receipt['plan_id'])
                                self.assertEqual(preview['render_kind'], 'CONCEPTUAL_IR')
                                self.assertNotIn('class="unit"', preview['html'])
                                self.assertTrue((await call('validate', session_id=session, plan_id=receipt['plan_id']))['offline_pass'])
                                fixture.approve(receipt)
                                applied = await call('apply_plan', session_id=session, plan_id=receipt['plan_id'],
                                                     approval_path='approval.json')
                                self.assertEqual(applied['production_native'], 'UNAVAILABLE')
                                path = 'wire-units' + extension
                                saved = await call('save_as', session_id=session, output_path=path)
                                diff = await call('diff', session_id=session)
                                self.assertEqual(saved['sha256'], diff['candidate_sha256'])
                                number, label = diff['candidate_inventory']['screens'][0]['elements']
                                self.assertEqual(number['native_fields']['ShowUnit'], '0')
                                self.assertEqual(number['unit_captions'][0]['text'], '')
                                self.assertEqual(label['texts'][0]['text'], 'mm')
                                self.assertEqual((fixture.root / fixture.numeric_source_path).read_bytes(), fixture.unit_source)
                                reopened = (await call('open_project', profile_id=fixture.profile_id, source_path=path))['session_id']
                                noop = await call('plan_changes', session_id=reopened, design=fixture.design,
                                                  operations=[], idempotency_key='unit-wire-noop')
                                fixture.approve(noop)
                                await call('apply_plan', session_id=reopened, plan_id=noop['plan_id'], approval_path='approval.json')
                                self.assertTrue((await call('diff', session_id=reopened))['byte_equal'])
                                # Low-level framing authority is not public
                                # permission to create a second unit caption.
                                operations = [dict(op='set_unit_caption', screen_id='1', element_id='1',
                                                   text='mm', expected_unit_baseline_sha256='0' * 64)]
                                denied = await call('plan_changes', session_id=reopened, design=fixture.design,
                                                    operations=operations, idempotency_key='embedded-unit-denied')
                                validation = await call('validate', session_id=reopened, plan_id=denied['plan_id'])
                                self.assertIn('NATIVE_OPERATION_INTENT', [f['code'] for f in validation['findings']])

                    asyncio.run(exercise())

    def test_automatic_macro_transaction_over_stdio_both_envelopes(self):
        for family in ('delta_diascreen', 'delta_dopsoft2'):
            with self.subTest(family=family):
                fixture = service_fixtures.ServiceTests()
                fixture.setUp()
                extension = fixture.use_macros(family)
                self.addCleanup(fixture.doCleanups)

                async def exercise():
                    params = StdioServerParameters(command=sys.executable, args=[
                        '-m', 'universal_hmi.cli', '--profiles', str(fixture.profile_dir),
                        'serve', '--workspace', str(fixture.root)])
                    async with stdio_client(params) as (read, write):
                        async with ClientSession(read, write) as client:
                            await client.initialize()

                            async def call(name, **args):
                                response = await client.call_tool(name, args)
                                self.assertFalse(response.is_error, str(response))
                                return response.structured_content

                            opened = await call('open_project', profile_id=fixture.profile_id, source_path=fixture.macro_source_path)
                            receipt = await call('plan_changes', session_id=opened['session_id'], design=fixture.design, idempotency_key='macro-wire')
                            self.assertEqual(len([op for op in receipt['operations'] if op['op'] == 'configure_macro']), 3)
                            checked = await call('validate', session_id=opened['session_id'], plan_id=receipt['plan_id'])
                            self.assertTrue(checked['offline_pass'])
                            fixture.approve(receipt)
                            await call('apply_plan', session_id=opened['session_id'], plan_id=receipt['plan_id'], approval_path='approval.json')
                            saved = await call('save_as', session_id=opened['session_id'], output_path='macro-wire' + extension)
                            diff = await call('diff', session_id=opened['session_id'])
                            self.assertEqual(saved['sha256'], diff['candidate_sha256'])
                            macros = diff['candidate_inventory']['macros']
                            clock = next(m for m in macros if m['owner'] == {'kind': 'application'} and m['field'] == 'ClockMacroLen')
                            self.assertEqual(clock['status'], 'REV_FRAMING_PASS')
                            self.assertEqual(clock['schedule']['ClockMacroDelayTime'], '100')
                asyncio.run(exercise())


if __name__ == '__main__':
    unittest.main()
