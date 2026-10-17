"""Create the source-qualified flat synthetic integration fixture only.

This uses original public regression builders, never customer/vendor assets.
The component's general framing example deliberately includes unsupported fills;
this variant is specifically bounded to the saved-layer flat-v1 preview contract.
"""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'components/dop_100'))
from tests.test_plan_review import native,profile

def create(destination):
    destination=Path(destination).resolve()
    if destination.exists() or not destination.parent.is_dir():raise ValueError('Fresh fixture destination required')
    raw=native();selected=profile()
    encoded=json.dumps(selected,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
    receipt={'scope':'ORIGINAL_SYNTHETIC_FLAT_FIXTURE_ONLY','source_sha256':hashlib.sha256(raw).hexdigest(),'profile_sha256':hashlib.sha256(encoded).hexdigest(),'vendor':'NOT_RUN','physical':'NOT_RUN'}
    destination.mkdir()
    for name,data in {'source.dpa':raw,'profile.json':encoded+b'\n','IDENTITY.json':(json.dumps(receipt,indent=2)+'\n').encode('utf8')}.items():
        with (destination/name).open('xb') as stream:stream.write(data)
    return receipt
if __name__=='__main__':print(json.dumps(create(sys.argv[1])))
