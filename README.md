# Universal Delta HMI Agent

Portable, file-only MCP tools for Delta HMI engineering. DOP-B/DOPSoft 2 and DOP-100/DIAScreen run in separate backend processes, Python environments, profile registries, workspaces and job state. Original code is licensed under Apache-2.0.

This release integrates the existing qualified offline capabilities of two independent components. It preserves unknown native bytes, requires explicit target/source/plan contracts, and saves new candidates. It does not claim support for every model, driver or native widget. See [support](docs/SUPPORT.md) before choosing a task.

Current source update: [MCP consolidation](docs/MCP_CONSOLIDATION.md), umbrella 0.4.0 and DIAScreen 0.5.0. The source backend has 83 routes; published v0.2.1 offline archives remain historical 30-tool bundles.

Earlier source additions: [gauge readback/profile intake](docs/GAUGE_SOURCE_PROFILE.md)
and [state text lookup](docs/STATE_LOOKUP.md). They remain included.

## Install

Download and extract the complete offline ZIP from [Releases](https://github.com/ufukefekaya-tr/universal-delta-hmi-agent/releases). Windows x64 (PowerShell and the system `tar` command):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/bootstrap.ps1 -Offline
./.venv/Scripts/python.exe -I -B -m delta_hmi.cli doctor --config .local/gateway.json
./.venv/Scripts/python.exe -I -B -m delta_hmi.cli config --config .local/gateway.json
```

Linux x86_64 with glibc:

```sh
sh scripts/bootstrap.sh
./.venv/bin/python -I -B -m delta_hmi.cli doctor --config .local/gateway.json
./.venv/bin/python -I -B -m delta_hmi.cli config --config .local/gateway.json
```

The package contains pinned CPython runtimes and dependency wheels. No Python, vendor IDE or administrator installation is required for the offline package. A source checkout can download only the release bundle specified by URL and SHA-256 in `templates/releases.lock.json`. Pass an explicit archive to either bootstrap script for fully offline source installation.

The Windows launch option applies only to that installer process and does not change the machine execution policy. The final command prints the MCP client configuration for this host. Copy its output into your MCP client. Paths are generated locally; virtual environments must be rebuilt when moving to another machine. Installation refuses to replace an existing environment.

On Windows, choose a fresh absolute installation root of at most64 characters;
the installer refuses longer roots before extraction or package installation.
Keep `-I -B` on gateway/test-driver launches: new import bytecode intentionally
invalidates the pinned runtime inventory. No system long-path setting is changed.
The base offline install includes structural/text previews. Optional PNG drawing
requires the separately installed `Pillow==12.2.0` visual extra and host-reviewed
fonts; neither is silently installed or bundled as a machine asset.

## Use

The optional [Delta HMI companion skill](skills/delta-hmi/SKILL.md) is version
0.1.0 under MIT; MCP code remains Apache-2.0. Extract the skill ZIP so
`delta-hmi/SKILL.md` is inside your Codex skills directory, connect this MCP using
the generated host configuration, then invoke `$delta-hmi`. The skill ZIP
contains instructions and compatibility metadata; the file server is installed
separately. It does not bundle project inputs, vendor seeds or a second parser.
The bounded independent forward acceptance is documented in
[skill evaluation](docs/SKILL_EVALUATION.md).

Call `delta_catalog` to see actual backend availability and authority. Tool names have explicit family prefixes:

- `dop_b__`: nine file tools and five persistent job tools. Jobs require a separately configured trusted policy; discovery never starts the queue.
- `dop_100__`: 83 source-audited routes and legacy aliases, plus `close_session`. Unsupported constructors/IDE routes refuse explicitly. Each opened or template-created project receives its own process and gateway session handle.

For DOP-B, call `capabilities(profile_id)`, then `open_project(profile_id, source_path)`. Follow the returned session/plan hashes through proposal, preview, validation, approval, application, new-only save and diff.

For DIAScreen, call `open_project(profile_id, path, source_sha256)` with a reviewed host profile. The gateway injects its pinned profile object and canonical hash. Pass the returned `session_id` to project tools. Review the exact proposed `plan_sha256` using `preview` and `validate` before `apply_plan`; approval must match that digest. `save_as` requires the exact candidate hash. Close idle sessions explicitly.

The installed synthetic profiles exercise file framing only; they are not usable machine applications or vendor-qualified targets. New machine work requires an authorized native source/donor and a source-qualified model/editor/profile, addresses, types and behavior contract. [Agent start](docs/AGENT_START.md) and [workflow](docs/WORKFLOW.md) describe the gates.

## Scope and evidence

The repository includes source snapshots in `components/dop_b` and `components/dop_100`; implementations, policies and support evidence stay isolated. [Component pins](templates/releases.lock.json) record provenance. No private native projects, customer PLC symbols, logos, fonts or machine logic are included.

File tests and synthetic previews establish offline behavior. Vendor opening, compilation, pixel fidelity, transport freshness, press/release behavior and physical panel operation require separate human acceptance. No Computer Use, vendor process or control-target connection is supplied.

The support ledger explicitly distinguishes implemented operations, source-bound limits, preserved-only resources, contract-only interfaces, withdrawn experiments and unsupported features. A passing refusal test is not a support claim. Alarm history, arbitrary picture-bank constructors and additional upstream widgets are not silently advertised as implemented.

## Development

```text
python tools/ci.py install
python tools/ci.py test
```

CI tests the gateway and both component suites on Windows and Linux. A separate
portable job installs an exact source archive in a fresh directory using bundled
runtimes and exercises `scripts/probe_both.py`. Current evidence and publication
ordering are in the [0.4.0 distribution contract](docs/RELEASE_0_4.md); earlier
native-service reports remain historical.

- [Architecture](docs/ARCHITECTURE.md), [workflow](docs/WORKFLOW.md), [goals](docs/GOALS.md)
- [Feature migration](docs/FEATURE_MIGRATION.json), [regressions](docs/REGRESSIONS.json)
- [Support](docs/SUPPORT.md), [persistent jobs](docs/JOBS.md)
- [Contributing](CONTRIBUTING.md), [security](SECURITY.md), [licensing](THIRD_PARTY_NOTICES.md)

Apache-2.0 provides the contributor patent grant described in section 3. Third-party dependencies and runtimes retain their own licenses and notices. Delta product names describe compatibility targets; this is independent software without vendor endorsement.


Typed numeric/dash visibility is documented in [DIAScreen visibility](components/dop_100/docs/TYPED_VISIBILITY.md). Existing source conditions and macros are preserved; validity and numeric types are checked separately.
