#!/bin/sh
# Lift the WWS SPU job modules Resistance 3 links into its EBOOT.
#
#   tools/regen_r3_jobmods.sh [EBOOT_ELF]
#
# EBOOT_ELF defaults to game/$RES_TITLE_ID/EBOOT.elf (BCUS98176). Each module
# has a 0xC0DEC0DE header and is streamed by the Wws_Job policy module into its
# job code buffer (LS 0x4000 in Resistance 1 and 2). Interpreted, they held
# Resistance 2's first level at ~5 FPS. tools/extract_jobmods_elf.py cuts them
# out and the toolkit's tools/lift_jobmods.py writes
#   port/spu/jobmods/jobmod_*/spu_recomp.{c,h}
#   port/spu/jobmods/jobmods_register.c
# (SPU images matched by the module's 16-byte content signature when the job
# manager DMAs it in). Translated game code: regenerate it, never commit it.
# Re-run cmake afterwards (tools/rebuild.sh build). An EBOOT with none of
# these modules leaves port/spu/jobmods/ empty and the build skips it.
#
# From the Resistance 2 port (tools/regen_r2_jobmods.sh).
set -e
here=$(cd "$(dirname "$0")/.." && pwd)
TK=${PS3RECOMP_DIR:-$here/ps3recomp}
PY=${PY:-python3}
title=${RES_TITLE_ID:-BCUS98176}
elf=${1:-$here/game/$title/EBOOT.elf}
work=${RES_OUT:-$here/out}/r3-jobmods-elf
dest=$here/port/spu/jobmods

[ -f "$TK/tools/lift_jobmods.py" ] || { echo "no toolkit at $TK (run tools/setup_toolkit.sh)" >&2; exit 1; }
[ -f "$elf" ] || { echo "no $elf: decrypt your EBOOT.BIN first (tools/rebuild.sh decrypt)" >&2; exit 1; }
rm -rf "$work" "$dest"; mkdir -p "$work" "$dest"
"$PY" -I "$here/tools/extract_jobmods_elf.py" "$elf" --out "$work"
if ! ls "$work"/jobmod_*.bin >/dev/null 2>&1; then
    echo "no WWS job modules in $elf: nothing to lift"
    exit 0
fi
"$PY" "$TK/tools/lift_jobmods.py" --jobmods "$work" --out "$dest" \
      --register "$dest/jobmods_register.c" --symbol-prefix r3
echo "lifted job modules -> $dest (re-run cmake so they are picked up)"
