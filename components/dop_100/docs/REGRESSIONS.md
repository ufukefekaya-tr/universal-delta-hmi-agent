# Regressions and retractions

Every shared regression R01–R21 has a concrete test target below. Earlier **PLANNED_FINAL_TREE_REVERIFY** wording recorded a verification gate, not a permanent test result. Actual execution status belongs to version-qualified test reports and the final review for the exact release tree; a named method alone is not proof of execution. Original 0.1.0 reports remain historical and cannot establish acceptance of a changed 0.1.1 tree.

| ID | Scenario | Concrete test target | Required result / history |
|---|---|---|---|
| R01 | Invalid width scalar rejected | `test_operations.OperationTests.test_r01_r02_invalid_rectangles` | Reject non-integer/nonpositive width before edit. |
| R02 | Negative or off-canvas coordinates rejected | `test_operations.OperationTests.test_r01_r02_invalid_rectangles` | Reject negative/off-panel geometry. |
| R03 | Negative element index cannot delete last object | `test_native.NativeTests.test_negative_identity_is_not_list_index` | Nonnegative screen-local identity; never Python negative indexing. |
| R04 | Opening another project does not silently discard pending changes | `test_session.SessionTests.test_r04_pending_open_does_not_discard` | Refuse another open while pending state exists. |
| R05 | Start rebinding does not alter Start2 | `test_operations.OperationTests.test_r05_exact_rebind_not_prefix` | Exact field owner/address; similarly named symbols unchanged. |
| R06 | Framed length cannot be edited separately from blob | `test_native.NativeTests.test_length_cannot_be_patched_as_scalar` | Count and payload are one owned span. |
| R07 | Truncated counted blob rejected | `test_native.NativeTests.test_declared_huge_truncated_blob_rejected` | Truncated/oversized counted blobs STOP. |
| R08 | CRLF-less opaque tail preserved | `test_native.NativeTests.test_opaque_tail_without_eol_is_exact` | Retain opaque suffix without terminal CRLF. |
| R09 | Repeated clone does not duplicate objects/pages | `test_operations.OperationTests.test_clone_unique_fresh_identity_geometry_and_reorder` | Fresh IDs and replay checks stop duplicate object/page insertion. |
| R10 | TriggerVar included in address inventory | `test_operations.OperationTests.test_r10_all_indexed_address_owners_and_trigger` | Inventory includes TriggerVar with read semantics. |
| R11 | Negative state index rejected | `test_operations.OperationTests.test_r03_r11_no_negative_identity_or_state` | Select actual Value, not state list index. |
| R12 | Turkish text never silently coerced to Latin1 | `test_native.NativeTests.test_counted_unicode` | Count UTF-16; unsupported encoding never silently becomes Latin1. |
| R13 | Wrong-page background detected | `test_preview.PreviewTests.test_wrong_page_background_and_ambiguous_resource` | Page offset and resource hash must match selected background. |
| R14 | Maintained subtype1.4 distinguished from momentary1.3 for qualified source | `test_operations.OperationTests.test_r14_real_behavior_codes_and_value_text` | Source-qualified historical1.3momentary/1.4maintained; old dictionary withdrawn. |
| R15 | Floating limits not guessed from missing display width | `test_operations.OperationTests.test_r15_limits_explicit_and_no_float_extremes_or_time_alias` | Explicit finite type-domain limits and digits; no E308/width guess. |
| R16 | Visible macro source not replaced together with parsed operands | `test_macros.MacroTests.test_exact_operand_replacement_preserves_visible_source` | Field0 immutable; failed visible-source Application rewrite stays withdrawn. |
| R17 | Compiled evidence tied to source/candidate hash | `test_macros.MacroTests.test_compiled_stale_source_candidate_and_actual_sha_rejected` | Actual artifact SHA plus receipt source/candidate pair; still no compile/runtime proof. |
| R18 | Rolled-back global macros not silently reenabled | `test_operations.OperationTests.test_r18_clear_global_macro_not_default_reenable` | No implicit regeneration of rolled-back startup/heartbeat globals. |
| R19 | Raw zero not automatically healthy; unknown codes visible | `test_status.StatusTests.test_r19_active_fault_zero_and_unknown_raw_never_healthy` | Active fault code0possible; raw unknown values never default healthy. |
| R20 | Text simplification does not imply visual style flattening | `test_operations.OperationTests.test_visual_geometry_and_full_inverse` | Caption-only edit preserves colors/fonts/gradients/geometry. |
| R21 | Style-only edits preserve writes addresses macros XML and unknown bytes | `test_operations.OperationTests.test_r21_style_only_preserves_controls_bindings_macro_xml_unknown` | Style-only ledger preserves all writes/addresses/macros/XML/unknown bytes. |

## Withdrawn and unresolved claims

- N003 visual PASS was withdrawn after background/layer defects. Earlier PNG or browser checks do not establish current native fidelity.
- Early button tables confused momentary and maintained. The qualified historical correction is1.3momentary/1.4maintained; a type dictionary is not a behavior oracle.
- E308 limits contributed to reported compilation failures. A13→12error reduction after one999upper-limit edit isolates that change, not every cause. Fifteen-digit limits do not prove ten-digit display fit or safe physical ranges.
- TIME4/RW metadata did not establish numeric keypad compatibility. A real separate millisecond interface is a contract boundary; TIME is never relabelled UDINT in XML.
- N008 macro operand acceptance was withdrawn; the shared-draft race candidate remains rejected. Startup/heartbeat/ownership globals were rolled back and are not defaults.
- N010 rewrote visible source together with parsed Application scope and produced five Error109 failures. Native acceptance was withdrawn. Failed archive and later delivery-location bytes have different identities.
- N011 preserved visible source and changed parsed operands. Human CompilePASS lacked exact native-byte linkage; live Error7/HB0 and stale bare descriptors remained. Final review STOP; no compile/runtime fix is claimed.
- N011 resave differences were not MeMeCode-only: an application prefix and two SRAM blocks changed too. Opaque bytes are not harmless metadata without evidence.
- Other observed N012/N013 copies differ from reviewed archives and fail historical whole-section/reverse checks. Old PASS reports cannot qualify changed source bytes. SOURCE_MANIFEST.json retains both identities.
- N014 current fault/drive presentation is not alarm history, fault ACK/reset, reliable mode selection or transport-cache invalidation. Active code0is possible; raw unknown values stay visible.
- N015 removed corrupted sparse mappings and retained raw values. Passive explanation text is not an alarm engine. Text simplification does not imply style flattening.
- N016 style-only inverse protects function. Sequential aesthetic approval is not gradient/radius/transparency/DPI qualification or native pixel/runtime acceptance.

## Negative-test discipline

Serialize and reread mutated candidates before validation. A stale in-memory payload or unchanged fixture cannot be the rejection oracle. Check exact identities, lengths, raw suffixes, metadata, access roles, malformed framing, unknown effects, wrong backgrounds, source/profile/plan hashes and complete inverse bytes. A failed/skipped test stays failed/not-run. No family fallback, arbitrary property writer, source overwrite or automatic macro generation hides it.



## Version 0.1.1 contract corrections

These patch findings supplement the historical R01–R21 identities; they do not renumber or withdraw their negative-test requirements.

| ID | Defect and corrected contract | Concrete test target |
|---|---|---|
| DIA-R2 | The 0.1.0 pre-application preview workflow claim is withdrawn: preview/validate selected current bytes only. An exact pending plan selector now reviews immutable proposed bytes and derived profile without applying or saving. Returned view, plan, candidate and candidate-profile identities distinguish proposal from current; stale/drifted/applied selections stop. | `test_plan_review.PlanReviewTests.test_proposal_caption_sha_and_readonly_state`; `test_plan_review.PlanReviewTests.test_gallery_uses_proposed_background_profile`; `test_plan_review.PlanReviewTests.test_stdio_readonly_proposal_review_and_discovery_schemas` |
| D04 | Coordinate order was advertised without an explicit ordering contract. Layout/text now opt into native page order, Y, X, then screen-local layer index; default layer order and renderer order are preserved. | `test_plan_review.PlanReviewTests.test_coordinate_layout_text_order_preserves_render_layers`; `test_plan_review.PlanReviewTests.test_sort_invalid_or_unrelated_views_refused` |

Proposal identity/failure checks also cover unknown or malformed selectors, source/profile/donor drift, stale/applied/discarded plans, inverse-ledger failure, unsupported rendering and unchanged session/files on refusal. MCP null is rejected; omitted selection means current. These are offline contract checks, not vendor pixel, compile, panel or runtime acceptance. Retained 0.1.0 packages and reports are historical evidence only.
