# Qualified external templates and references

The file MCP contains no native seed, vendor installation, customer project or
machine catalog. Host configuration may set `DIA_HMI_TEMPLATE_ROOT` to an external
directory containing `catalog.json`. The default is an empty, unavailable catalog.
The gateway forwards this variable from the trusted host environment; tool/job
arguments cannot supply it. Catalog roots and workspace/effect roots must be
disjoint. Every file uses bounded immutable reads and rejects links/hardlinks.

`catalog.json` has exactly `schema` (`delta.hmi.template-catalog.v1`), `templates`
and `transitions`. A template entry has exactly:

| Field | Contract |
|---|---|
| `id` | Unique bounded alphanumeric, underscore or hyphen identifier |
| `seed`, `profile`, `review` | Each `{path, sha256}`; normalized relative path, exact raw-file SHA256 |
| `target` | `{family, model, editor_version, width, height}` matching the actual native model and profile |
| `qualification` | `{decoder, operations}`; decoder `DIASCREEN_PDAB_COUNTED_V1`; operations are an explicit subset of `template_copy`, `neutral_page`, `target_transition`, including `template_copy` |

A transition is exactly `{from, to}`, referring to two registered different IDs.
It authorizes selecting another blank template, **not converting a machine
project to another panel model**. Native address/communication conversion is not
implemented by this operation.

The external review JSON has exactly these fields:

- `schema`: `delta.hmi.template-review.v1`;
- `template_id`, `seed_sha256`, `profile_sha256` (raw file), `target_sha256`;
- `descriptor_sha256`: canonical SHA256 of `{template_id, target, qualification}`;
- `coverage`: exact SHA256 for `preamble`, `page`, `tail`, `thumbnail`, `prefix`;
- `origin`: `OWNED_NEUTRAL_VENDOR_PROJECT` or `ORIGINAL_SYNTHETIC_OFFLINE_FIXTURE`;
- `reuse_rights`: `AUTHORIZED_LOCAL_TEMPLATE_REUSE`;
- `reviewer`: nonempty independent review identity;
- `auth_review`: `NO_CUSTOMER_CREDENTIALS_OR_PROJECT_CONTENT`;
- `opaque_review`: `EXACT_OWNERS_REVIEWED_NO_CUSTOMER_ASSETS`;
- `status`: `PASS`.

Canonical JSON means sorted keys, compact separators, UTF8, finite numbers, no
ASCII escaping. Raw-file SHA and canonical-profile SHA are different identities.
Coverage partitions all native seed owners; the prefix includes the counted
payload length. A single empty page is necessary but insufficient: inert global
macros, authorization data and opaque resource owners need exact independent
review. The loader rejects indexed executable macros and incomplete framing even
with a host receipt. A receipt is a trusted-host assertion, not cryptographic
proof of independent review or permission to redistribute seed bytes. Synthetic
tests remain offline fixtures; they never establish vendor or panel acceptance.

## Session and copy lifecycle

1. `inspect_template(template_id)` returns the profile, target, scope and seed,
   profile, catalog, review and engine identities without a project session.
2. `create_project` requires explicit seed/profile/catalog/engine pins and a new
   workspace-relative `.dpa` path. In the gateway it starts an isolated backend
   process and returns `session_id` with a durable proposal. No native file is
   created yet.
3. `inspect_native_plan` reads this exact proposal and exposes its durable
   operation state. `apply_project_plan` requires write authority, inspection and
   approval naming the immutable plan hash. It copies verified seed bytes with
   new-only creation, rereads them and opens the copy as the source in that same
   session, using the **catalog-owned** profile. No vendor API is invoked.
4. `inspect`, edit proposals, exact approval and `save_as` follow the existing
   contract. Saved outputs are separate files. Identical seed copies at different
   source paths have separate plan identities. Workspace-relative source identity
   survives moving the whole workspace; external read roots remain explicit.

A post-write interruption remains `UNKNOWN_OUTCOME`. Repeat `create_project`
with the same pins/path to discover the existing proposal in a fresh isolated
session; this does not copy again. Inspect the plan, then reconcile its operation.
Recovery inspects only the existing exact effect and never retries native writes.
A proven copy can attach as source to an empty session through a read-only open.
Another loaded project's state is left untouched. A PREPARED intent alone or a
pre-existing same-byte file does not establish a successful owned copy.

`configure_target` accepts only an inspected, unchanged registered blank, an
explicit registered transition and a separate new path. A subsequent edit or
pending native plan invalidates application of that transition proposal.

## Neutral frames and resource inspection

`create_neutral_screen` derives the exact reviewed stock page. Only ID, name,
title and background color may change. It uses the common durable native-plan
journal, inverse ledger and resource-boundary remapping. Preamble, thumbnail,
prefix ancestry, auxiliary records and opaque tail remain exact. Seed/profile/
catalog/review/engine pins are rechecked during reconstruction, application,
save and recovery. The 128-page neutral-frame limit does not change the ordinary
native transaction limit of 96. This route adds zero widgets.

`inspect_native_resource_banks` exposes the existing closed DOP-107EV/native
6.6.2.48 decoder. It needs a matching source, not a template catalog. Unsupported
framing or opaque variants refuse; bank ownership is not semantic support for
alarm/history/tag writers. Its synthetic positive parser test substitutes a
test-only opaque sentinel hash; the production decoder variant remains unchanged.

`DIA_HMI_REFERENCE_ROOT` separately provides an optional `registry.json` with
versioned reference source/profile/parameter/contract file pins. Catalog reads
are stateless. `open_delivery` starts a new isolated backend session, stages an
immutable source copy only with write authority, and preserves reference bytes.
These catalogs remain host-private and are excluded from every distribution.
