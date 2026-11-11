#!/bin/zsh
# Install the port from your own disc in one go, the way the launcher's
# "Install the game" button does:
#
#   PS3_VFS_ROOT=/Volumes/<your disc> tools/install.sh
#
#   deps     tools/bootstrap_deps.sh: CMake, Ninja, Python 3.12, SDL2,
#            SPIRV-Tools, glslang, SPIRV-Cross and FFmpeg in RES_DEPS
#            (no Homebrew; RES_NO_DEPS=1 skips this and uses Homebrew's)
#   toolkit  tools/setup_toolkit.sh (./ps3recomp at the pinned commit + patch)
#   venv     .venv from that Python, with ps3recomp/requirements.txt
#   decrypt  the disc's EBOOT.BIN (or RES_EBOOT_BIN) -> game/<title>/EBOOT.elf with
#            tools/decrypt_self.py, no RPCS3: the keys come from RPCS3's
#            public source code, downloaded once by tools/fetch_keys.py into a
#            file outside the repository. RPCS3 (tools/rebuild.sh decrypt) is
#            only the fallback when that fails. Then tools/rebuild.sh decrypt,
#            which copies PARAM.SFO and names the executable's version.
#   survey, analyse, lift, spu, build: tools/rebuild.sh's steps
#
# Run it again after a failure or a quit and it continues: tools/bootstrap_deps.sh
# skips what it installed, the toolkit and the venv are kept, decrypt runs only
# while EBOOT.elf is missing (so the disc is needed only then), analyse, lift
# and spu are skipped when they finished before with the same inputs (the ELF,
# the toolkit pin and patch, the port's scripts; stamps in out/install/), and
# the build is incremental.
#
# With RES_DEPS's tools installed, the build uses them rather than Homebrew's:
# they go first on PATH and in CMAKE_PREFIX_PATH, and HOMEBREW_PREFIX points
# at them for tools/env.sh's and tools/rebuild.sh's FFmpeg headers and
# libraries.
#
# Environment: as tools/rebuild.sh (RES_TITLE_ID, RES_EBOOT_BIN, PS3_VFS_ROOT, JOBS, PY), RES_DEPS,
# RES_NO_DEPS, RES_SELF_KEYS / PS3_KEYS (the key file).
set -e
setopt pipefail
here=${0:A:h}
say() { print -r -- "==> $*"; }
fail() { print -u2 -r -- ""; print -u2 -r -- "ERROR: $*"; exit 1; }

# A full Resistance 2 install left about 2.5 GB on the disk (the lift 1.2 GB,
# the build 0.5 GB, the toolkit, venv and build tools 0.6 GB); Resistance 3's
# EBOOT is larger, so more is asked for until it is measured, with room for
# the build tree on the way, the first boot's HDD install and the shader cache.
NEED_GB=${RES_NEED_GB:-8}

root=${here:h}
if [ ! -x "$root/build/${RES_TITLE_ID:-BCUS98176}/ResistanceRecomp" ]; then
    free_gb=$(( $(df -k "$root" | awk 'NR==2 {print $4}') / 1024 / 1024 ))
    if (( free_gb < NEED_GB )); then
        fail "not enough free disk space: $free_gb GB free, about $NEED_GB GB are needed. Free some space and run this again."
    fi
fi

RES_DEPS=${RES_DEPS:-$HOME/Library/Application Support/resistance-recomp-3/deps}
export RES_DEPS
if [ -z "$RES_NO_DEPS" ]; then
    say "deps (the build tools and libraries: tools/bootstrap_deps.sh)"
    "$here/bootstrap_deps.sh"
fi
if [ -f "$RES_DEPS/manifest.txt" ] && [ -f "$RES_DEPS/include/libavcodec/avcodec.h" ]; then
    path=("$RES_DEPS/bin" ${path:#$RES_DEPS/bin})
    export CMAKE_PREFIX_PATH=$RES_DEPS${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}
    export PKG_CONFIG_LIBDIR=$RES_DEPS/lib/pkgconfig
    export HOMEBREW_PREFIX=$RES_DEPS
fi
source "$here/env.sh"
TK=${PS3RECOMP_DIR:-$RES_ROOT/ps3recomp}
cd "$RES_ROOT"

# One install at a time in this checkout.
ST=$RES_OUT/install
mkdir -p "$ST"
if [ -f "$ST/pid" ] && kill -0 "$(cat "$ST/pid")" 2>/dev/null; then
    fail "another install is already running in $RES_ROOT (process $(cat "$ST/pid")). Wait for it, or stop it, and run this again."
fi
print -r -- $$ >"$ST/pid"
trap 'rm -f "$ST/pid"' EXIT

"$here/rebuild.sh" toolkit

# The Python environment the toolkit's tools and the SPU scripts run in (3.10+).
venv=$RES_ROOT/.venv
if ! "$venv/bin/python" -c 'import sys, Crypto, capstone, construct, tabulate, tqdm; assert sys.version_info >= (3, 10)' >/dev/null 2>&1; then
    say "venv (the Python environment)"
    if ! "$venv/bin/python" -c 'import sys; assert sys.version_info >= (3, 10)' >/dev/null 2>&1; then
        rm -rf "$venv"
        base=$(command -v python3.12 || command -v python3.13 || command -v python3.11 || command -v python3.10) ||
            fail "no Python 3.10 or newer (run tools/bootstrap_deps.sh, or brew install python@3.12)"
        "$base" -m venv "$venv" || fail "could not make the Python environment in $venv"
    fi
    "$venv/bin/python" -m pip install --quiet --disable-pip-version-check -r "$TK/requirements.txt" ||
        fail "could not install the toolkit's Python packages (pip). Check the internet connection and run this again."
fi
export PY=$venv/bin/python

# decrypt: only while EBOOT.elf is missing.
if [ ! -f "$E" ]; then
    say "decrypt (your disc's EBOOT.BIN)"
    [ -n "$RES_EBOOT_BIN" ] && [ -f "$RES_EBOOT_BIN" ] || res_disc ||
        fail "the disc is not mounted: mount your Resistance 3 ($RES_TITLE_ID) disc image and run this again."
    RES_EBOOT_BIN=${RES_EBOOT_BIN:-$PS3_VFS_ROOT/PS3_GAME/USRDIR/EBOOT.BIN}
    mkdir -p "$RES_GAME"
    keys=$PS3_KEYS
    if [ -z "$keys" ]; then
        # (RES_SELF_KEYS moves the key file; fetch_keys.py reads it itself)
        keys=$("$PY" "$here/fetch_keys.py") || keys=
    fi
    if [ -n "$keys" ] && "$PY" "$here/decrypt_self.py" "$RES_EBOOT_BIN" -o "$E.partial" --keys "$keys"; then
        mv "$E.partial" "$E"
    else
        rm -f "$E.partial"
        print -u2 -r -- "decrypting without RPCS3 failed; trying RPCS3 (tools/rebuild.sh decrypt)"
    fi
fi
# copies PARAM.SFO, checks the ELF (and decrypts with RPCS3 when it is still missing)
"$here/rebuild.sh" decrypt || fail "could not decrypt the game's EBOOT.BIN from your disc. Check that it is Resistance 3 ($RES_TITLE_ID), and the internet connection (the keys are downloaded once), then run this again."
"$here/rebuild.sh" survey

# analyse, lift, spu: skipped when they finished with the same inputs. Each
# step's key chains the one before it, so a new analysis re-lifts too.
key=
step() {   # <step> <input file...>
    local name=$1; shift
    key=$({ print -r -- "$key"; cat -- "$@"; } | shasum -a 256 | cut -d' ' -f1)
    if [ "$(cat "$ST/$name" 2>/dev/null)" = "$key" ]; then
        say "$name (done before with the same inputs, skipped)"
        return 0
    fi
    rm -f "$ST/$name"
    "$here/rebuild.sh" "$name"
    print -r -- "$key" >"$ST/$name"
}
step analyse "$E" "$here/setup_toolkit.sh" "$RES_ROOT"/patches/*.patch(N)
step lift "$here/rebuild.sh" "$RES_ROOT"/port/patches/*.json(N)
step spu "$here"/prepare_r3_*.py(N) "$here/regen_r3_jobmods.sh" "$here/extract_jobmods_elf.py"

"$here/rebuild.sh" build
say "done"
