# Persistent DOP-B jobs

The five `dop_b__` tools are `preflight_job`, `submit_job`, `job_status`, `job_result` and `cancel_job`. They are discoverable even when job authority is absent; calls then report a missing trusted policy. Tool discovery does not launch a dispatcher or recover old jobs.

Use the independent backend's [headless instructions](../components/dop_b/docs/HEADLESS_RELEASE.md) and policy schema. A host administrator prepares the policy outside all mutable workspaces, job state and output/review roots. Add its configuration-relative path as `backends.dop_b.job_policy` and its exact byte SHA-256 as `job_policy_sha256` in the trusted gateway configuration. This is host setup, never an MCP job argument.

The policy pins workspace, profile registry and allowed capabilities; its workspace and profile roots must match the DOP-B route. Output and review roots must not overlap either family's protected roots or each other. The gateway uses that route's isolated state directory. A new policy needs a new explicit policy hash, not an implicit authority extension.

Jobs require genuine independent review evidence before a result is published. A routing test deliberately missing reviews must fail to produce a completed result. Persistent job handles are bound to the same trusted policy and survive gateway restart. Changing policy identity invalidates old gateway handles. Native backend job IDs are reported separately for locating independent review records.

No job mode enables Computer Use, vendor compilation, control-target networking or physical operation.
