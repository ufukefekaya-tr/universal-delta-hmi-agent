#!/bin/sh
# Only the fixed, checksum-verified Astral distribution is provisioned.
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
offline=false
force=false
for arg in "$@"; do
    case "$arg" in --offline) offline=true;; --force-runtime) force=true;; *) echo '{"status":"BLOCKED","code":"BAD_BOOTSTRAP_ARGUMENT"}' >&2; exit 1;; esac
done
fail() { echo "{\"status\":\"BLOCKED\",\"code\":\"$1\"}" >&2; exit 1; }
[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || fail UNSUPPORTED_PLATFORM
python_cmd=${PYTHON:-python3}
if $force || ! "$python_cmd" -c 'import sys,struct; assert sys.version_info[:2] == (3,14) and struct.calcsize("P") == 8' 2>/dev/null; then
    # Repeated here because JSON parsing must work when no Python is installed.
    filename='cpython-3.14.8+20261013-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz'
    url='https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-3.14.8%2B20261013-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz'
    digest='d8faa1b588506b9e3e5a3f57807bb056d534a1641a6b10d15b6ea3f0b413b960'
    runtime_root="$repo_root/.runtime"
    python_cmd="$runtime_root/python/bin/python3"
    if [ ! -x "$python_cmd" ]; then
        mkdir -p "$runtime_root"
        archive="$repo_root/runtime-bundle/$filename"
        if [ ! -f "$archive" ]; then
            $offline && fail OFFLINE_RUNTIME_MISSING
            archive="$runtime_root/$filename"
            command -v curl >/dev/null 2>&1 || fail CURL_REQUIRED
            curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 --output "$archive" "$url" || fail RUNTIME_DOWNLOAD_FAILED
        fi
        actual=$(sha256sum "$archive")
        [ "${actual%% *}" = "$digest" ] || fail RUNTIME_HASH_MISMATCH
        tar -tzf "$archive" > "$runtime_root/archive-list.txt" || fail RUNTIME_ARCHIVE_INVALID
        awk '/(^|\/)\.\.(\/|$)|\\|:/ || $0 !~ /^python\// {bad=1} END {exit bad}' "$runtime_root/archive-list.txt" || fail UNSAFE_RUNTIME_ARCHIVE
        stage=$(mktemp -d "$runtime_root/stage-XXXXXXXX")
        tar --no-same-owner --no-same-permissions -xzf "$archive" -C "$stage" || fail RUNTIME_EXTRACTION_FAILED
        [ ! -e "$runtime_root/python" ] || fail PARTIAL_RUNTIME_REQUIRES_REPAIR
        mv "$stage/python" "$runtime_root/python" || fail RUNTIME_INSTALL_FAILED
    fi
fi
"$python_cmd" -c 'import sys,struct; assert sys.version_info[:2] == (3,14) and struct.calcsize("P") == 8' || fail INVALID_RUNTIME
if $offline; then
    "$python_cmd" "$repo_root/scripts/build_release.py" --install --offline || fail INSTALL_FAILED
else
    "$python_cmd" "$repo_root/scripts/build_release.py" --install || fail INSTALL_FAILED
fi
