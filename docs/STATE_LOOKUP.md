# Dense indexed state text lookup —0.3.3 / DIAScreen0.4.4

A source-observed manufacturer resave renumbered a Type7/SubType1 lookup with sparse serialized State.Value values to consecutive indices, while keeping the text order. The0.4.3 sparse writer/file-test claim is withdrawn. It was never vendor/runtime qualification. The new writer and readback require the ordered list0..maximum; a matching unordered set is insufficient.

`plan_native_update`, `op="state_lookup"`, still requires immutable source/donor/owner/template hashes and a complete readonly INT/one-word contract. Without `view`, the actual produced enum must be exactly0..maximum. Sparse calls are refused with LOOKUP_DENSE_INDEXED.

For a sparse actual produced enum, supply `view={"mode":"DENSE_INDEXED","maximum":122,"unknown_texts":["Unknown code {value}","Unknown code {value}","Unknown code {value}"]}` using the actual translated strings. maximum must equal the greatest produced code and be at most127. Each template contains exactly one literal {value}; other brace expressions are refused. This is bounded plain-text replacement, not an expression evaluator.

The states list must contain every index0..maximum in order. Known produced values use caller-reviewed translated labels. At every non-produced index, the three texts must equal the declared unknown templates with the literal decimal index substituted. Each row still supplies the existing explicit sizes, alignment, bold and colors. Font names remain source-derived. Existing readonly target, donor/schema/dependency, geometry, exact approval, durable reconstruction and new-only save gates remain unchanged.

The actual PLC contract.enum is never enlarged. Proof separates produced_values, view_values and unknown_values. MemLen1/MemFmt2 is the dedicated LOOKUP_WORD16_NONNEGATIVE role; general native INT/WORD/BOOL checks remain strict. Numeric unknown labels apply only to explicitly covered holes. Values outside the view have no qualified runtime/default behavior.

A manufacturer resave may change fonts, numeric lexical forms and owner hashes and does not carry generated profile markers. Reapplying all lookups merely to restore markers is unnecessary. The existing readonly `validate_bindings` tool accepts `lookup_expectations` and its canonical SHA256 `lookup_expectations_sha256`. Each item contains page_id, element_id, expected_element_sha256, states:[{value,texts}], and optional view. Provide the complete expected ordered three-language map from the approved contract/design, not a blindly echoed source table.

The service verifies candidate, contract and expectation hashes; exact owner, readonly plain lookup schema, link/station/address, dense order, produced/view domain and every expected text. A wrong renumbered label map fails. It returns SOURCE_EXPECTATION_MATCH and profile_mutated=false. It does not adopt a profile, apply a plan, save a file or grant vendor/runtime acceptance. Unknown, duplicate and unaudited owners are refused. Original snapshot and returned candidate profiles remain separate.

Tool counts remain70generic/83project-local. No new transport, raw command endpoint, GUI/Computer Use, gauge edit, PLC source change, native Alarm-table writer or physical access is introduced. The published source contains only neutral fixtures; private before/after native files and PLC labels are not distributed.
