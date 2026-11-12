#!/bin/zsh
# Play Resistance 3 in a window, with a controller.
#
#   tools/play.sh
#   RES_UNLOCK_FPS=1 RES_FOV=0.7 tools/play.sh   # the community patches
#   RES_LEVEL=<n> tools/play.sh                  # experimental, see below
#
# The window belongs to the launcher (build/<title>/Resistance, built here in
# seconds when missing): the game renders into it through shared IOSurfaces.
# A controller is required on macOS (DualSense, DualShock or Xbox, through
# SDL2). Close the game window (or Ctrl+C here) to quit.
#
# Saves, the HDD folders and the log live in RES_DATA (default
# ~/Library/Application Support/resistance-recomp-3/): dev_hdd0/, dev_hdd1/
# and last.log. The window title shows the frame rate (PS3RECOMP_METAL_FPS=1).
# PS3_PAD_LOG=1 (the default here) logs controller button changes;
# PS3_PAD_LOG=0 turns that off.
#
# RES_UNLOCK_FPS=1 / RES_FOV=<f>: port/patches.cpp, once tools/r3_survey.py
# --write-insn has generated the patch words for your EBOOT and it was lifted
# again.
#
# RES_LEVEL=<n> passes "-level <n>" to the game (PS3_ARGV); whether this
# EBOOT honours it is not known yet.
#
# Needs the build from tools/rebuild.sh and the disc; see tools/env.sh for the
# paths and overrides.
here=${0:A:h}; source "$here/env.sh"
[ -x "$B" ] || { echo "no build at $B: run tools/rebuild.sh first" >&2; exit 1; }
[ -r "$E" ] || { echo "no $E: run tools/rebuild.sh first" >&2; exit 1; }
res_disc || exit 1
if [ ! -x "$L" ]; then
    echo "building the game window ($L)..."
    cmake --build "$RES_BUILD/$RES_TITLE_ID" --target Resistance >&2 && [ -x "$L" ] ||
        { echo "could not build $L (tools/rebuild.sh build)" >&2; exit 1; }
fi

{   # read whole before running: editing this file mid-session cannot derail it
mkdir -p "$RES_DATA/dev_hdd0" "$RES_DATA/dev_hdd1" "$RES_DATA/logs"; cd "$RES_DATA" || exit 1
LOG=$RES_DATA/last.log
# The previous session's log moves to logs/session-<date>.log; the 10 newest
# are kept.
[ -s "$LOG" ] && mv "$LOG" "$RES_DATA/logs/session-$(stat -f %Sm -t %Y%m%d-%H%M%S "$LOG").log"
ls -t "$RES_DATA/logs"/session-*.log 2>/dev/null | tail -n +11 | while IFS= read -r old; do rm -f "$old"; done
[ -n "$RES_LEVEL" ] && export PS3_ARGV="-level;$RES_LEVEL"
echo "Disc: $PS3_VFS_ROOT"
echo "Saves: $RES_DATA"
echo "Log: $LOG"

# On by default, each off with VAR=0:
#   PS3_TELEMETRY       a [tele] line a second (frames, draws in the last
#                       frame) and, once per stall, every guest thread's lr
#                       when no frame came for 3 s
#   RSX_DRAIN_SPIKE_MS  every FIFO pass of 100 ms or more, with what the draw
#                       engine spent it on
#   PS3_SHADER_CACHE    shader translations kept across sessions (shadercache/)
#   PS3_SHADER_ASYNC    new shaders built in the background: a new object may
#                       be missing for a frame or two instead of the frame
#                       stalling for 30-500 ms
#   PS3RECOMP_FP_UNNORM_VOL  volume textures sampled in texel coordinates are
#                       scaled as volumes (Resistance 2's Moonpool effects)
# RES_DEBUG=1: the diagnostics the port is being brought up with -- where the
# SPU code runs interpreted (SPU_INTERP_STATS), what each SPURS policy module
# is doing (SPURS_PM_DUMP), which firmware calls are hot (PS3_HLE_TOP) and
# where SPU code is loaded from (SPU_GET_RANGE_LOG) -- and, when the game
# exits, logs/summary-<time>.txt with the lines that matter out of last.log.
# Each can still be set on its own.
if [ -n "$RES_DEBUG" ] && [ "$RES_DEBUG" != 0 ]; then
    export SPU_INTERP_STATS=${SPU_INTERP_STATS:-10} SPURS_PM_DUMP=${SPURS_PM_DUMP:-30}
    export PS3_HLE_TOP=${PS3_HLE_TOP:-60} SPU_GET_RANGE_LOG=${SPU_GET_RANGE_LOG:-D70000-1012000}
    echo "Debug: on (summary written to $RES_DATA/logs when the game exits)"
fi
unset PS3RECOMP_METAL_HEADLESS
PS3_HDD0_ROOT=$RES_DATA/dev_hdd0 PS3_HDD1_ROOT=$RES_DATA/dev_hdd1 \
PS3RECOMP_METAL_FPS=1 PS3_PAD_LOG=${PS3_PAD_LOG:-1} \
PS3_TELEMETRY=${PS3_TELEMETRY:-1} RSX_DRAIN_SPIKE_MS=${RSX_DRAIN_SPIKE_MS:-100} \
PS3RECOMP_ENG_VCACHE_STATS=${PS3RECOMP_ENG_VCACHE_STATS:-1} \
PS3RECOMP_FP_UNNORM_VOL=${PS3RECOMP_FP_UNNORM_VOL:-1} \
PS3_EXIT_REQUEST_MS=${PS3_EXIT_REQUEST_MS:-2000} \
PS3_SHADER_CACHE=${PS3_SHADER_CACHE:-$RES_DATA/shadercache} PS3_SHADER_ASYNC=${PS3_SHADER_ASYNC:-1} \
    caffeinate -i "$L" "$B" "$E" > "$LOG.raw" 2>&1 &
game=$!
# Every log line starts with the seconds since launch ([  123.45]).
perl -MTime::HiRes=time -e '$|=1; $t0=time; open(my $in, "<", $ARGV[0]) or exit 1;
    for (;;) { while (my $l = <$in>) { printf "[%8.2f] %s", time-$t0, $l }
               last if !kill(0, $ARGV[1]) && eof($in); select(undef,undef,undef,0.2); seek($in,0,1) }' \
    "$LOG.raw" "$game" > "$LOG" &
stamp=$!
wait $game; st=$?
wait $stamp; rm -f "$LOG.raw"
echo "The game exited (status $st). Log: $LOG"
if [ -n "$RES_DEBUG" ] && [ "$RES_DEBUG" != 0 ]; then
    SUM=$RES_DATA/logs/summary-$(date +%Y%m%d-%H%M%S).txt
    {
        echo "== exit status $st, $(date)"
        echo "== crashes";            grep -E 'killed by signal|SIGSEGV|SIGBUS|fatal|abort' "$LOG" | head -20
        echo "== frame rate (every 10 s)"; grep -F '[tele]' "$LOG" | awk 'NR % 10 == 1' | cut -c1-170
        echo "== levels and movies";  grep -E 'fs\] open .*(levels|movies)' "$LOG" | cut -c1-170 | uniq | head -60
        echo "== dialogs and saves";  grep -E 'cellMsgDialog\] Open|DIALOG\]|cellSaveData\] (SAVE|LOAD) dir' "$LOG" | head -40
        echo "== main thread when stuck"; grep -F 'guest-tid 1 ' "$LOG" | tail -5
        echo "== unresolved firmware calls"; grep -o 'unresolved NID 0x[0-9A-F]*' "$LOG" | sort | uniq -c | sort -rn | head -20
        echo "== SPU code interpreted"; grep -E 'spu-interp\]|spu-interp-hot' "$LOG" | tail -12 | cut -c1-200
        echo "== SPU code loaded";    grep -F '[get-range]' "$LOG" | cut -c1-160 | head -80
        echo "== policy modules (last)"; grep -F '[pm-dump]' "$LOG" | tail -8 | cut -c1-200
        echo "== hot firmware calls"; grep -A12 -F -- '--- HLE calls' "$LOG" | tail -14 | cut -c1-160
        echo "== last 40 lines";      tail -40 "$LOG" | cut -c1-200
    } > "$SUM" 2>/dev/null
    echo "Debug summary: $SUM"
fi
exit $st
}
