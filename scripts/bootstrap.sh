#!/bin/sh
# Source checkout may fetch only the checksum-pinned public release bundle.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
no_links() {
    check="$1"
    while [ "$check" != / ] && [ -n "$check" ]; do
        [ ! -L "$check" ] || { echo LINKED_INSTALL_PATH >&2; exit 1; }
        check=$(dirname -- "$check")
    done
}
no_links "$root"
for part in .local .local/downloads .local/backends .venv; do no_links "$root/$part"; done
[ ! -e "$root/.venv" ] || { echo EXISTING_GATEWAY_ENVIRONMENT_PRESERVED >&2; exit 1; }
unset PYTHONPATH PYTHONHOME
lock="$root/templates/releases.lock.json"
value() { awk -v key="\"$1\"" '$1 == key ":" {gsub(/[,\"]/, "", $2); print $2}' "$lock"; }
name=$(value linux_archive)
digest=$(value linux_sha256)
url=$(value linux_url)
[ ${#digest} -eq 64 ] || { echo INVALID_RELEASE_LOCK >&2; exit 1; }
archive=${1:-"$root/bundles/$name"}
[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || { echo UNSUPPORTED_PLATFORM >&2; exit 1; }
if [ ! -f "$archive" ]; then
    [ $# -eq 0 ] || { echo EXPLICIT_ARCHIVE_MISSING >&2; exit 1; }
    case "$url" in https://github.com/ufukefekaya-tr/universal-delta-hmi-agent/releases/download/*) ;; *) echo UNTRUSTED_RELEASE_URL >&2; exit 1;; esac
    mkdir -p "$root/.local/downloads"
    archive="$root/.local/downloads/$name"
    no_links "$archive"
    if [ ! -f "$archive" ]; then
    download=$(mktemp "$root/.local/downloads/download-XXXXXXXX")
    if command -v curl >/dev/null 2>&1; then
        curl --fail --location --proto '=https' --proto-redir '=https' --output "$download" "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$download" "$url"
    else
        echo 'HTTPS_DOWNLOADER_MISSING: use the offline release bundle' >&2; exit 1
    fi
    actual=$(sha256sum "$download")
    [ "${actual%% *}" = "$digest" ] || { echo DOWNLOAD_HASH_MISMATCH >&2; exit 1; }
    no_links "$archive"
    [ ! -e "$archive" ] || { echo EXISTING_DOWNLOAD_PRESERVED >&2; exit 1; }
    mv "$download" "$archive"
    fi
fi
no_links "$archive"
actual=$(sha256sum "$archive")
[ "${actual%% *}" = "$digest" ] || { echo ARCHIVE_HASH_MISMATCH >&2; exit 1; }
target="$root/.local/backends/dop_b"
[ ! -e "$target" ] && [ ! -L "$target" ] || { echo EXISTING_BACKEND_PRESERVED >&2; exit 1; }
check="$root"
while [ "$check" != / ]; do
    [ ! -L "$check" ] || { echo LINKED_INSTALL_ROOT >&2; exit 1; }
    check=$(dirname -- "$check")
done
[ ! -L "$root/.local" ] && [ ! -L "$root/.local/backends" ] || { echo LINKED_INSTALL_DIRECTORY >&2; exit 1; }
mkdir -p "$root/.local/backends"
stage=$(mktemp -d "$root/.local/backends/stage-XXXXXXXX")
tar -tzf "$archive" > "$stage/list.txt"
awk '/(^\/|(^|\/)\.\.(\/|$)|\\|:)/ {bad=1} END {exit bad}' "$stage/list.txt" || { echo UNSAFE_ARCHIVE_ENTRY >&2; exit 1; }
tar --no-same-owner --no-same-permissions -xzf "$archive" -C "$stage"
mv "$stage" "$target"
sh "$target/scripts/bootstrap.sh" --offline --force-runtime
"$target/.venv/bin/python" -I -B "$root/scripts/finish_install.py"
