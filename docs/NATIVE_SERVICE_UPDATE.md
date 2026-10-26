# Native service update — 26 October 2026

The current source tree exposes **70 DIAScreen tools and aliases** through the isolated `dop_100__` route, plus `close_session`. Existing DOP-B implementation and evidence are unchanged. Published v0.2.1 offline archives retain their historical 30-tool DIAScreen backend; this source update does not change those immutable archives or their download locks.

The reusable implementation is `components/dop_100/src/universal_diascreen_hmi/extended/`. It imports the original generic backend, never a private customer build module. Default reference catalog is empty. No native project, tag catalog, customer endpoint, password, logo, machine logic, fonts or device data is distributed.

| Capability | Current file scope |
|---|---|
| Native inspection | Complete indexed page/object/state catalog, three counted UTF-16 text/font banks, numeric/address/access/scale fields, navigation and endpoint readback; opaque resources remain explicitly bounded |
| Atomic native transactions | Existing source owners: captions, colors (Windows COLORREF BGR), geometry, source clone/move/static replacement, page clone, navigation and reviewed 800×480 opaque background DIBs |
| Typed registers | Native BOOL/INT/DINT/REAL widget bindings with exact source hashes, separate access/width/address/order contracts; unknown signed/unsigned coercion is refused |
| Numeric scale | Real native gain/offset/digit fields. REAL decimal count formats display; fixed integer decimals divide by10^DotNum. Source type and unit semantics remain explicit |
| Persistence | Immutable SQLite proposals, engine/source/profile/candidate hashes, inspect-first exact approval, new-only save/reread, fresh-session recovery and replay refusal |
| Artifacts | Deterministic one-DPA offline project ZIP, member/source hashes, interrupted outcome reconciliation. This is not a vendor transfer package |
| Contract rebind | Metadata-only compatibility receipt when declared ABI, enums, limits and scale match; no native apply/save replay and no PLC behavior acceptance |
| Visuals | Optional Pillow12.2.0, host-supplied hash-pinned fonts, synthetic saved-layer PNG and glyph-fit checks; no vendor pixels/runtime claim |

New native editing is deliberately limited to observed DOP-107EV800×480 / native6.6.2.48 owners. Old generic file operations keep their explicit reviewed profiles. Native macros/auth/Application fields remain preserved by the extended transaction engine. Cloning to a page created in the same plan is refused: inspect the new page in a later plan. Sparse enum controls cannot be represented by unrestricted numeric inputs.

`plan_native_update` accepts a canonical hash-bound version1 specification. Inspect the current candidate first, review its returned plan, call `apply_plan` with the exact digest, then `save_new` or `save_as` with the exact candidate hash. Persistent proposal inspection and recovery use `inspect_native_plan`, `restore_plan`, `restore_candidate`, `inspect_operation`, and `reconcile_operation`. A workspace is bound to engine bytes; changed code requires a fresh workspace.

The standard MCP entry is `python -B -m universal_diascreen_hmi.cli --workspace <folder>`. A CLI using the same service is `python -B -m universal_diascreen_hmi.extended.runner --workspace <folder> --batch`; feed newline JSON objects containing name and arguments. Writes additionally require `--allow-write`. The journal under workspace/.runtime is local state; native originals remain unchanged.

For source development use `python tools/ci.py install` and `python tools/ci.py test` with the declared Python/dependencies. Optional visuals can be installed with the component's `visuals` extra. The historical offline bootstrap archive does not install the new optional visual dependency. No global settings are changed by this update.

Optional trusted-host reference catalog: set `DIA_HMI_REFERENCE_ROOT` outside the published package, provide registry.json with schema `delta.hmi.reference-registry.v1`, versioned hashes and root-relative source paths. Do not expose catalog configuration as an MCP job input. Fonts require `DIA_HMI_FONT_ROOT` and matching font_sha256 entries in that host catalog. No reference/seed is bundled. A source-qualified donor is still required; this update does not claim template-free project creation.

Vendor headless opening/saving/compilation, real offline simulator, vendor transfer package, generic native alarm/history/recipe/trend/account constructors and password management remain explicitly unimplemented. Existing opaque data is preserved or affected edits are refused. These limitations do not prevent the qualified offline file services.

Final current offline receipts are in reports/NATIVE_SERVICE_UPDATE.json:62 gateway,981 unchanged DOP-B and163 DIAScreen cases;0failures,1declared Windows symlink permission skip. Actual source/open-plan-apply-new-save/reopen/ZIP paths pass in fresh CLI/MCP processes; optional font/render and relocated wheel integrity also pass. PNG framing/load/conversion and uncertain I/O return structured errors.


Typed visibility0.4.5: [existing readonly numeric/static visibility fields](TYPED_VISIBILITY.md) can use an exact BOOL contract while preserving the original source condition and numeric data type. Source-intent/file preservation is tested; manufacturer runtime truth remains separate.
