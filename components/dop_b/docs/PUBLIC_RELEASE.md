# Public distribution — 0.2.1

Original source and documentation: Apache-2.0. This patch adds license metadata, retained notices and an exact dependency/runtime notice inventory. Native behavior is unchanged from 0.2.0; dispatcher and worker subprocesses now use isolated Python imports to reject mutable state/PYTHONPATH module injection; prior tests are historical evidence, not newly executed vendor acceptance.

The source-only export excludes runtimes, wheels, vendor installers, customer files, Git history, caches and local state. The optional offline bundle additionally retains the pinned Windows/Linux runtimes and wheels with their own licenses. Runtime dependency notices are taken from matching upstream full builds because install-only archives omit that directory. Component metadata and source hashes are recorded in `licenses/inventory.json`.

Run `python scripts/public_release_audit.py --archive PREVIOUS_PINNED_BUNDLE --runtime-full MATCHING_FULL_BUILD_DIRECTORY` to regenerate the notice inventory. Never relicense dependency code as Apache-2.0. Delta editors, proprietary project examples, customer assets and license-unclear upstream code are not distributed.
