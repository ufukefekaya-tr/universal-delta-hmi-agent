"""Read-only packaged registries; source trees are never runtime dependencies."""
from importlib.resources import files
from pathlib import Path


def _root(name: str) -> Path:
    resource = files('universal_hmi').joinpath('data', name)
    # Wheels installed by pip are unpacked. Zip-import is deliberately unsupported:
    # the service requires stable filesystem paths for immutable registry witnesses.
    if not isinstance(resource, Path) or not resource.is_dir():
        raise RuntimeError('Install the unpacked wheel with pip; packaged assets are missing')
    return resource


def profiles_root() -> Path:
    return _root('profiles')


def templates_root() -> Path:
    return _root('templates')
