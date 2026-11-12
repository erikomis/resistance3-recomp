#!/bin/zsh
# Rebuild the port from your own disc: decrypt, survey, analyse, lift, compile.
#
#   tools/rebuild.sh [step ...]
#
# Steps, in order (default: all of them):
#   toolkit decrypt survey analyse lift spu build
#
#   toolkit  tools/setup_toolkit.sh (./ps3recomp at the pinned commit + patch)
#   decrypt  RES_EBOOT_BIN (default: the disc's PS3_GAME/USRDIR/EBOOT.BIN) ->
#            game/<title>/EBOOT.elf, and PS3_GAME/PARAM.SFO beside it.
#            tools/decrypt_self.py first (keys from RPCS3's public source,
#            tools/fetch_keys.py), RPCS3 (rpcs3 --decrypt; RPCS3=<path> if it
#            is not in /Applications) as the fallback. Skipped when EBOOT.elf
#            is already there, so an ELF decrypted some other way can simply
#            be dropped in.
#   survey   tools/r3_survey.py: which EBOOT this is (RPCS3's PPU hash: 01.00
#            or 01.05, USA or Europe), its segments, the SPU code embedded in
#            it, the community patches' words -> out/survey/<title>.json and
#            .txt. Read-only; it never stops the build.
#   analyse  toolkit tools/ppu_loader.py -> analysis/<title>
#   lift     toolkit tools/ppu_lifter.py -> recompiled/<title> (24 chunks),
#            with port/patches/eboot_<version>.insn.json (the code half of
#            the optional FPS/FOV patches, tools/r3_survey.py --write-insn)
#            and .sjlj.json when they exist for this EBOOT's version
#   spu      the SPU code the image scanner cannot find on its own:
#            tools/regen_r3_jobmods.sh (the WWS job modules, 0xC0DEC0DE) and
#            every tools/prepare_r3_*.py there is (raw SPU programs, the job
#            policy module: written once tools/r3_survey.py has found them)
#   build    cmake + ninja -> build/<title>/ResistanceRecomp and
#            build/<title>/Resistance (the window tools/play.sh runs);
#            Metal, FFmpeg video
#
# Everything it writes (game/, analysis/, recompiled/, build/, out/,
# port/spu/*/spu_recomp.*) is game-derived and .gitignore'd.
# Environment: see tools/env.sh (RES_TITLE_ID, RES_EBOOT_BIN, PS3_VFS_ROOT,
# PS3RECOMP_DIR, PY), RPCS3, JOBS, PS3_KEYS.
#
# JOBS: parallel lifter processes and compiles. Without it the build runs one
# compile per 10 GB of RAM (at least 1), at low priority: each of the 24 lift
# chunks is ~200 MB of C++ that takes several GB to compile, and Ninja's
# default (one per core, plus two) swapped a 24 GB Mac until it froze.
set -e
here=${0:A:h}; source "$here/env.sh"
AN=$RES_ROOT/analysis/$RES_TITLE_ID
RC=$RES_ROOT/recompiled/$RES_TITLE_ID
if (( $# )); then steps=("$@"); else steps=(toolkit decrypt survey analyse lift spu build); fi
jobs=(); [ -n "$JOBS" ] && jobs=(-j "$JOBS")
build_jobs=$JOBS
if [ -z "$build_jobs" ]; then
    mem=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
    build_jobs=$(( mem / (10 * 1024 * 1024 * 1024) ))
    (( build_jobs < 1 )) && build_jobs=1
fi

say() { print -P "%B==> $*%b"; }

find_rpcs3() {
    for c in "$RPCS3" ~/Applications/RPCS3.app/Contents/MacOS/rpcs3 \
             /Applications/RPCS3.app/Contents/MacOS/rpcs3 "$(command -v rpcs3)"; do
        [ -n "$c" ] && [ -x "$c" ] && { echo "$c"; return 0; }
    done
    return 1
}

# The version tools/r3_survey.py --identify reports for EBOOT.elf ("100",
# "105", or "unknown"): picks port/patches/eboot_<version>.*.json.
eboot_version() {
    "$PY" -I "$here/r3_survey.py" --identify "$E" 2>/dev/null || echo unknown
}

for s in $steps; do
    case $s in
    toolkit)
        say "toolkit"; "$here/setup_toolkit.sh" "$TK" ;;
    decrypt)
        say "decrypt"
        mkdir -p "$RES_GAME"
        if [ ! -f "$E" ]; then
            [ -n "$RES_EBOOT_BIN" ] || { res_disc; RES_EBOOT_BIN=$PS3_VFS_ROOT/PS3_GAME/USRDIR/EBOOT.BIN; }
            [ -f "$RES_EBOOT_BIN" ] || { echo "no EBOOT.BIN at $RES_EBOOT_BIN" >&2; exit 1; }
            keys=$PS3_KEYS
            [ -n "$keys" ] || keys=$("$PY" -I "$here/fetch_keys.py" 2>/dev/null) || keys=
            if [ -n "$keys" ] && "$PY" -I "$here/decrypt_self.py" "$RES_EBOOT_BIN" -o "$E.partial" --keys "$keys"; then
                mv "$E.partial" "$E"
            else
                rm -f "$E.partial"
                echo "decrypting without RPCS3 failed; trying RPCS3" >&2
                rp=$(find_rpcs3) || { echo "RPCS3 not found (set RPCS3=<path>), or put a decrypted EBOOT.elf in $RES_GAME" >&2; exit 1; }
                cp "$RES_EBOOT_BIN" "$RES_GAME/EBOOT.BIN"
                "$rp" --decrypt "$RES_GAME/EBOOT.BIN" >/dev/null 2>&1 || true
                [ -f "$E" ] || { echo "RPCS3 did not write $E" >&2; exit 1; }
            fi
        fi
        [ -f "$RES_GAME/PARAM.SFO" ] || { [ -n "$PS3_VFS_ROOT" ] && cp "$PS3_VFS_ROOT/PS3_GAME/PARAM.SFO" "$RES_GAME/" 2>/dev/null || true; }
        [ "$(head -c 4 "$E")" = $'\x7fELF' ] || { echo "$E is not an ELF" >&2; exit 1; }
        v=$(eboot_version)
        if [ "$v" = unknown ]; then
            echo "WARNING: EBOOT.elf is not one of the known Resistance 3 executables (tools/r3_survey.py); the port may not match it" >&2
        else
            echo "EBOOT.elf: Resistance 3 version $v"
        fi ;;
    survey)
        say "survey"
        mkdir -p "$RES_OUT/survey"
        "$PY" -I "$here/r3_survey.py" "$E" --sfo "$RES_GAME/PARAM.SFO" \
              --json "$RES_OUT/survey/$RES_TITLE_ID.json" | tee "$RES_OUT/survey/$RES_TITLE_ID.txt" || true ;;
    analyse)
        say "analyse"
        "$PY" "$TK/tools/ppu_loader.py" "$E" -o "$AN" ;;
    lift)
        say "lift"
        v=$(eboot_version)
        extra=()
        [ -f "$RES_ROOT/port/patches/eboot_$v.insn.json" ] && extra+=(--insn-patches "$RES_ROOT/port/patches/eboot_$v.insn.json")
        [ -f "$RES_ROOT/port/patches/eboot_$v.sjlj.json" ] && extra+=(--sjlj "$RES_ROOT/port/patches/eboot_$v.sjlj.json")
        (( ${#extra} )) && echo "  with ${extra[*]}"
        "$PY" "$TK/tools/ppu_lifter.py" "$E" "${jobs[@]}" --chunks 24 \
            --functions "$AN/EBOOT.functions.json" --hle-stubs "$AN/EBOOT.imports.json" \
            "${extra[@]}" --output "$RC" ;;
    spu)
        say "spu (WWS job modules, then the port's raw-SPU tools)"
        PS3RECOMP_DIR=$TK "$here/regen_r3_jobmods.sh" "$E"
        for t in "$here"/prepare_r3_*.py(N); do
            echo "  ${t:t}"
            PS3RECOMP_DIR=$TK "$PY" "$t" --eboot "$E"
        done
        echo "  lift_r3_igjobs.py (igPm's job modules)"
        PS3RECOMP_DIR=$TK "$PY" "$here/lift_r3_igjobs.py" --eboot "$E"
        echo "  lift_r3_relocmods.py (position-independent sub-modules)"
        PS3RECOMP_DIR=$TK "$PY" "$here/lift_r3_relocmods.py" --eboot "$E" ;;
    build)
        say "build"
        bp=${HOMEBREW_PREFIX:-$(brew --prefix 2>/dev/null)}
        cmake -S "$RES_ROOT/port" -B "$RES_BUILD/$RES_TITLE_ID" -G Ninja \
              -DPS3RECOMP_DIR="$TK" -DRECOMP_DIR="$RC" -DR3_EBOOT="$E" -DRES_TITLE_ID="$RES_TITLE_ID" \
              -DPORT_SPU_INPUTS="$(res_spu_inputs)" -DPython3_EXECUTABLE="$PY" \
              -DPS3RECOMP_FFMPEG_RUNTIME=ON -DPS3RECOMP_FFMPEG_INCLUDE_DIR="${bp:-/opt/homebrew}/include"
        echo "    $build_jobs compile(s) at a time (JOBS to change)"
        nice -n 10 cmake --build "$RES_BUILD/$RES_TITLE_ID" -j "$build_jobs" ;;
    *)
        echo "unknown step '$s' (toolkit decrypt survey analyse lift spu build)" >&2; exit 2 ;;
    esac
done
say "done"
