Current source extension: [native service update](NATIVE_SERVICE_UPDATE.md). See the current 69-tool integration inventory; historical release evidence below remains scoped to its original bytes.

# Support matrix

This inventory is not a completion or vendor certificate. The [machine ledger](SUPPORT_MATRIX.json) maps every D01–D44/U01–U09 feature,18file tools,4GUI tools,2excluded save options and R01–R21 regression. [Source identities](../SOURCE_MANIFEST.json) are neutral IDs and raw-byte hashes; private source files and locations are excluded.

The nine common tools consolidate historical file intents: `open_project`, `capabilities`, `inspect`, `plan_changes`, `preview`, `validate`, `apply_plan`, `save_as`, `diff`. Their count does not reduce historical feature scope. Four GUI intents and source-overwrite/editor-reload options are intentionally excluded.

## Evidence boundaries

`OFFLINE_TESTED` describes bounded original module observations. `SOURCE_BOUND_UNQUALIFIED` means original primitives/code under explicit source/profile contracts. `CONTRACT_ONLY`, `DISCOVERED_UNQUALIFIED`, `ROLLED_BACK_NOT_DEFAULT` and `WORKFLOW_REQUIRED` retain unfinished or external scope explicitly. Vendor compile, native pixels, panel/runtime and physical acceptance remain NOT_RUN.

The final-tree test and review reports establish exact version-qualified execution. Historical0.1.0 reports are preserved under reports/releases/0.1.0. Named methods and discovery alone do not establish implemented functionality; the feature support levels and refusal limits remain binding.

## Feature-to-source-to-implementation-to-test ledger

Source references and per-test availability are expanded in SUPPORT_MATRIX.json. Every row also references the hashed shared checklist.

| ID | Feature | Level | Implementation | Concrete final test targets | Limits |
|---|---|---|---|---|---|
| D01 | Native container and unknown byte preservation | SOURCE_BOUND_UNQUALIFIED | `native.NativeFile`; `native.NativeIndex`; `native.apply_spans` | `test_native.NativeTests.test_noop_original_container`; `test_native.NativeTests.test_unknown_fields_survive_edit` | Bounded source spans and complete unknown-byte retention; exact source/profile only. |
| D02 | Application model resolution controller metadata | SOURCE_BOUND_UNQUALIFIED | `native.Project.info` | `test_session.SessionTests.test_profile_mismatch_and_profile_mutation` | Serialized model/version/resolution metadata is not editor execution evidence. |
| D03 | Screen element state geometry text address inventory | SOURCE_BOUND_UNQUALIFIED | `native.Project`; `session.inspect` | `test_session.SessionTests.test_inspect_before_plan_and_pins` | Inventory is not qualification of every native type. |
| D04 | Project find and explicit coordinate text/layout projection | SOURCE_BOUND_UNQUALIFIED | `session.inspect` | `test_plan_review.PlanReviewTests.test_coordinate_layout_text_order_preserves_render_layers`; `test_plan_review.PlanReviewTests.test_stdio_readonly_proposal_review_and_discovery_schemas` | Native layer order is default; coordinate is native page order/Y/X/layer_index; projection only, render z-order unchanged. |
| D05 | All address owners including trigger interlock visible unit dot and macros | SOURCE_BOUND_UNQUALIFIED | `operations.address_inventory` | `test_operations.OperationTests.test_r10_all_indexed_address_owners_and_trigger` | Trigger/interlock/visible/unit/dot and macro owners; unknown roles stay unqualified. |
| D06 | Donor clone with fresh IDs geometry target page and z-order | SOURCE_BOUND_UNQUALIFIED | `operations.operation_patches:clone_element`; `operations.operation_patches:reorder_element` | `test_operations.OperationTests.test_clone_unique_fresh_identity_geometry_and_reorder` | Pinned donor, fresh identities, explicit inheritance and complete order. |
| D07 | Screen creation clone deletion and navigation reference checks | SOURCE_BOUND_UNQUALIFIED | `operations.operation_patches:clone_screen`; `operations.validate_references` | `test_operations.OperationTests.test_screen_frame_clone_delete_and_navigation_guards` | Explicit frame/full donors and complete default/navigation references. |
| D08 | Turkish UTF16 state captions language fields descriptions | SOURCE_BOUND_UNQUALIFIED | `native.encode_token`; `operations.operation_patches:set_text` | `test_native.NativeTests.test_counted_unicode`; `test_operations.OperationTests.test_r12_turkish_caption_and_long_unicode` | Counted UTF-16; no silent Latin1 fallback. |
| D09 | Native geometry font alignment fill border | SOURCE_BOUND_UNQUALIFIED | `operations.ELEMENT_VISUAL`; `operations.STATE_VISUAL` | `test_operations.OperationTests.test_visual_geometry_and_full_inverse` | Qualified existing fields only; preserve functional owners. |
| D10 | DIB background and offset decode; remove duplicate background text | SOURCE_BOUND_UNQUALIFIED | `resources.flat_dib`; `preview.decode_dib` | `test_preview.PreviewTests.test_dib_channel_stride_orientation_and_32bit_unused_alpha`; `test_operations.OperationTests.test_flat_background_has_real_page_offset_and_no_old_text` | Text-free background append and actual page offsets; no bitmap controls. |
| D11 | Picture bank encode append import copy prune | DISCOVERED_UNQUALIFIED | `resources.resource`; `native.NativeIndex opaque retention` | `test_contracts.ContractTests.test_picture_bank_import_copy_and_prune_refused` | General picture import/copy/prune/codecs are absent; preserve or refuse. |
| D12 | Momentary maintained set-on set-off and navigation behaviors | SOURCE_BOUND_UNQUALIFIED | `operations.operation_patches:button_behavior`; `operations.operation_patches:navigation` | `test_operations.OperationTests.test_r14_real_behavior_codes_and_value_text` | Explicit source-qualified behavior contracts; no universal enum guess. |
| D13 | Value0/1 text color and request versus feedback | SOURCE_BOUND_UNQUALIFIED | `preview state selection`; `operations.state` | `test_preview.PreviewTests.test_actual_value_selection_commands_and_no_unknown_fallback`; `test_preview.PreviewTests.test_shared_address_fixture_conflict_and_numeric_cases` | Use actual Value; request readback is not physical feedback. |
| D14 | Mode selection opposite-bit macros; non-atomic semantics | CONTRACT_ONLY | `macros.MacroProgram`; `no atomic mode controller` | `test_contracts.ContractTests.test_atomic_mode_and_automatic_reconnect_replay_are_not_supplied` | Opposite-bit cleanup plus another write is non-atomic. |
| D15 | Numeric type width decimals digits limits scale offset and units | SOURCE_BOUND_UNQUALIFIED | `operations.numeric_changes`; `operations.operation_patches:numeric` | `test_operations.OperationTests.test_r15_limits_explicit_and_no_float_extremes_or_time_alias` | Explicit type/width/digits/decimals/limits/gain/offset and separate unit owners. |
| D16 | Numeric literal limit overflow and digit-fit regression | SOURCE_BOUND_UNQUALIFIED | `operations.numeric_changes`; `preview numeric formatting` | `test_operations.OperationTests.test_r15_limits_explicit_and_no_float_extremes_or_time_alias`; `test_preview.PreviewTests.test_numeric_exponent_is_bounded` | No guessed limits, overflow or insufficient digits; narrowing changes behavior. |
| D17 | Explicit separate TIME-to-ms PLC interface; no silent coercion | CONTRACT_ONLY | `symbols.SymbolCatalog.resolve`; `operations.numeric_changes TIME refusal` | `test_symbols.SymbolTests.test_enum_and_time_remain_distinct`; `test_operations.OperationTests.test_r15_limits_explicit_and_no_float_extremes_or_time_alias` | Require a real separate millisecond PLC interface; no bridge generation or XML relabel. |
| D18 | Counted embedded DIA XML replace and metadata preservation | SOURCE_BOUND_UNQUALIFIED | `resources.embedded_xml`; `resources.resource_patch`; `operations.operation_patches:replace_xml` | `test_native.NativeTests.test_resource_xml_and_exact_metadata`; `test_operations.OperationTests.test_xml_preserves_metadata_and_all_dependencies` | Raw-byte count includes BOM; unrelated metadata and suffix survive. |
| D19 | XML nested types structs arrays width and access resolver | OFFLINE_TESTED | `symbols.parse_symbols`; `symbols.SymbolCatalog.resolve` | `test_symbols.SymbolTests.test_actual_offsets_and_native_padding`; `test_symbols.SymbolTests.test_inclusive_array_bounds`; `test_symbols.SymbolTests.test_ancestor_access_cannot_be_restored_by_member` | Nested structs/arrays/enums and intersected access; no invented layout/stride. |
| D20 | Exact read/write rebind with typed access validation | SOURCE_BOUND_UNQUALIFIED | `symbols.validate_reference`; `operations.operation_patches:rebind` | `test_symbols.SymbolTests.test_role_specific_read_and_write_permissions`; `test_operations.OperationTests.test_r05_exact_rebind_not_prefix` | Exact owner/address, role, link and station; no substring/global replace. |
| D21 | All macro slots counted framing opcode five-fields and tail | OFFLINE_TESTED | `macros.parse_macro`; `macros.MacroProgram.to_bytes` | `test_macros.MacroTests.test_counted_roundtrip_and_source_with_newlines`; `test_macros.MacroTests.test_truncation_lengths_flags_and_trailing_bytes` | 02REV/opcode/five counted fields/observed tail; unknown opcodes read-only. |
| D22 | Visible statement distinct from parsed macro operands | OFFLINE_TESTED | `macros.MacroProgram.replace_operand`; `macros.MacroProgram.inspect` | `test_macros.MacroTests.test_exact_operand_replacement_preserves_visible_source`; `test_macros.MacroTests.test_legacy_display_operand_can_be_inspected_without_acceptance` | Field0 immutable during operand edits; display-form parsed operands flagged invalid. |
| D23 | Remote macro operand link station Application and type canonicalization | SOURCE_BOUND_UNQUALIFIED | `macros.parse_parsed_address`; `symbols.validate_reference` | `test_macros.MacroTests.test_display_addresses_and_source_statements_are_not_operands`; `test_operations.OperationTests.test_macro_slot_type_access_and_visible_source` | Parsed link/station/path syntax differs; Application qualification is not a universal repair. |
| D24 | Initial clock and button macro add remove preserve | SOURCE_BOUND_UNQUALIFIED | `operations.operation_patches:clear_macro`; `operations.operation_patches:donor_macro` | `test_operations.OperationTests.test_macro_slot_type_access_and_visible_source` | Explicit hash-pinned slot operation; retain all unrelated slots and opaque bytes. |
| D25 | BITON BITOFF assignment increment IF ELSE ENDIF from exact donors | SOURCE_BOUND_UNQUALIFIED | `macros.KNOWN_OPCODES`; `operations.operation_patches:donor_macro` | `test_macros.MacroTests.test_unknown_opcode_roundtrips_but_blocks_all_writes`; `test_operations.OperationTests.test_macro_slot_type_access_and_visible_source` | Observed BITON/BITOFF/word assignment/add/IF/ELSE/ENDIF exact reuse; no runtime guarantee. |
| D26 | Other upstream macro instructions including popup arithmetic FMOV FILLASC | DISCOVERED_UNQUALIFIED | `macros.parse_macro unknown opcode retention` | `test_macros.MacroTests.test_unknown_opcode_roundtrips_but_blocks_all_writes` | Other popup/arithmetic/FMOV/FILLASC writers absent; unsupported edits refuse. |
| D27 | Read-only compiled CIN operand inspection and stale-hash rejection | OFFLINE_TESTED | `macros.inspect_compiled` | `test_macros.MacroTests.test_compiled_stale_source_candidate_and_actual_sha_rejected`; `test_macros.MacroTests.test_compiled_observation_is_partial_counted_scan` | Caller-linked three-SHA receipt and partial BOOL scan; not full CIN/compiler/runtime acceptance. |
| D28 | Heartbeat startup inhibit rollover ownership reconnect contract | ROLLED_BACK_NOT_DEFAULT | `preservation and explicit clear_macro only` | `test_operations.OperationTests.test_r18_clear_global_macro_not_default_reenable` | No automatic heartbeat/startup/ownership/reconnect macro regeneration. |
| D29 | Draft versus drive-read freshness read/apply terminal result contract | CONTRACT_ONLY | `external transaction roles`; `generic read-only primitives` | `test_status.StatusTests.test_transfer_draft_fresh_readback_terminal_result_distinct` | Draft/readback/freshness/terminal result need a target-owned contract; no dispatcher. |
| D30 | Current fault view code family source catalog unknown fallback | CONTRACT_ONLY | `typed read-only numeric/text primitives` | `test_status.StatusTests.test_r19_active_fault_zero_and_unknown_raw_never_healthy` | Active/family/source/raw-code roles; no alarm/history engine or healthy sparse default. |
| D31 | Reference latch versus physical home and start permit roles | CONTRACT_ONLY | `read-only typed symbol roles` | `test_status.StatusTests.test_reference_latch_separate_from_sensor_and_start_permission` | Reference latch/home/start permit are distinct external signals. |
| D32 | Drive request ACK status freshness frequency raw fault roles | CONTRACT_ONLY | `read-only roles and saved-layer fixtures` | `test_status.StatusTests.test_drive_request_ack_fresh_status_frequency_not_conflated` | Request/ACK/status/freshness/frequency/raw fault differ; cache is not transport validity. |
| D33 | Compact current-fault strip and read-only service navigation | SOURCE_BOUND_UNQUALIFIED | `operations navigation/text/style primitives` | `test_operations.OperationTests.test_r21_style_only_preserves_controls_bindings_macro_xml_unknown` | Qualified source owners only; no invented fault reset/ACK/history side effects. |
| D34 | Two sequential aesthetic reviews preview approval style-only plan | WORKFLOW_REQUIRED | `docs/WORKFLOW.md`; `exact review hash gates` | `test_status.StatusTests.test_sequential_visual_reviews_challenge_first_and_producer` | Two sequential aesthetic reviews and approval bind exact proposal/candidate; runtime separate. |
| D35 | Saved layer render font cmap fit occlusion actual backgrounds | SOURCE_BOUND_UNQUALIFIED | `preview.render_preview`; `preview.FontFace` | `test_preview.PreviewTests.test_metrics_missing_glyph_overflow_and_occlusion`; `test_preview.PreviewTests.test_all_states_checked_not_only_selected` | Actual DIB/layers/states plus supplied font metrics/cmap; absent metrics never fit PASS. |
| D36 | Range state long-text sample galleries clearly marked examples | SOURCE_BOUND_UNQUALIFIED | `preview.render_gallery` | `test_preview.PreviewTests.test_shared_address_fixture_conflict_and_numeric_cases`; `test_preview.PreviewTests.test_offline_label_escape_no_font_claim_and_source_preserved` | Synthetic long/range/state examples labelled; shared-address fixture conflicts refuse. |
| D37 | Inverse byte diff restoring allowed changes equals entire original | SOURCE_BOUND_UNQUALIFIED | `native.restore_spans`; `operations.compile_changes` | `test_native.NativeTests.test_patch_precondition_and_overlap`; `test_session.SessionTests.test_multiple_approved_plans_inverse` | Reverse every exact ledger to recover whole payload and thumbnail. |
| D38 | Source plan codec hashes inspect-before-apply idempotency new-only save | SOURCE_BOUND_UNQUALIFIED | `session plan/authorization/save lifecycle` | `test_session.SessionTests.test_actual_apply_save_reread_diff_rollback_and_source` | Inspect before apply; exact authorization/hashes/replay protection/new-only save. |
| D39 | Real stdio mutation/result tests not only tool discovery | SOURCE_BOUND_UNQUALIFIED | `cli JSON-RPC stdio dispatch` | `test_stdio.StdioTests.test_real_process_mutation_not_only_discovery` | Actual isolated stdio mutation/reread required; tools/list is insufficient. |
| D40 | Source isolation scope manifests checkpoints Kaizen retractions | WORKFLOW_REQUIRED | `AGENTS.md`; `SYSTEM_PROMPT.md`; `tools/session_guard.py`; `docs/PROVENANCE.md` | `test_release.ReleaseTests.test_current_inventory_and_public_privacy` | Read-only sources, exact owners, root checkpoint, scoped commit and retractions. |
| D41 | Canonical design/tag ledger CSV mapping and operator preview | CONTRACT_ONLY | `docs design/tag ledger contract` | `test_status.StatusTests.test_design_csv_is_native_reference_not_vendor_import` | Object count differs from unique tags; CSV/HTML are references, not native import. |
| D42 | Missing-tag disabled placeholder no invented feedback/counters | WORKFLOW_REQUIRED | `symbols missing-path refusal`; `preview unknown-value refusal` | `test_symbols.SymbolTests.test_scalar_index_and_unindexed_array_traversal_rejected`; `test_contracts.ContractTests.test_missing_tag_is_not_invented_feedback_or_a_polling_counter` | Missing tags disabled/unknown; no polling event counters or fabricated feedback. |
| D43 | Preserve existing symbols and bindings during XML update | SOURCE_BOUND_UNQUALIFIED | `operations.operation_patches:replace_xml`; `symbols.validate_reference` | `test_operations.OperationTests.test_xml_preserves_metadata_and_all_dependencies`; `test_native.NativeTests.test_resource_xml_and_exact_metadata` | Validate surviving bindings against new catalog; retain type semantics/metadata. |
| D44 | Unsupported gradient radius transparency DPI explicitly stops render claim | SOURCE_BOUND_UNQUALIFIED | `preview effect qualification/refusal` | `test_preview.PreviewTests.test_unknown_effect_gradient_radius_and_family`; `test_preview.PreviewTests.test_wrong_page_background_and_ambiguous_resource` | Unsupported gradient/radius/transparency/DPI stop the affected claim; preservation is not pixels. |
| U01 | Enhanced recipes | DISCOVERED_UNQUALIFIED | `opaque retention and unsupported-operation refusal only` | `test_contracts.ContractTests.test_unimplemented_runtime_families_have_no_generic_builder` | Discovery retained explicitly. No generic builder, native/lifecycle rendering, or runtime qualification; preserve unknown owners or refuse the edit. |
| U02 | Native alarm history | DISCOVERED_UNQUALIFIED | `opaque retention and unsupported-operation refusal only` | `test_contracts.ContractTests.test_unimplemented_runtime_families_have_no_generic_builder` | Discovery retained explicitly. No generic builder, native/lifecycle rendering, or runtime qualification; preserve unknown owners or refuse the edit. |
| U03 | Trend history charts gauges | DISCOVERED_UNQUALIFIED | `opaque retention and unsupported-operation refusal only` | `test_contracts.ContractTests.test_unimplemented_runtime_families_have_no_generic_builder` | Discovery retained explicitly. No generic builder, native/lifecycle rendering, or runtime qualification; preserve unknown owners or refuse the edit. |
| U04 | Login accounts security operation log | DISCOVERED_UNQUALIFIED | `opaque retention and unsupported-operation refusal only` | `test_contracts.ContractTests.test_unimplemented_runtime_families_have_no_generic_builder` | Discovery retained explicitly. No generic builder, native/lifecycle rendering, or runtime qualification; preserve unknown owners or refuse the edit. |
| U05 | Multilingual state rendering | DISCOVERED_UNQUALIFIED | `opaque retention and unsupported-operation refusal only` | `test_contracts.ContractTests.test_unimplemented_runtime_families_have_no_generic_builder` | Discovery retained explicitly. No generic builder, native/lifecycle rendering, or runtime qualification; preserve unknown owners or refuse the edit. |
| U06 | System menu datetime brightness keypad | DISCOVERED_UNQUALIFIED | `opaque retention and unsupported-operation refusal only` | `test_contracts.ContractTests.test_unimplemented_runtime_families_have_no_generic_builder` | Discovery retained explicitly. No generic builder, native/lifecycle rendering, or runtime qualification; preserve unknown owners or refuse the edit. |
| U07 | Popup open close and leave cleanup | DISCOVERED_UNQUALIFIED | `opaque retention and unsupported-operation refusal only` | `test_contracts.ContractTests.test_unimplemented_runtime_families_have_no_generic_builder` | Discovery retained explicitly. No generic builder, native/lifecycle rendering, or runtime qualification; preserve unknown owners or refuse the edit. |
| U08 | S7 DB mapping and relocation | DISCOVERED_UNQUALIFIED | `opaque retention and unsupported-operation refusal only` | `test_contracts.ContractTests.test_unimplemented_runtime_families_have_no_generic_builder` | Discovery retained explicitly. No generic builder, native/lifecycle rendering, or runtime qualification; preserve unknown owners or refuse the edit. |
| U09 | SVG icon rasterization and custom process assets | DISCOVERED_UNQUALIFIED | `opaque retention and unsupported-operation refusal only` | `test_contracts.ContractTests.test_unimplemented_runtime_families_have_no_generic_builder` | Discovery retained explicitly. No generic builder, native/lifecycle rendering, or runtime qualification; preserve unknown owners or refuse the edit. |

## Legacy tool disposition

| Historical intent | Replacement | Disposition |
|---|---|---|
| `open_project` | `open_project` | MAPPED_STDIO_DISCOVERY_VERIFIED; Immutable hash-pinned source/profile. |
| `list_screens` | `inspect: screens` | MAPPED_STDIO_DISCOVERY_VERIFIED; Actual screen identity. |
| `layout` | `inspect: layout` | MAPPED_STDIO_DISCOVERY_VERIFIED; Source geometry/order. |
| `element` | `inspect: element` | MAPPED_STDIO_DISCOVERY_VERIFIED; Page ID plus screen-local identity. |
| `find` | `inspect: find` | MAPPED_STDIO_DISCOVERY_VERIFIED; Read-only text search. |
| `addresses` | `inspect: addresses` | MAPPED_STDIO_DISCOVERY_VERIFIED; All owners and roles. |
| `macros` | `inspect: macros` | MAPPED_STDIO_DISCOVERY_VERIFIED; Counted records; runtime unqualified. |
| `alarms` | `inspect: alarms` | PRESERVED_ONLY_DISCOVERY; Discovery/preserved-only raw record inventory; no alarm/history engine. |
| `set_property` | `plan_changes: set_property` | MAPPED_STDIO_DISCOVERY_VERIFIED; Qualified existing visual fields only. |
| `set_text` | `plan_changes: set_text` | MAPPED_STDIO_DISCOVERY_VERIFIED; Counted Unicode caption/description. |
| `rebind` | `plan_changes: rebind` | MAPPED_STDIO_DISCOVERY_VERIFIED; Exact owner/address/type/access. |
| `pending_changes` | `diff` | MAPPED_STDIO_DISCOVERY_VERIFIED; Read exact pending/applied diff state; no source mutation. |
| `save` | `save_as` | MAPPED_STDIO_DISCOVERY_VERIFIED; New-only authorized output plus reread/diff. |
| `screenshot_text` | `inspect: text` | MAPPED_STDIO_DISCOVERY_VERIFIED; Coordinate text projection, not screenshot. |
| `clone_element` | `plan_changes: clone_element` | MAPPED_STDIO_DISCOVERY_VERIFIED; Pinned donor and explicit inherited fields. |
| `clone_screen` | `plan_changes: clone_screen` | MAPPED_STDIO_DISCOVERY_VERIFIED; Pinned frame/full page and reference checks. |
| `delete_element` | `plan_changes: delete_element` | MAPPED_STDIO_DISCOVERY_VERIFIED; Exact nonnegative identity. |
| `set_state_text` | `plan_changes: set_text + state_value` | MAPPED_STDIO_DISCOVERY_VERIFIED; Actual state Value, not list index. |
| `editor_windows` | None | INTENTIONALLY_EXCLUDED; Editor/Computer Use operations are outside file-only authorization. |
| `close_in_editor` | None | INTENTIONALLY_EXCLUDED; Editor/Computer Use operations are outside file-only authorization. |
| `open_in_editor` | None | INTENTIONALLY_EXCLUDED; Editor/Computer Use operations are outside file-only authorization. |
| `reload_in_editor` | None | INTENTIONALLY_EXCLUDED; Editor/Computer Use operations are outside file-only authorization. |

Excluded save options: `overwrite_source`, `reload_editor`. `save_as` creates a new output after exact authorization and saved reread; it never overwrites source or an existing output.

## Native revision history

Historical PASS claims never automatically qualify current bytes or this new implementation.

- **N002** (`history-n002-manifest`): Main-page file pilot with native owners. Schema-derived types, tag import and missing gates remained unqualified; file/model checks were not panel acceptance.
- **N003** (`history-n003-manifest`): Seven-page operator reconstruction. Visual PASS withdrawn after background/layer defects; button enum assumptions later withdrawn too.
- **N004** (`history-n004-manifest`): Text-free DIB/background and actual state/layer preview. Numeric limits and button behavior defects remained separate open issues.
- **N005** (`history-n005-manifest`): Diagnostic numeric limits: one999upper-limit change reduced13reported errors to12; no safe physical-range, full fit or generic TIME acceptance.
- **N006-buttons** (`history-n006-buttons-manifest`): Source witnesses corrected momentary1.3/maintained1.4. TIME card temporarily removed without changing original TIME XML; mode writes non-atomic.
- **N006-time-interface** (`history-n006-time-interface-manifest`): Separate source-level millisecond interface branch. Source-backed candidate, not a new generic PLC bridge or vendor export.
- **N007** (`history-n007-manifest`): Four time-card owners restored onto corrected buttons; real helper leaves added, original TIME and surviving object/XML bytes retained.
- **N008** (`history-n008-manifest`): Startup/heartbeat and draft/readback proposal. Shared-draft race candidate rejected; macro acceptance later withdrawn and globals rolled back.
- **N009** (`history-n009-manifest`): Vendor-resaved initial/clock preserved; three button parsed operands changed. Five programs/40records roundtripped; no live write/cadence proof.
- **N010** (`history-n010-manifest`): Visible source plus parsed Application rewrite failed with five Error109. Acceptance withdrawn; failed archive and later delivery-location bytes differ.
- **N011** (`history-n011-manifest`): Field0 retained and29parsed operands qualified. Human CompilePASS lacked exact compiled-native linkage; live Error7/HB0/stale bare descriptors remained, final STOP. MeMeCode-only explanation withdrawn.
- **N012** (`history-n012-manifest`): Only Initial/Clock cleared, three BeforeExec retained. PLC pairing/rearm/live acceptance open. Reviewed archive passes9negatives; other copy fails whole-section drift.
- **N013** (`history-n013-manifest`): Sixteen buttons/32fields rebound to command inputs; physical/status fields remained Read. Request is not motion. Reviewed archive passes11negatives; other copy fails whole-payload reverse.
- **N014** (`history-n014-manifest`): Readonly current fault/home/drive roles. No history/ACK/reset engine, reliable mode transaction or transport-cache suppression; active code0possible.
- **N015** (`history-n015-manifest`): Simplified layout and passive code reference replaced corrupted sparse mappings; raw codes retained. Text simplification does not authorize style flattening.
- **N016** (`history-n016-manifest`): Exact style-only transfer with sequential aesthetic reviews/preservation negatives. Unproved gradient/radius/DPI/native pixels and runtime remain unqualified.

## Planning history and generic intent

The ignored root-collected record contains109turns across11pages and declares complete collection. The document author filtered39HMI-focused user messages; machine PLC narrative is excluded from reusable implementation. The record's neutral ID/hash is `planning-conversation-109-turns`.

- Coordinate native file MCP work with separate manual vendor import/compile acceptance.
- Clearly distinguish input/display, request/readback and physical feedback.
- Readable labels and separate units; value range, width, gain and digit-fit matter.
- Large hit areas and consistent grids; do not fill blank space with invented controls.
- Canonical CSV is a technical ledger, not a vendor import file.
- Missing tags/counters stay disabled; no fictional polling counters.
- Momentary JOG and maintained toggles require explicit behavioral intent.
- Preview is not native fidelity; preserve controlled revisions and retractions.

The hashed design-document chain provides additional context:

- **R010** (`design-r010-readme`): Canonical object/tag/migration ledger and measured layout; simulated transaction model. Unique-tag and object counts differ; design references are not a compiled native project.
- **R011** (`design-r011-readme`): Recipe/motor/service consolidation and clear input/display distinction. Draft/apply differs from readback; analog/reserved channels stay explicit.
- **R012** (`design-r012-readme`): Simplified ramps/service hierarchy. Local drafts need a real dispatcher/readback contract; unsupported browser/native writes refuse.
- **R013** (`design-r013-readme`): Unavailable counters/full servo feedback/first-fault latch remain missing or disabled. No invented polling counters or alternative feedback; full acceptance withheld.

Request, readback, permit, drive ACK, cached freshness and physical feedback are separate roles. No fabricated counters, heartbeat runtime, driver dispatcher, native alarm history or safe-restart controller is supplied. Final root review must reconcile tests/selectors or retain an explicit unqualified/refusal disposition.


## Final execution evidence

All mapped concrete test targets exist and passed offline. A refusal/contract test passing does not implement an unsupported feature; support levels in the table retain that distinction. The historical0.1.0suite ran136tests:135passed and one real-OS symlink privilege case was skipped; the reparse branch was separately tested without OS link privileges. See TEST_RESULTS, BUILD_VERIFICATION and the independent FINAL_REVIEW reports for exact evidence. Python3.11 syntax was checked; runtime execution used Python3.14.

Private qualification covered20hash-pinned candidates spanning every requested revision, including both N006 branches and N010/N011.19passed their requested no-op/in-memory inverse checks; N008-candidate-1 stopped because an Element lacks nPartsID. It is not safe to infer an identity. Historical visual/compile/runtime failures remain withdrawn.

## 0.1.1 patch evidence

DIA-R2 withdraws the old pre-application preview claim. `preview(plan_sha256=...)` and `validate(plan_sha256=...)` select the exact pending candidate and derived profile without changing session or disk state. Omission selects current; stale, unknown, changed and applied proposals are rejected. The dedicated 12-test regression suite passed; final complete-suite/build evidence is recorded in the version-qualified reports.

All18retained legacy names are verified by the dedicated real-stdio discovery test;17mapped rows no longer carry stale pending labels. The alarms row remains preserved/discovery-only. Discovery does not implement alarm history, runtime behavior or other unqualified functionality.

The final0.1.1suite ran148tests:147passed, one host symlink-privilege skip, zero failures/errors. All mapped test targets and18legacy discovery names are verified by this version-qualified run; source-bound, contract-only, refusal and unqualified levels are unchanged.


## Gauge source patch0.4.2

See [gauge readback and fresh source profiles](GAUGE_SOURCE_PROFILE.md). Complete source indexing, read-only fresh profile proposals, source-retained login copies and dependency-checked readonly deletion are covered by eight neutral regressions. Gauge bytes remain preserved-only. Vendor/native pixel/runtime acceptance remains separate.


## State lookup extension0.4.3

[Source-qualified state lookup](STATE_LOOKUP.md) supports explicit readonly positive enum text with three languages, exact donor pins and separate WORD16 role validation. General type conversion and DWORD mask decoding remain unsupported. Five neutral regression methods cover positive/negative and durable save paths.


## Dense ordinal correction0.4.4

Sparse State.Value writer support is withdrawn after a manufacturer-resaved source normalized indices. [State lookup](STATE_LOOKUP.md) now separates actual produced PLC codes from explicit dense display coverage and validates source text maps without rewriting or adopting profile markers. Runtime/default behavior outside the view remains unqualified.


Fixed TRUE/FALSE bit actions remain unqualified without an observed SET/RESET source donor. A maintained toggle, momentary control or INT constant button is not an equivalent fixed BOOL write. No new native opcode is inferred.
