# Architecture and frozen module boundaries

The implementation is original. Format facts were extracted from private historical files and an independently authored reader. Unlicensed upstream Python is not copied or imported. The nine common tools are an interface, not a reduction of historical scope.

| Owner/module | Responsibility |
|---|---|
| Root: native.py | Bounded PDAB container, immutable byte spans, sections, screen-local identities, exact patch ledger and full inverse |
| Root: resources.py | Explicit counted XML/background resources, existing metadata retention, flat DIB append |
| Root: operations.py | Typed existing-field edits, donor/block operations, navigation and binding checks |
| Binding implementer: symbols.py/macros.py | Original XML type/access resolver and bounded five-field macro records; conservative compiled inspection |
| Preview implementer: preview.py | Saved-layer SVG, actual DIB, state fixtures, optional font metrics/cmap and unsupported-effect refusal |
| Root: session.py/cli.py | Isolated workspace, profile/source hashes, read/plan/authorize/apply/new-only-save/diff/rollback and JSON-RPC stdio |

`Project(bytes)` exposes `file.payload`, `index`, `app`, and `pages`. Page identity is `[Screen].ID`; element identity is screen-local `nPartsID`, never a negative list index. `index.scalar/number/text(section,key,default)` retrieves a unique field. Tokens retain exact start/end/raw spans. States belong to the preceding element. Unknown resource suffix bytes are retained as one opaque interval except explicitly decoded counted resources.

The profile has `schema_version`, family `diascreen-dop100`, `panel:{width,height}`, allowed `application_versions`, explicit `preview_model:'flat-v1'`, per-page `background_sha256`, optional workspace-relative font paths with hashes, and source-qualified type/numeric contracts. A profile is hashed and never silently inferred from a file extension. All tools reject DOP-B/DPS envelopes.

Symbols API: `parse_symbols(bytes)` returns a catalog with `raw`, `sha256`, `resolve(path)` and `inventory()`. Resolve retains XML offsets and distinct size/nativesize; permissions intersect ancestors and members. Binding addresses, macro display source, and parsed operands are different grammars.

Macro API: `parse_macro(bytes)` returns instructions, their original five byte fields and tails, and exact `to_bytes()`. Parsed-operand edits preserve visible field0. No general macro compiler, heartbeat runtime, or atomic mode controller is supplied.

Preview API: `render_preview(project, profile, values=None, fonts=None)` and `render_gallery(project, profile, fonts=None)` return SVG with an explicit offline level. Fonts are optional caller-supplied byte assets, never fixed PC paths. Missing metrics cannot yield a fit PASS; unsupported effects cannot yield a fidelity claim.

The orchestrator alone writes checkpoints and holds stage/commit ownership. Module writers receive disjoint paths and a short exclusive commit lease after their tests; integration and final adversarial audit occur afterwards. No process contacts a PLC or opens a vendor application.
