# Isolated stdio integration

Run one backend process per workspace/session. The process owns an immutable source snapshot, pinned profile, optional donors, reviewed plan and pending candidate. Do not share mutable project state between independent clients.

```text
python -m universal_diascreen_hmi.cli --workspace ./workspace
python -m universal_diascreen_hmi.cli --workspace ./workspace --allow-write --read-root ./reference-inputs
```

The workspace and additional read-root directories must already exist. File paths are resolved under those roots. Outputs are new-only workspace paths. A source or donor must never be selected as an output. Profile data is supplied as a JSON object, not as a backend-read profile pathname. No GUI/IDE/control-target process or network connection is part of this interface.

## Transport

Use MCP initialization, then `tools/list` and `tools/call` over JSON-RPC 2.0. Each input/output message is one UTF-8 JSON line. Standard output contains protocol messages only; diagnostics belong on standard error. The transport is a subprocess stdio channel, not HTTP and not a listening TCP service. An SDK is optional on the client side; the backend has no runtime SDK dependency.

Tool arguments are explicit JSON objects. Tool results contain JSON text in MCP content blocks and structured results where supplied by the server. Read the declared schemas instead of invoking an arbitrary method/property or relying on a historical tool list. Transport/protocol failures are distinct from structured `AgentError` tool failures.

The common tool contract is:

| Tool | Arguments and effect |
|---|---|
| `open_project` | `path`, `source_sha256`, JSON object `profile`, `profile_sha256`; pins exact source bytes and canonical profile data, then opens one project |
| `capabilities` | No arguments; reports actual support and exclusions |
| `inspect` | `view`, optional `page_id`, `element_id`, `query`, `sort`; read-only inspection and layout evidence |
| `plan_changes` | `operations` list; builds an exact proposed candidate/ledger without implicitly applying it |
| `preview` | Optional `page_id`, `values`, `gallery`, `plan_sha256`; returns bounded saved-layer SVG/evidence for the selected current or proposed candidate |
| `validate` | Optional `plan_sha256`; reports offline checks and remaining unqualified areas for the selected current or proposed candidate |
| `apply_plan` | `plan_sha256`, `approval_sha256`; applies only the exact reviewed plan with local write permission |
| `save_as` | `path`, `candidate_sha256`; saves a new workspace file, rereads it and returns evidence |
| `diff` | No arguments; describes exact source/candidate changes and preservation evidence |

`inspect.view` is one of `project`, `screens`, `layout`, `element`, `find`, `addresses`, `macros`, `alarms`, `symbols`, `resources`, `text`, or `design`. Read-only catalog coverage can be partial; an inspection view is not a claim that all corresponding runtime subsystems exist.

`sort` defaults to `layer`, retaining native page and element layer order. For `layout` and `text`, `sort='coordinate'` sorts within each native page by Y, then X, then screen-local zero-based `layer_index`. Native page order is preserved even when page IDs are numerically out of order. Layout rows expose `layer_index`; the default textual line format is unchanged. Invalid sort values and coordinate sorting of unrelated views are rejected. Inspection sorting does not edit bytes or reorder the renderer.

Additional tools:

| Tool | Purpose |
|---|---|
| `register_donor(donor_id,path,sha256)` | Register a separate immutable donor with an exact identity |
| `pending_changes()` | Read pending plan/candidate status |
| `rollback()` | Discard process-local pending changes; never overwrite a source or previously saved output |
| `inspect_compiled(path,artifact_sha256,source_sha256,candidate_sha256,receipt)` | Partial receipt-bound compiled observation; no compilation or deployment |

The 18 legacy names remain part of discovery: `open_project`, `list_screens`, `layout`, `element`, `find`, `addresses`, `macros`, `alarms`, `set_property`, `set_text`, `rebind`, `pending_changes`, `save`, `screenshot_text`, `clone_element`, `clone_screen`, `delete_element`, `set_state_text`.

Legacy editing aliases create plans only. `save` is an alias for new-only `save_as`. `screenshot_text` is textual inspection, not a vendor screenshot. Legacy `layout` and `screenshot_text` accept optional `sort` with the same `layer`/`coordinate` behavior. Legacy discovery does not restore unsafe generic setters, silent discard, negative indexes or global substring rebinding.

## Pins and explicit application

`source_sha256` identifies the exact input bytes. `profile_sha256` identifies the canonical JSON object: keys sorted, compact separators `,` and `:`, UTF-8, `ensure_ascii=False`, and nonfinite values forbidden. Whitespace in a caller's local JSON file is not part of this identity. Donors carry their own byte SHA. A path resolving to another file with the same friendly name does not inherit authority.

The Python standard-library calculation is:

```python
import hashlib, json
profile_bytes = json.dumps(profile, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
profile_sha256 = hashlib.sha256(profile_bytes).hexdigest()
```

Call `inspect` before planning and applying. `inspect(view='project')` reports the editable-index digest and coverage. Every edit plan requires the caller's `reviewed_index_ack` and exact `indexed_layout_sha256` pin. Unknown byte ownership remains unsupported until separately qualified; acknowledgement is not a generic bypass.

After `plan_changes`, review its exact operations, source/profile/candidate identities, proposed change summaries, unsupported areas and returned `plan_sha256`. In 0.1.1, supply that digest to `validate(plan_sha256=...)` and `preview(plan_sha256=...)` to inspect the immutable proposal before applying it. Proposal review uses the proposed bytes and derived profile, including changed background pins; gallery selection follows that same proposal.

Both tools return `view`, `plan_sha256`, `candidate_sha256`, and `candidate_profile_sha256`. With a selected proposal, `view` is `proposal` and the plan digest is echoed. When the selector is omitted, `view` is `current` and `plan_sha256` is null. The Python API's default `None` selects current; an explicitly supplied MCP null selector is rejected. This prevents an invalid supplied selector from silently selecting another view.

Proposal review requires a known, unapplied plan with unchanged source, base candidate/profile, proposal record/bytes/profile/ledger, donor registry and required inspection. Unknown, malformed, stale, drifted, applied or discarded plan selections are rejected. These tools do not apply a plan, consume authorization, alter inspection state, or write files; they work in a read-only process. After application, omit the selector to inspect the current candidate.

The 0.1.0 claim that this workflow could preview a pending proposal before application is withdrawn under DIA-R2. Version 0.1.0 selected the current candidate only; its retained packages and reports do not establish 0.1.1 acceptance. Internal ledgers support exact preservation and inverse checks; tool output does not imply that opaque bytes have a semantic decoder. To apply, all of these must hold:

1. The process was started with `--allow-write`.
2. The inspected source/profile and current plan still match their pins.
3. `apply_plan.plan_sha256` equals the reviewed plan's returned digest.
4. `apply_plan.approval_sha256` equals that same digest.

The approval equality is an explicit local consent field. It is not a digital signature, human identity check, privilege escalation token or vendor approval. Possession of a plan digest alone does not enable application in a read-only process.

The final `save_as.candidate_sha256` must match the candidate returned by the backend. Saving to an existing path is rejected. Do not retry an unknown save result blindly; inspect the new path and receipt first.

## Profile contract

This neutral shape shows the core fields. Replace the values with facts from the exact reviewed source and a qualified profile; placeholders are not usable digests.

```json
{
  "schema_version": 1,
  "family": "diascreen-dop100",
  "panel": {"width": 1024, "height": 600},
  "application_versions": ["6.6.2.48"],
  "link": "ExampleLink",
  "station": 0,
  "preview_model": "flat-v1",
  "background_sha256": {"1": "<raw DIB frame SHA-256>"},
  "reviewed_index_ack": true,
  "indexed_layout_sha256": "<exact digest from inspect view project>",
  "fonts": {}
}
```

The version is an example of the observed internal file-version form, not an assertion that every file from that version is supported. Saved `Version`/`NewVersion`, panel dimensions and family must match. A profile is reviewed data; the backend does not infer write eligibility from this example.

The Session requires an explicit `link` and `station`, including read-only opening; the example link must be replaced with the source-qualified link. Preview-specific fields qualify preview rather than making every read-only catalog view available. Numeric operations need `numeric_types` contracts with native fields such as `MemLen`, `MemFmt`, bit width, signed/floating status and bounded literal/display rules. `button_behavior` conversion is limited to raw1.3/1.4 contracts with source-qualified evidence; 1.7 SetValue remains a donor workflow. These mappings are deliberately not filled in by a universal guess.

Optional `fonts` map font names to workspace-relative asset paths and exact SHA-256 values. The session reads validated bytes and supplies them to the preview module. The preview module itself never searches installed fonts. Font assets are caller material and are not included in this package.

Optional reviewed resource boundaries acknowledge exact source-payload/header/blob hashes and nonoverlapping resource locations. They are required for resource access when the sequential suffix grammar is unqualified. See [FORMAT](FORMAT.md); a regex match must never be automatically marked reviewed.

## Operation scope

Plans may contain qualified existing-field/caption changes, exact role-aware rebinds, typed numeric changes, source-qualified button behavior, navigation, donor element/page clones, deletion, element/state ordering, explicit XML/background resource changes and bounded macro operations where their schemas qualify them. Each operation is checked against the actual source; requesting an absent field does not create a vendor schema.

An address inventory distinguishes object roles, visible macro source and parsed macro operands. Published RW metadata is necessary for a write binding, but does not prove process permission or a successful live write. Numeric TIME coercion, generic arbitrary property writes and substring tag substitution are outside the contract.

## Preview and acceptance

`preview` returns `OFFLINE_MODEL_ONLY`, issues, a layer digest and synthetic samples. `values` keys are exact saved ReadVar strings; no values are fetched from a PLC. Gallery cases deliberately exercise OFF/ON, limits, long and negative numbers independently. Shared-address fixture conflicts, unknown states and unsupported drawing behavior are refused.

Numeric values are formatted directly; the preview does not apply saved `GainValue`/`OffsetValue` scaling. A scale contract in the edit profile does not establish a scaled display's visual fidelity.

With no qualified font bytes, `FONT_METRICS_NOT_VERIFIED` is expected. SFNT glyph/advance checks and estimated occlusion cannot establish vendor pixels, border thickness, shaping, rasterization or native runtime. Compiled observation similarly cannot replace a real compiler log bound to the exact candidate.

Treat an offline validation failure as a stop for the affected operation. Keep sources, candidate hashes, exact diff/ledger, profile, donor identities and review receipts together. Independent final review and any human vendor/panel acceptance must refer to the exact saved candidate, not an earlier report with the same revision name.

Read-only `evaluate_status(values)` evaluates only synthetic interface evidence from optional `interface_contract`; it never polls a target or establishes healthy/working/start permission. `inspect(view=design)` supplies a native reference ledger and technical CSV, not vendor-import CSV.

Catalog selection is tied to DIATag link/station metadata. Optional `catalog_bindings` may fill missing metadata with reviewed XML hashes but cannot contradict a present link/station. XML updates are additive: existing node/type/member access and layout definitions are preserved. `binding_types` qualifies a previously unbound address field; `macro_slots` qualifies each opcode/operand kind, role and IEC type.

The workspace is trusted local caller storage. Root/path checks and exclusive new-file creation limit ordinary traversal and overwrite; this process is not an OS sandbox against a concurrent privileged filesystem attacker.
