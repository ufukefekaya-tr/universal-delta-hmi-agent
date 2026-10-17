# Corrective evidence and withdrawn assumptions

Historical claims and their retractions remain in SUPPORT_MATRIX/REGRESSIONS. They are not promoted by a successful new test. This extraction produced the following independent findings and fixes:

| Trigger / evidence | Effect | Correction | Retest |
|---|---|---|---|
| Unknown `FutureBlobLen` carried a fake Screen header and accepted a geometry edit | Opaque bytes could acquire editable ownership | Stop on unqualified framing; pin reviewed indexed boundaries; explicitly frame observed preamble data | `test_future_counted_owner_is_not_editable_screen`, qualification preamble tests |
| Known macro opcode accepted an unrelated empty operand slot | An address outside the selected link/type/access could enter a candidate | Require opcode/field/kind/role/type evidence and the associated XML catalog | `test_macro_slot_type_access_and_visible_source` |
| XML update skipped auxiliary/trigger/macro dependencies | A referenced symbol could disappear | Inventory all indexed owners; validate known dependencies; refuse unknown roles/semantics | `test_xml_unknown_address_dependency_blocks_removal` |
| Arbitrary Style/font flag enum and donor frame inheritance passed | Unobserved rendering or inherited behavior could be introduced | Qualified enum sets; explicit frame binding/macro acknowledgment; equal cross-file dependency banks | enum/frame/donor negative tests |
| Same-name symbol was retyped, or an existing node redirected to a new UDT | Access-only validation concealed a changed control type | Preserve existing node/type/member/array metadata and types; allow genuinely additive definitions | direct-type, alternate-anchor and explicit-shadow tests |
| Another DIATag index supplied RW metadata; partial foreign metadata could be overridden | A different target's permission could authorize the binding | Bind catalog metadata to the selected link/station; reviewed mapping may fill missing fields without contradictions | catalog and partial-metadata negative tests |
| Returned plan/diff nested values aliased internal records | Review evidence could drift while candidate bytes stayed fixed | Deep-copy views; hash record, candidate, derived profile and patch ledger; recheck before apply/validate | returned-plan, stored-proposal and profile-drift tests |
| Decimal limit 9.99 with zero decimals could round into an extra digit | A raw-digit check could overstate display suitability | Require exact decimal representability; keep font-fit and scale fidelity separate | typed numeric negative cases |
| Build left generated metadata inside the public source selection | Package membership check stopped | Keep strict membership checking; relocate generated metadata after building and before release freeze | release membership and wheel/sdist inspection |
| DIA-R2: 0.1.0 preview/validate selected current bytes despite the pre-application review workflow claim | A review could inspect the old candidate rather than the pending proposal | Withdraw that claim; select exact immutable pending plan bytes and derived profile read-only, return view/plan/candidate/profile identities, reject stale/drifted/applied selections | `test_plan_review.PlanReviewTests.test_proposal_caption_sha_and_readonly_state`; `test_plan_review.PlanReviewTests.test_gallery_uses_proposed_background_profile`; `test_plan_review.PlanReviewTests.test_stdio_readonly_proposal_review_and_discovery_schemas` |
| D04: coordinate-ordered text/layout was advertised without an explicit sort selector | Native layer order could be mistaken for spatial reading order | Keep layer order as default; add layout/text coordinate projection in native page order, then Y, X and layer index; preserve renderer order | `test_plan_review.PlanReviewTests.test_coordinate_layout_text_order_preserves_render_layers`; `test_plan_review.PlanReviewTests.test_sort_invalid_or_unrelated_views_refused` |

One orchestrator action guard failed on expected parallel membership changes and an already-authorized native edit was nevertheless applied. This was a process defect, not a successful guard. The exact scope/bytes were reviewed, and subsequent tool batches explicitly aborted on nonzero guard results before mutation. Later guard failures stopped without edits. The checkpoint records both the incident and correction.

Private qualification examined twenty hash-pinned historical candidates. Nineteen passed their requested no-op or in-memory visual inverse checks. One earlier candidate lacked `nPartsID` for an Element and remained STOP; no identity was invented. Successful no-op parsing does not withdraw historical visual, macro, compilation or runtime failures.

Original-code licensing is Apache-2.0. The unlicensed upstream implementation and private native/XML/font assets remain excluded. No GUI, vendor compile, PLC connection, target operation or remote push was used.


The 0.1.1 correction does not rewrite original 0.1.0 packages or reports. They remain historical evidence, not current release acceptance. Final 0.1.1 test/build/review reports must identify the changed tree and package bytes.
