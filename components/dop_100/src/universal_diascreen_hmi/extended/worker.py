# SPDX-License-Identifier: Apache-2.0
"""Fail-closed vendor worker boundary. No arbitrary executable or receipt inputs."""
from .common import hash_value, require

# Routes are code-reviewed implementation, not caller-provided config/receipts.
# Empty until a documented calling contract and an actual adapter are qualified.
IMPLEMENTED_ROUTES = {}


class VendorWorker:
    def __init__(self, journal):
        self.journal = journal

    def capabilities(self):
        return {name: {'implemented': name in IMPLEMENTED_ROUTES, 'headless': False, 'native_qualified': False}
                for name in ('create_project', 'configure_target', 'vendor_open_save_reopen', 'vendor_compile',
                             'offline_simulator', 'build_transfer_package', 'inspect_transfer_package')}

    def execute(self, operation, source_sha256, candidate_sha256):
        hash_value(source_sha256); hash_value(candidate_sha256)
        require(operation in IMPLEMENTED_ROUTES, 'NOT_IMPLEMENTED',
                'No executable documented vendor adapter qualified for ' + operation)
        # This boundary deliberately has no generic executable/argument runner.
        # A future reviewed route must implement ownership, timeout, diagnostic,
        # new-only artifact and reconciliation semantics before registration.
        require(False, 'ROUTE_NOT_QUALIFIED', 'Registration alone cannot authorize vendor execution')
