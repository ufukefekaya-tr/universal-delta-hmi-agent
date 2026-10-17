# Accepted independent DIAScreen integration contract

The separately maintained component is published as a clean source snapshot in `components/dop_100`; `templates/releases.lock.json` pins its version, original commit and archive identity. Original source is Apache-2.0. Historical license-unclear upstream code and proprietary qualification files are excluded.

The module is `universal_diascreen_hmi.cli`. Its actual CLI accepts `--workspace`, optional `--allow-write` and repeated `--read-root`. It has no DOP-B `serve` subcommand, profile registry argument or durable job runner. The gateway preserves this distinction.

A trusted registry supplies exact profile objects of family `diascreen-dop100`. Gateway opening accepts `profile_id`, `path` and `source_sha256`; it injects the canonical profile and hash. Each open owns a new backend process; all project tools require the returned gateway `session_id`. `close_session` explicitly releases it. No previous project's implicit state is overwritten.

All30 audited tool names, including18 historical file intents, are discoverable. Their backend schemas are retained except the explicit gateway session/profile transformation. Four historical GUI tools and source-overwrite/editor-reload options remain intentionally excluded. Unsupported constructors remain explicit refusals.

Proposal preview and validation require the exact reviewed `plan_sha256` to select a proposed candidate. Application still requires independent `approval_sha256` equality and trusted process write permission. Save requires a new path and exact candidate hash. Read-only proposal review does not apply or save the candidate.

The full53-group feature disposition and21 regressions remain linked to the component support matrix. Offline, source-bound, contract-only, unqualified, withdrawn and physical evidence levels are not interchangeable.
