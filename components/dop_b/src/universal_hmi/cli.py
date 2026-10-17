"""Local entry points. Vendor IDE actions are deliberately absent."""
import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .errors import HmiError
from .model import new_project
from .runtime_assets import profiles_root


def main():
    parser = argparse.ArgumentParser(description="File-only universal HMI framework")
    parser.add_argument("--profiles", default=str(profiles_root()))
    commands = parser.add_subparsers(dest="command", required=True)
    server = commands.add_parser("serve")
    server.add_argument("--workspace", default=str(Path.cwd() / "projects"),
                        help="Private project root; default is projects under current working directory")
    server.add_argument("--job-policy", help="Trusted host policy outside the writable workspace")
    server.add_argument("--job-state", help="Private durable job state directory")
    for name in ("preflight-job", "run-job", "worker-job", "dispatch-jobs", "job-status", "job-result", "cancel-job"):
        job = commands.add_parser(name)
        job.add_argument("--policy", required=True)
        job.add_argument("--state", required=True)
        job.add_argument("--job-id")
        job.add_argument("--input", help="Complete job JSON")
        job.add_argument("--key", help="Idempotency key for a new job")
    doctor = commands.add_parser("doctor")
    preview = commands.add_parser("preview")
    preview.add_argument("design")
    preview.add_argument("profile")
    preview.add_argument("output")
    create = commands.add_parser("new-project")
    create.add_argument("directory")
    create.add_argument("--id", required=True)
    create.add_argument("--profile", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("source")
    inspect.add_argument("--family", choices=["delta_diascreen", "delta_dopsoft2"], required=True)
    args = parser.parse_args()
    try:
        if args.command == "serve":
            from .mcp_server import create_server
            Path(args.workspace).mkdir(parents=True, exist_ok=True)
            create_server(args.workspace, args.profiles, job_policy=args.job_policy, job_state=args.job_state).run(transport="stdio")
        elif args.command in ("preflight-job", "run-job", "worker-job", "dispatch-jobs", "job-status", "job-result", "cancel-job"):
            from .job_runner import JobRunner
            from .job_policy import read_object
            runner = JobRunner(args.policy, args.state)
            if args.command == "dispatch-jobs":
                result = runner.dispatch()
            elif args.command == "preflight-job":
                if not args.input:
                    raise HmiError("JOB_ARGUMENT", "--input required")
                result = runner.preflight(read_object(args.input)[1])
            else:
                job_id = args.job_id
                if args.command == "run-job" and args.input:
                    if not args.key or job_id:
                        raise HmiError("JOB_ARGUMENT", "New job requires --key and no --job-id")
                    job_id = runner.submit(args.key, read_object(args.input)[1])["job_id"]
                if not job_id:
                    raise HmiError("JOB_ARGUMENT", "--job-id or new run-job input/key required")
                result = {"run-job": runner.supervise, "worker-job": runner.run, "job-status": runner.status,
                          "job-result": runner.result, "cancel-job": runner.store.cancel}[args.command](job_id)
            print(json.dumps(result, ensure_ascii=False))
            if result.get("status") in ("FAILED", "CANCELLED"):
                raise SystemExit(2)
            if result.get("status") == "WAITING_REVIEWS":
                raise SystemExit(3)
        elif args.command == "doctor":
            from importlib.metadata import version
            from .mcp_server import create_server
            if not Path(args.profiles).is_dir():
                raise HmiError("REGISTRY", "Pass --profiles with the repo registry directory")
            print(json.dumps({"framework": __version__, "python": sys.version.split()[0],
                              "mcp": version("mcp"), "profiles": str(Path(args.profiles).resolve()),
                              "transport": "stdio", "vendor": "NOT_RUN"}))
        elif args.command == "preview":
            from .preview import render_preview
            from .validation import validate_design
            design = json.loads(Path(args.design).read_bytes())
            profile = json.loads((Path(args.profiles) / (args.profile + ".json")).read_bytes())
            content = render_preview(design, profile)
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as file:
                file.write(content)
            print(json.dumps({"path": str(output.resolve()), "findings": validate_design(design, profile),
                              "render_kind": "CONCEPTUAL_IR"}, ensure_ascii=False))
        elif args.command == "new-project":
            root = Path(args.directory)
            root.mkdir(parents=True, exist_ok=False)
            for name in ("inputs", "preview", "delivery", "evidence"):
                (root / name).mkdir()
            (root / "design.json").write_text(json.dumps(new_project(args.id, args.profile), ensure_ascii=False, indent=2), encoding="utf-8")
            print(str(root.resolve()))
        elif args.command == "inspect":
            from .native import NativeAdapter
            print(json.dumps(NativeAdapter(Path(args.source).read_bytes(), args.family).inspect(), ensure_ascii=False, indent=2))
    except (HmiError, FileNotFoundError, FileExistsError, json.JSONDecodeError) as exc:
        print(json.dumps(exc.as_dict() if isinstance(exc, HmiError) else {"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
