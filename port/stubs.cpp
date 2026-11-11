/*
 * ps3recomp game project -- game-specific hooks and overrides.
 *
 * main.cpp is the runner and is game-agnostic. This file is where a port puts
 * everything that is not: the PRX loading hook it must answer, overrides for
 * firmware functions the HLE library gets wrong for this title, and patches
 * over recompiled code.
 *
 * Resistance 3 (BCUS98176) starts here empty. Resistance 2 was a single ELF
 * (the EBOOT fronts the whole game); Resistance: Fall of Man exitspawns into
 * game.self, and its stubs.cpp has the sys_game_process_exitspawn hand-off.
 * tools/r3_survey.py lists the .self/.sprx the EBOOT names; if Resistance 3
 * spawns one, that hand-off comes over from the Resistance 1 port. As the boot
 * log reveals unimplemented NIDs or HLE mismatches, they land in this file.
 */

#include <cstdio>
#include <cstring>

#include "ps3emu/ps3types.h"
#include "ps3emu/error_codes.h"

/* ---------------------------------------------------------------------------
 * PRX loading
 *
 * main.cpp calls this once, after the lifted function table is registered and
 * vm_base is live, before the game runs. A title that lifts a real system PRX
 * -- libsre, which is cellSpurs and cellSync -- loads its image into guest RAM
 * here and registers its exports. Most ports never need to: the HLE library
 * answers those modules instead.
 * -----------------------------------------------------------------------*/

extern "C" void ps3_load_prx_modules(void)
{
}
