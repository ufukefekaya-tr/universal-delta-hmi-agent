# Independent final review — 0.1.1

**SCOPED_OFFLINE_PASS — no open important or critical findings.**

The orchestrator recorded the independent final response from `/root/diascreen_tenth` and its separate matrix/documentation and package/privacy reviewers. Reviewers were read-only and did not alter implementation, reports, checkpoint or Git state.

The reviewed pre-report freeze contains60files and has SHA-256 `0bb4b458b34534d807440eddd4f9ba24fbf6862c949dd5c948f60e97e06f4cf4`. All30tested Python file hashes match the actual final test report. The full suite ran148tests:147passed, one host symlink-privilege skip, zero failures or errors. The reparse refusal branch is separately tested. Python3.14 ran the tests; Python3.11 syntax was checked, but its runtime was not executed.

## Important regression and correction

**DIA-R2:** In0.1.0, `plan_changes` could propose a new caption while `preview` still rendered current/source bytes. The general pre-application visual-review claim is withdrawn for0.1.0. Its reports and artifacts are preserved as historical evidence, not current acceptance.

In0.1.1, optional `plan_sha256` in `preview` and `validate` selects the exact pending proposal's candidate and derived profile. Both return explicit current/proposal identity, plan SHA, candidate SHA and candidate-profile SHA. Source, profile, base, record, candidate, ledger and donor pins are checked. Unknown, malformed, drifted, stale, rolled-back and already-applied selections fail closed. Review works in a read-only process and does not apply, save, consume approval or change inspection/session state. After application, callers omit the proposal selector and inspect current.

Independent counterexamples cover two pending proposals, changed captions, proposed backgrounds, gallery selection, source/profile/ledger/candidate/donor drift, successful and failed review snapshots, and a length-changing pending plan over an applied plan. Proposal validation reverses pending steps, then applied steps, back to original payload and thumbnail. A failing inverse does not receive preservation acceptance.

**D04:** `inspect` layout/text now supports explicit `sort='coordinate'`: native page order, Y, X, then zero-based screen-local `layer_index`. Default saved layer order remains unchanged. Legacy layout/screenshot_text publish the same selector. Sorting affects only copied inspection rows; native bytes, hit/draw order and preview layer order are preserved. Other coordinate-sort views and invalid selectors are rejected.

The dedicated12-test module exercises these paths, full session/disk snapshots, MCP input schemas and all18retained legacy names. Matrix rows now record actual final stdio discovery instead of stale pending labels. Discovery is not a claim that unqualified or refused features are implemented; alarm history, runtime and other support levels remain unchanged.

## Built and installed artifacts

- Wheel SHA-256: `c87ea901d52c613cae3074e90cfb291f865f5bd78f1e3e4681b1b08737e39fa0`.
- Source distribution SHA-256: `936b83aa0d0e34fa6826f8df44e7fcaf295ab1ce8048b0a2d0faafd7ef01cf54`.
- All11runtime modules match source; Apache-2.0 LICENSE/NOTICE and metadata are included; no runtime dependency or private/native/font assets are bundled.
- Isolated installed API checks:20passed. A separate installed-only MCP subprocess used isolated Python with no PYTHONPATH and verified proposal preview/validate before apply, exact identities, current preservation, rejection paths, approval/write gates, save/reread and rollback.

All20private source files remain unchanged. Their repeated qualification equals the historical report:17no-op passes, two in-memory inverse passes and one N008 missing-identity STOP. This is not universal native compatibility.

The canonical portable ZIP is made after this report and contains it plus its exact file manifest. Separate extracted-launch and archive verification is recorded in the external release receipt; that receipt is excluded from the archive to avoid a hash cycle. Original0.1.0packages remain byte-exact.

## Acceptance boundary

This is bounded offline acceptance. Vendor compilation, vendor pixel fidelity, panel/runtime, PLC connection, physical operation, heartbeat scheduling, atomic mode safety, transport reconnect/freshness and alarm-history runtime remain NOT_RUN or NOT_ESTABLISHED. Unsupported rendering remains refused. No Computer Use, IDE, control-target connection, umbrella mutation, push or remote publication occurred in this patch scope.
