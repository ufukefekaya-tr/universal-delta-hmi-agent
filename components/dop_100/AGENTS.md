# Repository entry

Read this file, [SYSTEM_PROMPT.md](SYSTEM_PROMPT.md), and [INDEX.md](INDEX.md) in full before working. The canonical policy is SYSTEM_PROMPT.md. Policy epoch is SHA-256 over these three paths in this order, each UTF-8 relative path, NUL, raw file bytes, NUL.

For a new repository, the owner may make the initial control-plane commit before activating the guard. Afterwards the three files must be committed and unchanged. Read the task envelope and single-owner checkpoint. Run `python tools/session_guard.py resume` after handoff or compaction and `action` before mutations or commit. Acknowledgements are not access authorization.

Read only the relevant indexed documents. Write only assigned paths. A successful mutation closes with an exact-scope local commit; push and history changes need separate authority. Read-only reviewers never edit implementation or checkpoint files.
