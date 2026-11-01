"""Build/audit positive-membership release archives; no workspace collection."""
import importlib.util
from pathlib import Path
_spec=importlib.util.spec_from_file_location("delta_package_contract",Path(__file__).resolve().parents[1]/"tools/package_contract.py")
_contract=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_contract)
build=_contract.build
audit=_contract.audit
if __name__=="__main__":_contract.main()
