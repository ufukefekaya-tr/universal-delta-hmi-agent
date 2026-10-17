"""Print config for the current host; never change a client's settings."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ['open_project', 'capabilities', 'inspect', 'plan_changes', 'preview', 'validate', 'apply_plan', 'save_as', 'diff']
JOB_TOOLS = ['preflight_job', 'submit_job', 'job_status', 'job_result', 'cancel_job']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--format', choices=['json', 'codex'], default='codex')
    parser.add_argument('--workspace', type=Path, default=ROOT / 'projects')
    parser.add_argument('--profiles', type=Path, help='Optional explicit registry; default uses packaged registry')
    parser.add_argument('--job-policy', type=Path, help='Trusted host policy; outside the job workspace')
    parser.add_argument('--job-state', type=Path, help='Private persistent job state')
    args = parser.parse_args()
    if bool(args.job_policy) != bool(args.job_state):
        parser.error('--job-policy and --job-state must be supplied together')
    # Absolute paths here are generated afresh on this host, not stored in the repo.
    # Preserve POSIX venv/bin/python symlinks: resolving them selects the base
    # interpreter, whose environment may not contain this editable package.
    command = str(Path(sys.executable).absolute())
    arguments = ['-m', 'universal_hmi.cli']
    if args.profiles:
        arguments += ['--profiles', str(args.profiles.resolve())]
    arguments += ['serve', '--workspace', str(args.workspace.resolve())]
    if args.job_policy:
        arguments += ['--job-policy', str(args.job_policy.resolve()), '--job-state', str(args.job_state.resolve())]
    if args.format == 'json':
        print(json.dumps({'mcpServers': {'universal-hmi': {'command': command, 'args': arguments}}}, ensure_ascii=False, indent=2))
    else:
        # JSON basic string escaping is also valid for these TOML values.
        print('[mcp_servers.universal_hmi]')
        print('command = '+json.dumps(command))
        print('args = '+json.dumps(arguments))
        print('startup_timeout_sec = 20\ntool_timeout_sec = 60')
        print('enabled_tools = '+json.dumps(TOOLS + (JOB_TOOLS if args.job_policy else [])))


if __name__ == '__main__':
    main()
