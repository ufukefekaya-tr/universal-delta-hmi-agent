# Portable headless installation — 0.2.0

Supported acceptance targets: Windows 11 x64 and Ubuntu 24.04 x86_64. Installation is project-local, without administrator privileges, Git, vendor IDE, PLC access, global PATH changes or client configuration changes. This installation path consumes the release source ZIP, which includes the application wheel. A checkout is for building the release; it is not the installation artifact.

1. Extract the release ZIP into a writable directory owned by the current user.
2. Windows: `powershell -NoProfile -File scripts/setup.ps1`.
3. Ubuntu: `sh scripts/setup.sh`.
4. Use `.venv/Scripts/python.exe -m universal_hmi.cli doctor` on Windows or `.venv/bin/python -m universal_hmi.cli doctor` on Ubuntu. Use the same interpreter for all CLI/job commands.

If Python 3.14 x64 is absent, setup downloads the fixed CPython 3.14.8 distribution from the official Astral python-build-standalone release 20261013, verifies its SHA-256, and extracts it into `.runtime`. Windows requires its built-in `tar`; Ubuntu requires `curl`, `tar`, `sha256sum` and `awk`. Missing base tools produce a blocking result; setup never invokes a system package manager. `-ForceRuntime` / `--force-runtime` exercises provisioning even when compatible Python is on PATH.

Windows Store execution aliases are skipped during Python detection so a missing-runtime install cannot open the Store. The pinned project-local runtime is provisioned instead.

The trusted distribution sources and hashes are in `scripts/bootstrap.lock.json`. Linux repeats the three runtime constants in its shell bootstrap because Python may be absent; tests enforce equality. Runtime hashes come from GitHub's release asset digest. All 30 dependency versions remain identical to `requirements.lock`, with published wheel hashes obtained from PyPI's version JSON API. Installation uses pip's `--require-hashes --only-binary=:all:`. The application wheel is checked against the release manifest. Manifests provide integrity relative to the trusted release; they are not a signature or an independent source of trust.

## Offline bundles

The default release needs network access for dependencies and, when absent, Python. An optional offline release can be built with `--wheelhouse <directory> --runtime-bundle <directory>`. Supply dependency wheels for each target platform and the exact runtime tarballs named in the lock. Only hash-matching, named files are accepted. The builder does not claim completeness from the presence of directories; offline pip resolves the complete dependency graph and fails if any wheel is absent. Run `setup.ps1 -Offline -ForceRuntime` or `sh scripts/setup.sh --offline --force-runtime` in a clean environment to qualify an offline bundle. No download fallback is allowed in offline mode.

## Build and data ownership

Run `.venv/Scripts/python.exe scripts/build_release.py` (or the equivalent Linux interpreter) from a developer checkout with its locked setuptools installed. Outputs are under `dist/0.2.0`: deterministic source ZIP, application wheel and SHA-256 manifest. The build writes generated package assets only under `src/universal_hmi/data`. `profiles/` and `templates/` remain canonical; the builder validates JSON and copies the exact bytes, including all nested authority books. After changing either source, run `scripts/build_release.py --sync-assets` before source tests. Direct pip builds consume the already synchronized package assets; the canonical release builder performs synchronization first.

Installed wheels use `importlib.resources` to find their included profiles and templates. They work from unrelated working directories without a checkout, including read-only package directories. Zip-import without installing the wheel is unsupported because service witnesses require stable files. Writable workspaces and job stores must be outside the installed package. Releases exclude `.git`, agent state, virtual environments, local projects, vendor material and private directories. Optional runtime bundles contain the upstream runtime's licensing notices; redistribute them unchanged.

The source ZIP includes current public report summaries, all public `reports/headless` records, Kaizen text, and top-level neutral examples. Historical report/log trees and the old browser-review image collection are omitted; links into those historical collections require the full repository. Current headless status and acceptance reports are included with the release.

`scripts/configure_mcp.py` prints host-specific JSON or TOML; it never edits client settings. Run it with the installed environment's interpreter. Runtime execution never invokes Git.

## Evidence boundary

A successful build, isolated wheel installation or `doctor` proves only that particular operation. Fresh Windows and Ubuntu jobs, termination/restart recovery, denied-network offline installation, source hash preservation and vendor acceptance are separate evidence. Missing Linux or offline evidence must remain open; no headless release-ready claim follows from the package tests alone.

Sources: [Astral distribution format](https://docs.astral.sh/python-build-standalone/distributions/), [published runtime release](https://github.com/astral-sh/python-build-standalone/releases/tag/20261013), [pip secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/).
