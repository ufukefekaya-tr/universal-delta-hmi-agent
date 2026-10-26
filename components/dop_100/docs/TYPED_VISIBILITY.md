# Typed readonly visibility0.4.5

`plan_native_update` accepts an optional `visibility` on `edit_element`, `bind_element`, `clone_element`, `replace_element`, `move_element`, and `numeric_display`. It operates only on existing macro-free readonly numeric Type5/SubType1 and static Type10/SubType6 owners in the observed DOP-107EV800x480/native6.6.2.48 format. The source must already contain a readonly numeric owner using direct PLC BOOL visibility on native link2.

```json
{"address":"M100","type":"BOOL","access":"READ_ONLY","link":"Link1","station":0,"visible_when":true}
```

The hash-bound contract must declare that M address as BOOL/words0/READ_ONLY. Link and station must match the reviewed native source. No raw native fields are exposed. Only existing VisibleVar and VisibleLink change; existing VisibleCondition remains exact. A true JSON boolean is required: true matches source condition0, false matches condition1. A conflicting condition is refused. Unknown or indirect variants, writers, macro-bearing owners, unsupported families and missing direct-source witnesses are refused.

For a valid-number/invalid-dash pair, clone or edit an existing condition0 numeric display and condition1 static dash in the same exact plan, use the same BOOL address and opposite visible_when values. Rebind the numeric data address separately with its unchanged REAL/INT/DINT contract. Reuse the actual source dash text/style. The complementary pair retains the source intent for valid/invalid display; no healthy-zero fallback is inserted. This source condition preservation test does not observe manufacturer runtime TRUE/FALSE behavior.

`validate_bindings` audits VisibleVar as READ_ONLY_BOOL_VISIBILITY independently of ReadVar/WriteVar native IEC typing. `require_all` counts a declared visibility-only address. A valid BOOL role cannot conceal a wrong numeric type. Plan proof includes exact source witness identities; candidate readback checks the typed address/link/station/truth condition after native re-encoding. Exact approval, new-only save, drift/replay refusal and source/application/auth/global macro/resource preservation remain in force.

This is source-bound file functionality. Manufacturer compile, pixels and runtime behavior remain separate acceptance stages. The tests use original neutral fixtures; no customer native data, actual PLC addresses or credentials are distributed.

Existing visibility on other source families is listed separately as `preserved_visibility` with PRESERVED_ONLY. It receives no matched-address/require_all acceptance credit, and cannot widen the writer scope. Existing ReadVar/WriteVar contract audits retain their own checks. This keeps a preserved historical control from being incorrectly treated as a failed request for the new numeric/static visibility writer.
