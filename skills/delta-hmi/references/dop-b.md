# DOP-B / DOPSoft 2 file workflow

Use `dop_b__capabilities(profile_id)` with a host-registered DOPSoft 2 profile,
then `dop_b__open_project(profile_id, source_path)`. A conceptual session without
a source is not a native constructor. A `.dps` extension or an imported DOP-100
conversion does not prove a B-panel target.

The nine file routes are `open_project`, `capabilities`, `inspect`,
`plan_changes`, `preview`, `validate`, `apply_plan`, `save_as`, `diff` under the
`dop_b__` prefix. Read their discovered input schemas: DOP-B uses gateway-wrapped
`session_id` and `plan_id`, not DIAScreen's plan digest argument names.

Inspect the actual source, prepare the requested design/typed contract and
operations, then call `plan_changes` with its required idempotency key. Inspect
the returned plan and preview, validate, apply under the exact design/plan
authorization returned by this backend, and save to a separate relative output.
Legacy `apply_plan` uses an `approval_path` containing the returned
`approval_contract` plus `approved: true`, issued under actual user/host
authority. Materializing already authorized local consent is different from
fabricating an independent job-review receipt; neither file grants its own
authority.
Use `diff` and reopen the saved bytes for verification. Source-qualified donor,
neutral-library and blank-program operations travel inside these tools; they
are not extra top-level DIAScreen routes. Capability evidence decides which
constructors and control families exist for the chosen profile.

Maintained, momentary, constant and navigation controls need their real source
families and retained semantics. A shape or caption cannot turn an unsupported
native control into a qualified behavior. Check read/write permission, states,
numeric limits, units, macro operands and alarm contracts against actual fields.
Sparse produced alarm codes and display coverage are separate concepts.

Persistent jobs use `dop_b__preflight_job`, `submit_job`, `job_status`,
`job_result`, `cancel_job`. They require the host's separately pinned job policy
and task-start authority. Discovery does not start a dispatcher. Preflight is
not approval; never generate a reviewer receipt to unblock a job. Poll status
and inspect a known job's result after interruption rather than submitting a
replacement request. Preserve unknown, cancelled or review-pending outcomes.

Do not share a job policy, profile root, session handle or native donor with the
DOP-100 route. Missing licensed native donors or unsupported model/format
features are explicit open inputs, not permission to patch raw bytes. Backend
offline acceptance does not establish DOPSoft compilation or panel behavior.
