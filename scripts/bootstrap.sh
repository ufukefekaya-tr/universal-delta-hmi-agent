#!/bin/sh
# Fixed release only; no project-controlled command or network download.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
archive=${1:-"$root/bundles/dop-b-0.2.0.zip"}
[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || { echo 'UNSUPPORTED_PLATFORM' >&2; exit 1; }
command -v unzip >/dev/null 2>&1 || { echo 'UNZIP_REQUIRED' >&2; exit 1; }
actual=$(sha256sum "$archive")
[ "${actual%% *}" = b2fba4ab82c91adc0478c493c879c05f1337ab2e1e8ab8a645b399149fa290b3 ] || { echo 'ARCHIVE_HASH_MISMATCH' >&2; exit 1; }
target="$root/.local/backends/dop_b"
[ ! -e "$target" ] && [ ! -L "$target" ] || { echo 'EXISTING_BACKEND_PRESERVED' >&2; exit 1; }
[ ! -L "$root/.local" ] && [ ! -L "$root/.local/backends" ] || { echo 'LINKED_INSTALL_DIRECTORY' >&2; exit 1; }
mkdir -p "$root/.local/backends"
stage=$(mktemp -d "$root/.local/backends/stage-XXXXXXXX")
unzip -q "$archive" -d "$stage"
mv "$stage" "$target"
sh "$target/scripts/bootstrap.sh" --offline --force-runtime
"$target/.venv/bin/python" "$root/scripts/finish_install.py"
