# Observed native format and preservation contract

This document describes the bounded format observations implemented by this package. It is not a complete vendor file specification. Unknown constructs remain opaque; a successful parse or offline preview is not vendor acceptance.

## Container

The accepted family has a BMP-like prefix beginning `BM` and the family marker `PDAB` at bytes 6–9. The thumbnail boundary is `54 + uint32_le(file[34:38])`. A single bounded gzip member follows. Its decoded bytes are XORed with decimal 100.

The resulting data has a 41-byte binary prefix followed by `[Application]\r\n`. The index exposes the Application stream as `Project.file.payload`; the preceding 41 bytes are held separately. The reader does not infer this layout from `.dpa` alone and rejects foreign DOP-B/DPS envelopes.

A no-op save returns the original container bytes. An edited save retains the thumbnail and opaque prefix. A length-changing edit updates the observed coupled prefix length only when the source's declared length already matches its payload. It does not guess an unknown prefix layout. Recompression may change gzip bytes; candidate payload equality, full inverse and preservation of controlled/opaque spans are the relevant checks. Exact compressed-file equality is reserved for no-op output.

## Indexed stream

The stream uses CRLF-framed headers and scalar records, but it is not ordinary INI text. Counted blobs can contain newlines, apparent section headers, equals signs, NULs and arbitrary bytes. Splitting the whole payload on CRLF or searching for the first matching header cannot establish ownership.

Tokens retain their exact byte intervals, raw content, kind and optional blob interval. A unique scalar field can be retrieved or changed only through an explicitly qualified operation. Duplicate field keys are ambiguous. Raw data and coupled length fields are not generic editable properties.

Observed coupled fields include:

| Field class | Representation |
|---|---|
| `w…Len…` and qualified text-length fields | Decimal byte count, followed by counted UTF-16LE and its native framing |
| Nonempty counted text | Even byte count including the terminal UTF-16 NUL; strict Unicode decoding |
| `…MacroLen…` | Decimal byte count; the macro blob includes its final CRLF |
| `MeMeCode` | Inline uint32 little-endian length followed by opaque bytes and CRLF |
| Palette/point/recipe arrays | Coupled counts and observed element widths; never independently editable length scalars |

The source's raw bytes remain authoritative. Counted-length truncation, malformed terminators and unsupported ownership stop the affected operation. An unrecognized outer grammar is not silently treated as an understood blob.

## Pages, elements and states

Observed ownership follows this sequence:

```text
[Screen]
[AuxKeyElement] …
[Element]
[State] …
[Element]
[State] …
[Screen] …
```

A page uses `[Screen].ID`; its name is the counted `wTextLen` field. Panel/page dimensions include `PanelResWidth`, `PanelResHeight`, `DocSizeX`, `DocSizeY`, `PanelSizeX` and `PanelSizeY`. `DefaultScreen` is a reference, not a page count.

An element uses screen-local `nPartsID`. Its counted description/name is `wDescTextLen0`, with qualified alternate-language fields handled explicitly. An element index is its current order, not a stable identity. Negative indexes are never accepted as identities. Type is the pair `Type`/`SubType`; geometry is `X`, `Y`, `Width`, `Height`.

The contiguous State sections after an Element belong to that element. `Value` identifies a state; list position is not its value. Captions use `wTextLen0` or an explicitly selected language field. Duplicate state values are rejected. Element and state blocks move or delete together so that z-order and ownership remain coupled.

Observed fixtures do not provide a mandatory global ScreenCount, ElementCount or StateCount field. Counts are derived from qualified sections. Fields such as `SaveScrCount` and `PrintScrCount` have other meanings and must not be repurposed.

Donor cloning preserves unmodified donor bytes and requires separately pinned donor identity, a fresh destination identity/name and explicit handling of inherited bindings/macros. A page frame/aux clone is different from cloning all page content; full `content='all'` requires explicit binding and macro retention acknowledgements. Cross-file donors require byte-equal Background, Picture and DIATag banks under the current contract. Resource-bank copy/remapping is not supplied. Neither operation synthesizes an arbitrary vendor object schema.

## Types, bindings and symbols

The source corpus established raw `1.3` Momentary, `1.4` Maintained and `1.7` SetValue behavior classifications. Earlier contradictory classifications were withdrawn. No general raw `1.1`/`1.2` SetOn/SetOff classification is inferred. A macro BITON/BITOFF record is not proof of a UI button subtype.

Navigation uses coupled `GoToScreenID` and `GoToScreenName`. Live navigation references must resolve after structural edits.

Object addresses use the qualified form `DIA_TAG@{LinkName}0.Symbol.Path`; the selected link/station and role are checked against the profile and published XML. `ReadVar`, `VisibleVar`, `InterLockVar` and `TriggerVar` require read access; `WriteVar` requires write access. Command readback is not physical feedback.

Symbolconfiguration XML retains its original bytes. The resolver walks `TypeSimple`, `TypeArray`, STRUCT and enum references; array bounds are inclusive and access rights intersect ancestors/members. `size`, `nativesize`, byte offsets, bit offsets and alignment gaps are distinct metadata. Missing layout data is not an invitation to calculate a packed structure. Multidimensional physical stride remains unqualified where the export does not establish it.

Numeric storage maps such as `MemLen`/`MemFmt` are profile-qualified facts, not universal values derived from width alone. Explicit decimal limits receive bounded literal, type-domain and declared-digit checks against the bound symbol. Scale and offset require an explicit caller-qualified contract; they do not establish visual fidelity. Rounded display extents and decimal representability must be qualified separately from raw type limits. Scientific notation/nonfinite edits and silent TIME-to-UDINT coercion are refused. A real PLC millisecond interface must exist before a TIME-related interface can be bound; the package does not create PLC logic.

## Opaque suffix and reviewed boundaries

After the editable screen stream, global/resource content is retained as an opaque suffix. The safe resource reader walks only its qualified ASCII/count-framed grammar and skips entire counted owners. It does not use regex hits inside Picture/XML/other blobs as proof of top-level sections.

Known selected resources include `[Picture] Size`, `[Background] Size`, and `[DIATag] size`. DIATag metadata remains separate from its raw XML span. A replacement is a coupled counted-resource patch; unrelated metadata and suffix bytes remain unchanged.

Some legacy suffixes contain outer binary grammars that are not covered by the sequential walker. Such input stops with an ownership error. A caller may provide separately reviewed boundaries tied to the exact payload hash:

```json
{
  "reviewed_boundary_ack": true,
  "source_payload_sha256": "<exact payload SHA-256>",
  "frames": [
    {
      "section": "Background",
      "header_start": 0,
      "header_sha256": "<exact header SHA-256>",
      "blob_sha256": "<exact blob SHA-256>"
    }
  ]
}
```

The zero offset is illustrative and will not qualify an actual suffix. Do not generate reviewed boundaries by automatically approving search hits. The record acknowledges caller-reviewed ownership, not a complete schema or vendor proof. Overlapping/nested reviewed resources are rejected. Editable-index acknowledgement similarly pins the exact digest reported by inspection; it does not grant arbitrary-property access.

## Macro and compiled observations

The bounded native macro profile begins `02 52 45 56` (`02REV`). Each instruction contains four opcode bytes, five `uint32_le length + raw field` values, and its observed 14-byte tail. `MacroLen` is a byte count. Statement/CRLF splitting is insufficient.

Visible field0, object address syntax and parsed operand fields have different roles. A parsed-operand edit does not globally normalize source text. Unknown encodings/opcodes/flags stop operand edits or donor insertion. Explicitly clearing an exact hash-pinned slot is a separate operation and need not interpret the removed instructions. Exact parsing and byte roundtrip do not prove macro scheduling, successful target writes or heartbeat cadence.

Compiled inspection is a bounded signature observation with exact artifact/source/candidate identities and a caller-linked receipt. It may report only partial BOOL descriptors from a raw or qualified compressed observation. It does not compile, rebuild, confirm provenance independently, or establish full compiled-format/runtime acceptance.

## Preview model

`flat-v1` reads the saved background, saved object order and actual state values. A background frame is a 40-byte BITMAPINFOHEADER plus its exact padded pixel extent. The per-page SHA covers that entire frame, including header and native row padding, excluding later resource bytes. A frame selected for the wrong page is rejected even if it is a valid image.

The decoder covers 24/32-bit uncompressed BI_RGB, positive bottom-up and negative top-down height, BGR/BGRX channels and row stride. BI_RGB32's fourth byte is not treated as established alpha. SVG embeds a standard-library-encoded PNG and escapes native text.

Only explicitly modeled Style0 flat surfaces and Style3 transparency are used. Unknown image references, dynamic visibility/position effects, nonflat gradients, radius controls, font ratio changes or unqualified font properties raise `UNSUPPORTED_RENDER`. The model does not establish vendor borders, highlight/shadow behavior, DPI, transparency fidelity or keypad behavior.

Optional caller-supplied SFNT bytes provide bounded Unicode cmap4/cmap12 glyph checks and horizontal advance estimates. No installed font path is searched. Fonts absent from the caller's byte map remain unverified; a declaration of an unknown font name alone does not qualify it. Missing glyphs, estimated overflow and opaque text occlusion are rejected when the supplied metrics support those checks. Shaping, kerning, hinting and vendor rasterization are not established by these estimates.

Every result remains `OFFLINE_MODEL_ONLY`. Gallery OFF/ON/minimum/maximum-long/negative cases are independent synthetic examples, not simultaneous process-valid PLC states.

Numeric synthetic values are formatted directly. The preview does not apply saved `GainValue`/`OffsetValue` scaling, so a scaled numeric display requires a separately qualified model before visual fidelity can be assessed.
