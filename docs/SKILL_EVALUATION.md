# Companion skill acceptance

The current results and exact evidence identities are in
[G4_BEHAVIOR.json](../reports/hmi_skill/G4_BEHAVIOR.json). This is a bounded
forward evaluation, not a statistical claim that the skill improves all agents.

Two fresh evaluators receive the same nine original synthetic tasks. The first
uses MCP and repository instructions; the second also receives the skill and
family references. They do not receive expected answers, each other's results
or the effect auditor. They discover the actual installed MCP schemas and use
real stdio processes. No production screen or vendor/panel operation is involved.

The cases cover two authorized native edits, maintained versus momentary
behavior, read-only intent, a version mismatch, stale data, an unavailable
backend, invalid consent, instruction-like source text and recovery of an
existing saved effect after response loss. A no-operation model proposal for
the stale preview is distinct from changing native content.

An independent reviewer examines every decision, including denials with no
tool call, and the complete call traces. The supplemental effect auditor checks
successful save results against actual bytes, complete native payload diffs,
outer framing, the opaque prefix and format-specific length field, source and
existing-effect SHA/mtime, operation identity and unexpected recursive native
or ZIP output. It rejects unlisted effect routes. It does not authenticate an
untrusted trace or score response wording. A response saying PASS is insufficient.

## Repeat with isolated neutral inputs

Install a clean copy as described in the root README. Start every test driver
and child Python with `-I -B`; generated import bytecode intentionally invalidates
the trusted runtime inventory. Existing environments and failed attempts must
not be silently reused or repinned.

From the clean copy's gateway interpreter, run:

```text
python -I -B tools/prepare_behavioral_cases.py <installed-repository-root>
```

This setup creates new-only `.local/eval` workspaces and four separately named
host configs under `.local`. It uses only repository-authored fixture builders
and the synthetic profile. It rejects existing outputs, linked local roots and
ambient catalog/font variables. Its direct Service calls inject the original
synthetic response-loss setup; this is not a production alternative to MCP.

Give fresh evaluators [the raw tasks](../tests/behavioral/tasks.json) and their
own isolated actor/config only. Keep the baseline blind to skill contents and
both evaluators blind to the auditor. Trace actual `call_tool:NAME` events with
case, arguments, full SDK result and exception fields. Preserve initialization,
failed attempts and a separate `trace-missing.jsonl` if the unavailable-backend
case needs its own connection. Use explicit UTF-8 when reading evidence.

After both evaluators finish, independently review decisions and run:

```text
python -B tools/check_behavioral_evidence.py <isolated-actor-directory>
```

The prepared originals and saved native files stay in private test workspaces.
Public reports contain generic outcomes and exact evidence hashes. Customer
projects, catalogs and raw machine data are never evaluation inputs or package
members. File, visual/font, vendor and physical acceptance remain separate.
