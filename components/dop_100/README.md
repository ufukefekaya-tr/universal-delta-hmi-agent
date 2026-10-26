Current source extension: [native service update](docs/NATIVE_SERVICE_UPDATE.md). See the current 70-tool integration inventory; historical release evidence below remains scoped to its original bytes.

# Universal DIAScreen HMI Agent

Original, portable, file-only tools for inspecting and preparing DIAScreen/DOP-100 native project copies. The backend indexes saved bytes, compiles explicit changes into an exact patch ledger, rereads candidates, and produces bounded saved-layer SVG previews.

The observed format family includes DOP-100 projects. Compatibility with every panel, editor version, widget or driver is not established. DOP-B/DPS/DOPSoft writing is outside this package. This is independent tooling, not an official vendor SDK.

## Install and start

Python 3.11 or later is required. Runtime code uses the Python standard library; no MCP SDK, image library or installed system font is required. Building/installing from source uses setuptools 77 or later.

From an isolated Python environment, install the source package without runtime dependencies:

```text
python -m pip install --no-deps --no-build-isolation .
python -c "from pathlib import Path; Path('workspace').mkdir(exist_ok=True)"
python -m universal_diascreen_hmi.cli --workspace ./workspace
```

The source installation command requires setuptools 77 or later to be available in that environment. It does not install build tools automatically. An already-built release wheel can instead be installed with `python -m pip install --no-deps <wheel-path>`. The installed console entry point is `universal-diascreen-hmi-agent`.

The process accepts newline-delimited JSON-RPC MCP messages on standard input and writes protocol responses on standard output. Use a stdio MCP client; this is not an interactive shell. It does not open a listening TCP server. Each process owns one isolated session.

Read-only is the default. To permit reviewed offline plans to be applied to an in-memory copy:

```text
python -m universal_diascreen_hmi.cli --workspace ./workspace --allow-write
```

`--read-root PATH` may be repeated to grant additional read roots. Candidate outputs remain inside the workspace and must be new files. Use source copies and a dedicated workspace.

For the complete source ZIP, installation and build tools are optional. With an existing workspace, start directly from the extracted folder:

```text
python tools/start.py --workspace ./workspace
```

This launcher discovers only the adjacent `src` directory. It uses the same CLI and stdio protocol. Add `--allow-write` only for explicitly reviewed local plans. `examples/create_demo.py` can create a fresh neutral example for offline qualification; it is not a real panel application.

## Controlled workflow

1. Prepare a profile object. Calculate the source file's byte SHA-256 and the canonical profile object's SHA-256 as specified in [integration](docs/INTEGRATION.md). A filename or extension is not a format profile.
2. Call `open_project` with workspace-relative `path`, `source_sha256`, the JSON object in `profile`, and `profile_sha256`.
3. Call `capabilities` and `inspect`. Review the saved structure, source identity, editable-index coverage and any unqualified sections.
4. Call `plan_changes` with explicit operations. Review its before/proposed values or byte summaries, owner information, change hashes, candidate identity and limitations. Native byte ledgers remain internal preservation evidence; the tool does not expose every opaque byte as a readable schema. Editing aliases also create plans; they do not apply changes implicitly.
5. Before applying, call `validate` and, when the drawing profile qualifies, `preview` with that exact `plan_sha256`. Review the proposed candidate and derived profile identities. These read-only calls also work without `--allow-write`; they leave the current candidate and pending plans unchanged.
6. With `--allow-write`, call `apply_plan` with the returned `plan_sha256` in both `plan_sha256` and `approval_sha256`. This equality records the caller's explicit local consent to that exact plan. It does not authenticate a human or prove vendor acceptance.
7. Omit `plan_sha256` to validate and preview the current candidate after application, then inspect `diff`. A proposal selector is rejected once that plan is applied.
8. Call `save_as` with a new workspace-relative path and the exact `candidate_sha256`. Review the reread/diff receipt. Existing source and output paths are never overwritten.

`rollback` discards pending candidate changes in this process. It does not modify a previously saved candidate or write back to a source. Keep the source and all release receipts separately.

Unknown byte ownership stops editing. Every edit plan requires a reviewed index pin for the exact layout reported by project inspection; complex resource suffixes may additionally need source-hash-bound reviewed resource boundaries. These are caller review records, not vendor schema or runtime proof. See [integration](docs/INTEGRATION.md) and [format](docs/FORMAT.md).

## Tools

The nine common tools are `open_project`, `capabilities`, `inspect`, `plan_changes`, `preview`, `validate`, `apply_plan`, `save_as`, and `diff`.

`inspect(view='layout', sort='coordinate')` and `inspect(view='text', sort='coordinate')` present rows in native page order, then Y, X and screen-local `layer_index`. The default `sort='layer'` preserves saved layer order. Sorting changes only the inspection projection; it does not change native bytes or preview rendering order. Legacy `layout` and `screenshot_text` accept the same selector.

Additional tools cover donor registration, rollback/pending state and conservative compiled-artifact inspection. The legacy interface remains discoverable through 18 names, with its editing aliases routed through the same plan and authorization boundary. Call `tools/list` for the installed process's complete schemas; no GUI/compile/PLC tool is supplied.

## Evidence boundaries

- Native inspection, bounded symbol/access checks, exact byte patches and synthetic tests are offline evidence.
- Previews return `OFFLINE_MODEL_ONLY`. Values are synthetic; shared-address conflicts are rejected. Missing font bytes produce `FONT_METRICS_NOT_VERIFIED`, never a font-fit PASS. Supplied SFNT bytes permit bounded glyph/advance estimates, not vendor pixels.
- Unknown image/effect/gradient/radius behavior is rejected. A profile cannot establish unsupported drawing behavior simply by declaring it.
- Source-qualified button types, numeric formats and XML metadata are not live press/release, write-success or physical-feedback acceptance.
- Compiled-artifact observation is partial and receipt-bound. It does not run a compiler, establish full compiled-format coverage or prove that a candidate was deployed.
- Heartbeat scheduling, atomic operating-mode selection, reconnect/lost-release behavior, alarm history/ACK engines and machine PLC logic are not supplied as working runtime features.

Vendor IDE opening, save/reopen, compilation, native pixel fidelity, panel/runtime and physical acceptance remain separate human checks. No Computer Use, vendor process, PLC connection, force, download or energizing is performed by this package.

## Validation and provenance

Run the neutral synthetic regression suite from the repository:

```text
python -m unittest discover -s tests -v
```

Use an environment in which the package is installed. Final test counts, exact release identities and remaining findings belong in [the final review](reports/FINAL_REVIEW.md), not in a stale README claim.

Version 0.1.1 adds exact proposal review before application and explicit coordinate-ordered inspection. The 0.1.0 pre-application preview workflow claim is withdrawn by DIA-R2: those tools selected only the current candidate. Original 0.1.0 packages and reports remain historical evidence, not acceptance of 0.1.1. See [regressions](docs/REGRESSIONS.md).

See [architecture](docs/ARCHITECTURE.md), [workflow](docs/WORKFLOW.md), [support matrix](docs/SUPPORT_MATRIX.md), [regressions](docs/REGRESSIONS.md), and [provenance](docs/PROVENANCE.md). Private native samples, paths, symbols and fonts are excluded from the package. Original distributed code is [Apache-2.0 licensed](LICENSE); see [NOTICE](NOTICE.md) for third-party and proprietary material boundaries.
