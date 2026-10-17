# Universal Delta HMI Agent

Read this file, SYSTEM_PROMPT.md and INDEX.md completely before work. Read the relevant role and checkpoint. The three control files must match committed HEAD before implementation. Initial bootstrap is the sole exception.

Use a scoped task envelope and checkpoint for mutations. Run `python tools/guard.py` before edits and commit. Only the orchestrator writes shared state and commits. Independent reviewers are read-only. Sources outside this repo remain read-only. Local scoped commits are required; no push.
