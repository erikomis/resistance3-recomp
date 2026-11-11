#!/bin/sh
# Prepare the ps3recomp toolkit this port builds against.
#
#   tools/setup_toolkit.sh            # -> ./ps3recomp
#   tools/setup_toolkit.sh DIR
#
# The port builds against upstream ps3recomp v0.17.0 (commit below) plus this
# repository's toolkit changes, all in patches/ps3recomp-a6d76c8-resistance3.patch.
# It starts as the Resistance 2 port's patch as it stood on 2026-11-11 (itself
# the Resistance: Fall of Man patch plus the Resistance 2 changes): the same
# Insomniac engine, so the same SPURS, WWS job, RSX and audio fixes are the
# place to start. Resistance 3 changes are added to it with
# tools/export_toolkit_patch.sh. A checkout with changes of its own is never reset: if the patch
# neither applies nor is already applied, the script stops and says so.
#
# TOOLKIT_URL overrides where the toolkit is cloned from (a fork, a mirror).
set -e
here=$(cd "$(dirname "$0")/.." && pwd)
dest="${1:-$here/ps3recomp}"
TOOLKIT_URL=${TOOLKIT_URL:-https://github.com/sp00nznet/ps3recomp.git}
TOOLKIT_COMMIT=a6d76c895f77eb30b90a806c830544e61821b77f   # v0.17.0
PATCH="$here/patches/ps3recomp-a6d76c8-resistance3.patch"

if [ ! -d "$dest/.git" ]; then
    git clone "$TOOLKIT_URL" "$dest"
fi
cd "$dest"
if ! git cat-file -e "$TOOLKIT_COMMIT^{commit}" 2>/dev/null; then
    git fetch --quiet origin
fi

head=$(git rev-parse HEAD)
if [ "$head" = "$TOOLKIT_COMMIT" ] && git apply --reverse --check "$PATCH" 2>/dev/null; then
    echo "toolkit already patched: $dest"
    exit 0
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "$dest has local changes and is not a clean $TOOLKIT_COMMIT + patch;" >&2
    echo "commit or stash them, or point the script at a fresh directory." >&2
    exit 1
fi
git checkout --quiet --detach "$TOOLKIT_COMMIT"
git apply --whitespace=nowarn "$PATCH"   # third_party/smaa/AreaTex.h is a generated table
echo "toolkit ready: $dest (ps3recomp v0.17.0 $(git rev-parse --short HEAD) + resistance3 patch)"
