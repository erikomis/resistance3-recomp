#!/bin/sh
# Regenerate patches/ps3recomp-a6d76c8-resistance3.patch from a working
# toolkit folder.
#
#   tools/export_toolkit_patch.sh [TOOLKIT_DIR] [OUT_PATCH]
#
# TOOLKIT_DIR (default ./ps3recomp) is any ps3recomp tree with this port's
# toolkit changes in it: the git checkout tools/setup_toolkit.sh made, or a
# plain copy of the toolkit without .git (the way the port was developed, with
# the game, the lift and the port's own project/ folder living inside it).
# The patch is the difference between upstream ps3recomp a6d76c8 (v0.17.0)
# and that tree, so `git apply` takes it on a clean a6d76c8 checkout.
#
# How: pristine a6d76c8 in a temporary git repository, the current patch
# applied (so files the working folder does not have, e.g. docs/ or
# .github/ in a partial copy, keep their patched content), the working
# folder's toolkit files copied over it, `git diff --binary` against a6d76c8.
# The export never deletes a file.
#
# Never exported: the game and anything made from it (game/, PS3_GAME/,
# PS3_UPDATE/, analysis/, recompiled/, build/, out/, modules/, project/,
# port/, disc images and executables, lifted SPU code: spu_recomp.c/.h,
# image.bin, functions.json, lift.json, generated_spu/, ppu_hle_nids.cpp),
# logs and frame dumps, and this repository's own tools (they live in tools/
# here, not in the toolkit). A new file that looks game-derived is dropped and
# listed; the finished patch is then checked for absolute home paths and
# applied to a fresh a6d76c8 tree.
#
# Upstream comes from TOOLKIT_DIR's own .git, ./ps3recomp's, UPSTREAM_GIT (any
# clone that has the commit), or a fresh clone of TOOLKIT_URL.
set -e
here=$(cd "$(dirname "$0")/.." && pwd)
src=$(cd "${1:-$here/ps3recomp}" && pwd)
out=${2:-$here/patches/ps3recomp-a6d76c8-resistance3.patch}
COMMIT=a6d76c895f77eb30b90a806c830544e61821b77f
TOOLKIT_URL=${TOOLKIT_URL:-https://github.com/sp00nznet/ps3recomp.git}
current=$here/patches/ps3recomp-a6d76c8-resistance3.patch

[ -f "$src/runtime/ppu/ppu_hle.cpp" ] || { echo "$src does not look like a ps3recomp tree" >&2; exit 1; }
tmp=$(mktemp -d "${TMPDIR:-/tmp}/r3-export.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
g() { git -c user.name=export -c user.email=export@localhost -c core.autocrlf=false "$@"; }

# 1. Pristine upstream.
up=
for c in "$src" "$here/ps3recomp" "$UPSTREAM_GIT"; do
    [ -n "$c" ] && git -C "$c" cat-file -e "$COMMIT^{commit}" 2>/dev/null && { up=$c; break; }
done
if [ -z "$up" ]; then
    echo "cloning $TOOLKIT_URL for $COMMIT..."
    git clone --quiet --filter=blob:none --no-checkout "$TOOLKIT_URL" "$tmp/clone"
    up=$tmp/clone
fi
mkdir "$tmp/tree"
git -C "$up" archive "$COMMIT" | tar -x -C "$tmp/tree"
cd "$tmp/tree"
g init --quiet && g add -A -f && g commit --quiet -m upstream
base=$(git rev-parse HEAD)   # a6d76c8's tree, under a local commit id
[ -f "$current" ] && g apply --whitespace=nowarn "$current"

# 2. The working folder's toolkit files over it.
( cd "$src" && find . \( -name .git -o -name .DS_Store -o -name __pycache__ -o -name generated_spu \
        -o -path ./game -o -path ./PS3_GAME -o -path ./PS3_UPDATE -o -path ./analysis \
        -o -path ./recompiled -o -path ./build -o -path ./out -o -path ./modules \
        -o -path ./project -o -path ./port -o -path ./patches -o -path ./ps3recomp \) -prune \
        -o -type f -print ) | sed 's|^\./||' | grep -v -E \
    -e '\.(iso|ISO|elf|ELF|bin|BIN|self|SELF|sprx|SPRX|prx|PRX|sdat|SDAT|edat|EDAT|pkg|PKG|SFB|SFO|sfo|psarc|PSARC|rap|rif|log|ppm|wav|pyc)$' \
    -e '\.(orig|rej|bak)$' \
    -e '^[^/]+\.(md|sh)$' \
    -e '^tools/(r3_[^/]*|prepare_r3_[^/]*|lift_r3_[^/]*|regen_r3_[^/]*|extract_jobmods_elf\.py|export_toolkit_patch\.sh|setup_toolkit\.sh|rebuild\.sh|install\.sh|play\.sh|env\.sh|bootstrap_deps\.sh|decrypt_self\.py|fetch_keys\.py)$' \
    > "$tmp/files" || true
# Top-level Markdown files and scripts are the port's notes and launchers, not
# the toolkit's, except the ones upstream has.
for f in README.md CHANGELOG.md CONTRIBUTING.md CONTRIBUTORS.md; do
    [ -f "$src/$f" ] && echo "$f" >> "$tmp/files"
done
rsync -a --files-from="$tmp/files" "$src/" "$tmp/tree/"
g add -A -f

# 3. Drop new files that look game-derived (lifted code, extracted images).
g diff --cached --name-only --diff-filter=A "$base" | grep -E \
    -e '(^|/)(spu_recomp\.[ch]|image\.bin|functions\.json|lift\.json|ppu_hle_nids\.cpp|ppu_recomp[^/]*)$' \
    -e '(^|/)(jobmods_register\.c|jobmods_manifest\.json|spu_workloads\.c)$' \
    > "$tmp/dropped" || true
if [ -s "$tmp/dropped" ]; then
    echo "not exported (look game-derived):" >&2; sed 's/^/  /' "$tmp/dropped" >&2
    while read -r f; do g rm --quiet --cached -f -- "$f"; done < "$tmp/dropped"
fi

g diff --cached --binary "$base" > "$tmp/patch"

# 4. Checks: no home paths, and it applies to a fresh a6d76c8.
if grep -n -E '/Users/[A-Za-z]|/home/[a-z]' "$tmp/patch" | head -5 | grep . >&2; then
    echo "the patch has absolute home paths (above): fix them in $src first" >&2; exit 1
fi
mkdir "$tmp/check"
git -C "$up" archive "$COMMIT" | tar -x -C "$tmp/check"
( cd "$tmp/check" && g init --quiet && g apply --check --whitespace=nowarn "$tmp/patch" )
cp "$tmp/patch" "$out"
n=$(grep -c '^diff --git' "$out")
echo "wrote $out: $n files, $(wc -c < "$out" | tr -d ' ') bytes; applies cleanly to a6d76c8"
