"""Headless entry point; host configuration is never a tool argument."""
import argparse
import asyncio
import json
import sys
from .config import GatewayConfig

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['serve', 'doctor', 'config'])
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    try:
        config = GatewayConfig.load(args.config)
        if args.action == 'serve':
            from .gateway import serve
            asyncio.run(serve(args.config))
        elif args.action == 'doctor':
            result = {}
            for name, backend in config.backends.items():
                try:
                    backend.verify()
                    result[name] = {'status':'CONFIG_VERIFIED', 'native_qualification':'BACKEND_PROFILE_DEPENDENT'}
                except (ValueError, OSError) as exc:
                    result[name] = {'status':'UNAVAILABLE', 'reason':str(exc)}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if all(v['status']=='CONFIG_VERIFIED' for v in result.values()) else 2
        else:
            from pathlib import Path
            print(json.dumps({'mcpServers':{'universal-delta-hmi':{
                'command':str(Path(sys.executable).absolute()),
                'args':['-I','-B','-m','delta_hmi.cli','serve','--config',str(Path(args.config).resolve())]
            }}}, indent=2))
    except (ValueError, OSError) as exc:
        print(json.dumps({'status':'BLOCKED','detail':str(exc)}), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
