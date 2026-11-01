# SPDX-License-Identifier: Apache-2.0
"""Closed decoder plumbing. Synthetic opaque bytes never qualify a vendor variant."""
from pathlib import Path
import struct,tempfile,unittest
from unittest.mock import patch
from tests.test_extended import fixture
from tests.fixtures import line
from universal_diascreen_hmi.extended.hmi4_bootstrap import *
from universal_diascreen_hmi.extended import native_resource_intake as resources
from universal_diascreen_hmi.extended.hmi4_service import Service
from universal_diascreen_hmi.resources import flat_dib

def synthetic_walk_fixture():
    raw,profile=fixture();q=Project(raw);opaque=b'\x00'*resources.SYS_BYTES
    tail=b'[SubMacro]\r\n'+b''.join(line(f'SubMacro{kind}{i:03d}',0 if kind=='Protect' else '00000000') for i in range(1,513) for kind in ('Protect','PWD'))
    tail+=b'[Global_Auxkey]\r\n[Alarm]\r\n'+b''.join(line(k,0) for k in sorted(resources.ALARM|{p+str(n) for p in ('EnableCol','DisplayOrder') for n in range(1,8)}))
    tail+=b'[History]\r\n'+b''.join(line(k,0) for k in sorted(resources.HISTORY))+b'[NewTextBank]\r\nwFont001=Arial\r\n[Tag]\r\nTagLinkCount=0\r\n'
    tail+=b'[100_SRAM_DATA]\r\n'+struct.pack('<I',0)+b'\r\n'+opaque+b'[Picture]\r\nSize=0\r\n\r\n[Background]\r\n'
    dib=flat_dib(800,480,0x111111);tail+=line('Size',len(dib))+dib+b'\r\n[DIATag]\r\nDIATagResource=0\r\n[DeviceTable]\r\n'
    tail+=b''.join(line(k,0) for k in sorted(resources.DEVICE))+b'[MQTTFile]\r\n[END]\r\n'
    data=q.file.encode(q.file.payload[:q.index.tail_start]+tail);profile.pop('reviewed_resources');profile['indexed_layout_sha256']=layout_digest(Project(data))
    return data,profile,opaque

class ResourceSurfaceTests(unittest.TestCase):
    def test_public_service_uses_existing_closed_decoder_and_refuses_opaque_variant(self):
        raw,profile,opaque=synthetic_walk_fixture()
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'source.dpa').write_bytes(raw);s=Service(d);s.open_project('source.dpa',sha(raw),profile,sha(canonical(profile)))
            with self.assertRaises(Error) as cm:s.inspect_native_resource_banks(sha(raw))
            self.assertEqual(cm.exception.code,'RESOURCE_OPAQUE_VARIANT')
            # Test harness substitutes ONLY the opaque sentinel hash to exercise the remaining walk.
            # This is not an added production decoder variant or a vendor-qualified file.
            with patch.object(resources,'SYS_SHA',sha(opaque)):
                r=s.inspect_native_resource_banks(sha(raw))
            self.assertEqual(r['ownership'],'VERSION_PINNED_COUNTED_FRAMING_THROUGH_EOF')
            self.assertFalse(r['native_file_written']);self.assertFalse(r['native_qualified']);self.assertEqual(len(r['banks']),2)
            self.assertEqual((Path(d)/'source.dpa').read_bytes(),raw)
            with self.assertRaises(Error) as cm:s.inspect_native_resource_banks('0'*64)
            self.assertEqual(cm.exception.code,'CANDIDATE_HASH')
    def test_incomplete_framing_never_gets_resource_profile(self):
        raw,profile=fixture()
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'source.dpa').write_bytes(raw);s=Service(d);s.open_project('source.dpa',sha(raw),profile,sha(canonical(profile)))
            with self.assertRaises(Error):s.inspect_native_resource_banks(sha(raw))

if __name__=='__main__':unittest.main()
