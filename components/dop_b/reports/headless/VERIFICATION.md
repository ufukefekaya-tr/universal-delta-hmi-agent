# Headless 0.2.0 verification

Release readiness is tracked in [STATUS.json](STATUS.json). Historical reports outside this folder describe earlier revisions and are not acceptance of this release.

Final complete source regression: **979 tests passed, zero skips, 340.228 seconds**. Final runtime source is pinned in SOURCE_MANIFEST.json; the separately tested last installer-only WindowsApps-alias correction is described below. Windows and Linux installed-wheel acceptance each passed **52 tests** against the identical final wheel. No Computer Use, vendor executable, PLC connection, panel download or remote push was used.

## Genuine neutral native job

The real SDK stdio client discovered all 14 tools, preflighted and submitted the job, polled it, then obtained a verified `OFFLINE_DELIVERY_COMPLETE` result. Four actual independent review reports were required; no synthetic approval was used for this native pilot. The second aesthetic reviewer read and hashed the first report. The final technical reviewer inspected the saved native bytes and compared the entire decoded body with the separate IR-to-raw expectation.

- Job: `5ef684ead86a45caba5f2b2b8ff5c6c7`.
- Input blank SHA: `c16e6b81580f91f508becae459dede710239d5f6f243800404575cdf77b3abfb`.
- Reviewed design subject: `593655b495de87ed1c452b288d8a17f6f0c7595a9797ae7d5b890c1e31645564`.
- Saved DPS: 55,700 bytes; SHA `d4cbd91b5a3e9d2b5c0815d17343cdd0e4c98dd188f784f6ce38024605e5792c`.
- Reviewed native subject: `d377509e2700182824074014bda463b41ff054449d68665e922a7c092a65e41d`.
- Decoded body SHA: `3a02f38a52f7baac45ef4c9bf538a9d41bea3fff61ee9531b5dc26dc35da9dbf`.

The B10S615-qualified source graph contains three pages and sixteen owners. Four button types remain distinct, UINT input/display retain storage and bounds, read-only feedback uses a separate bit, and three navigation targets match their native companion names. Source, opaque prefix, thumbnail, global prefix and qualified resource-tail preservation were checked. Macros are empty and enabled alarm count is zero in this pilot; it does not test every existing library feature.

All three previews are conceptual samples, not live controller values or native screenshots. Nine page/state images were reviewed. The sparse neutral layout and intentionally shared command bit are feature exercises, not a machine operator design. Native pixels, vendor compilation, communication/runtime behavior and physical panel acceptance are `NOT_RUN`. Opaque graph dependencies remain `UNKNOWN`; `program_writer_complete=false` remains unchanged.

## Protocol and portability

Automated fixture reviews are explicitly `TEST ONLY`; they test the review protocol and cannot replace the actual independent reports above. Negative tests cover missing/changed reviews, forged/rehashed packages, changed sources, unreviewed preview mutation, invalid staging before publication pin, idempotency conflicts, two queued stdio jobs, cumulative execution budgets, cancellation/publication races, process death and exact pinned recovery. Reference-pack tests reject traversal/links/case collisions and verify immutable archive snapshots.

The installed-wheel Windows and Linux acceptance results are each **52 tests, zero failures/errors/skips**. The exact accepted wheel SHA is `e6508c0e6a6a4a40e4aaf25756da766a0c5c7f7108ded3deb8ff1d75314d3527`. Tests call all fourteen actual SDK tools and close/restart a separate real server, which resumes the durable job without resubmission. These transport/fixture tests use visibly synthetic protocol reviews, independently of the genuine native review above. The final full source suite is recorded in STATUS when complete.

Windows provisioning is a fresh non-elevated user-owned directory on the existing Windows host, not a new Windows VM. The fixed runtime was provisioned locally with offline/no-index dependencies; final application-wheel fixes were reinstalled into that isolated environment before rerunning all 52 tests. Windows network denial was not externally enforced. Linux provisioning is fresh Ubuntu 24.04.5 userspace under a private WSL mount/network namespace, not a fresh kernel/VM. No Python or Git exists in that userspace before setup; uid/gid1000 is used, network access is denied and the socket probe returns ENETUNREACH101. The final wheel was installed through fresh offline setup there. Both environments exclude the source checkout and remove PYTHONPATH; tests use installed site-packages. These distinctions must remain in downstream claims.

Private source fixtures, machine-local paths, full logs and visual evidence stay outside the public MCP archive. The public source manifest pins the reviewed implementation and tests. Public code contains no dependency on the author's project folders.

An additional fresh network-denied Ubuntu run read the **actual** neutral pilot DPS with the installed NativeAdapter: 55,700 bytes, the same `d4cbd91b...` SHA above, three screens and sixteen elements. This was read/inspection only; it does not manufacture another native emission or transfer Windows review approval to a new job. The private artifact is excluded from the public archive. The final Windows installer also passed a targeted App Execution Alias probe: an unavailable WindowsApps Python alias is skipped without opening Store, and offline local provisioning completes.
