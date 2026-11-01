# MCP consolidation 0.4.0 / DIAScreen 0.5.0

The umbrella exposes the unchanged DOP-B 0.2.1 file/job backend and 83 DIAScreen
routes, plus the gateway's project-session closer. The family backends remain
separate. No customer data, vendor seed or machine builder is bundled.

The thirteen additions and source-to-test mapping are in
[the migration ledger](HMI_SKILL_MIGRATION.json). See
[external template and reference contracts](TEMPLATE_CATALOG.md) for the exact
host qualification, plan-only creation, copy, session and recovery lifecycle.

## Deliberate risk closures

- Legacy and native deletion share one conservative dependency guard. Its proven
  subset contains only wholly indexed inert metadata, empty auxiliary slots and
  known readonly labels/indicators with no executable macros, active events,
  object/group references, opaque blobs or resource payload. Unknown keys and
  families refuse. The old deletion PASS on opaque synthetic sources is withdrawn.
  There is no job-supplied bypass or generic model-wide deletion qualification.
- `colors.foreground` writes `FgColor` only. A full flat foreground fill requires
  explicitly planning all seven `FgFillColor`, `FgFillEndColor` and
  `FgFillStopColor0..4` owners. Gradient type/angle fields remain unchanged.
- Creation, native saves, offline packages and contract provenance rebinds retain
  interrupted effects as `UNKNOWN_OUTCOME`. Recovery reads existing exact effects;
  it never retries writes. Missing/partial outputs stay unknown. A PREPARED intent
  or a lost exclusive-create race cannot become successful ownership evidence.
  The journal records the successful exclusive-open descriptor before writing,
  then binds completed file identity, length and SHA after flush/fsync. An
  unclaimed RUNNING intent, incomplete claim or recreated same-byte file cannot
  establish success. Historical SUCCEEDED records remain historical if current
  effect verification fails. This is cooperative file integrity, not an OS
  sandbox or protection against a hostile host rewriting the journal. Stable
  filesystem identity and the shared 64 MiB reread bound are required.
- Source identity includes the workspace-relative path as well as bytes/profile,
  keeping same-seed projects separate. Rebind recovery needs the exact source,
  candidate and profile loaded; missing session context is an explicit refusal.
- Dense HMI state indices remain separate from actual produced PLC codes. No
  sparse state writer or fabricated healthy fallback is reintroduced.
- New-page object move/clone needs a subsequent inspected transaction. Navigation
  writes require an actual source navigation control and the actual target page
  name, including planned renames; dormant donor fields cannot grant behavior,
  graph reachability or alias authority.
- Full symbol shape, access, member offsets and array bounds remain audited.
  Logical TIME/64-bit validation does not imply a qualified native writer or
  permission to silently coerce the type.
- Discovery descriptions and capabilities share a support registry. Vendor IDE,
  compile, simulation, transfer and unimplemented service constructors remain
  explicit `UNSUPPORTED_NOT_IMPLEMENTED` routes. An exposed name is not a feature
  acceptance claim.

The regression suite exercises byte preservation, saved rereads, exact replay
refusals and adverse outcomes with original generated fixtures. Vendor compile,
pixel fidelity, PLC truth and physical operation remain separate, unperformed
acceptance stages. Synthetic decoder sentinel substitution is identified in its
test and never changes the production decoder's admitted opaque variant.

Goals and each goal's ordered inner workflow are tracked in
`goals/hmi-skill-transition.json`. Accepted source changes reopen affected gates;
historical receipts remain available. The companion skill cannot be authored
before the hash-bound G2 MCP acceptance gate passes.
