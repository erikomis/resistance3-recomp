/*
 * Resistance 3 port: optional game patches and compatibility hooks.
 *
 * The community patches RPCS3 ships in its patch.yml for this game, carried
 * over to the static recompilation the way the Resistance: Fall of Man port
 * carries its own. All are off unless asked for:
 *
 *   RES_UNLOCK_FPS=1   "Unlock FPS" (Whatcookie, boma): the 30 fps cap off.
 *                      patch.yml's note: the frame rate is bounded by the
 *                      vblank rate, and above ~75 fps the left stick and
 *                      some actions (ladders) misbehave, so the frame clock's
 *                      default 62.5 Hz is kept; PS3_VBLANK_HZ overrides it.
 *   RES_FOV=<float>    "Extended FOV" (illusion): the field-of-view value
 *                      (RPCS3's patch writes 0.7; the game's own value is
 *                      in the generated header's comment).
 *
 * A patch is two halves. The data half is written into guest memory here,
 * after the ELF is loaded and before the guest starts. The code half cannot
 * be: a static recompilation never executes the guest's code words. Those
 * instructions are lifted in both forms instead (ppu_lifter.py
 * --insn-patches port/patches/eboot_<version>.insn.json, which
 * tools/rebuild.sh passes when the file exists), and the lifted code picks
 * one by g_res_unlock_fps.
 *
 * Both halves are generated from the player's own EBOOT by
 * tools/r3_survey.py --write-insn port/patches: eboot_<version>.insn.json
 * and eboot_<version>.words.h, the original words this file checks before it
 * writes anything. A version without its header (or an EBOOT whose words
 * differ) gets nothing.
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "ppu_recomp.h"

extern "C" {
extern uint8_t* vm_base;
/* Read by the lifted code at the patched instructions. */
int g_res_unlock_fps = 0;
/* The vblank rate this process's patches want (0 = the frame clock's own
 * default); PS3_VBLANK_HZ still wins. Read by main.cpp's frame clock. */
double g_res_vblank_hz = 0.0;
void ps3_hle_register_ctx(uint32_t, const char*, void (*)(ppu_context*));
}

namespace {

struct R3Word { uint32_t addr, value; };

#if __has_include("patches/eboot_100.words.h")
#include "patches/eboot_100.words.h"
#endif
#if __has_include("patches/eboot_105.words.h")
#include "patches/eboot_105.words.h"
#endif

struct PatchSet {
    const char*   name;
    const R3Word* sig;          /* all must match, or the set is not applied */
    size_t        nsig;
    const R3Word* unlock_data;  /* {0,0}-terminated */
    uint32_t      fov;          /* the FOV float's address */
};

const PatchSet kSets[] = {
#ifdef R3_HAVE_SET_100
    {"EBOOT 01.00", kR3Sig_100, sizeof kR3Sig_100 / sizeof *kR3Sig_100, kR3UnlockData_100, kR3Fov_100},
#endif
#ifdef R3_HAVE_SET_105
    {"EBOOT 01.05", kR3Sig_105, sizeof kR3Sig_105 / sizeof *kR3Sig_105, kR3UnlockData_105, kR3Fov_105},
#endif
    {nullptr, nullptr, 0, nullptr, 0},
};

uint32_t rd32(uint32_t a)
{
    const uint8_t* p = vm_base + a;
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}

void wr32(uint32_t a, uint32_t v)
{
    uint8_t* p = vm_base + a;
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}

void wrf32(uint32_t a, float f)
{
    uint32_t v;
    memcpy(&v, &f, 4);
    wr32(a, v);
}

bool matches(const R3Word* w, size_t n)
{
    for (size_t i = 0; i < n; i++)
        if (rd32(w[i].addr) != w[i].value) return false;
    return true;
}

bool env_on(const char* name)
{
    const char* e = getenv(name);
    return e && *e && strcmp(e, "0") != 0;
}

/* Carried from the Resistance 2 port (same engine; not yet seen in a
 * Resistance 3 log): cellHttpClientPollConnections is otherwise unresolved
 * and returns a fake success without a transaction ID, and the game's HTTP
 * service then polled it at full CPU speed. Report "unavailable" so its
 * retry path sleeps. RES_HTTP_POLL_COMPAT=0 turns it off. */
void http_poll_unavailable(ppu_context* ctx)
{
    ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)0x80710026u;
}

}  // namespace

/* Apply what the environment asks for to the ELF just loaded. */
extern "C" void res_apply_patches(void)
{
    const char* http = getenv("RES_HTTP_POLL_COMPAT");
    if (!(http && http[0] == '0'))
        ps3_hle_register_ctx(0xADC0A4B2u, "cellHttpClientPollConnections (unavailable)",
                             http_poll_unavailable);

    const bool unlock = env_on("RES_UNLOCK_FPS");
    const char* fov_s = getenv("RES_FOV");
    if (!vm_base || (!unlock && !(fov_s && *fov_s))) return;

    for (const PatchSet* ps = kSets; ps->name; ps++) {
        if (!matches(ps->sig, ps->nsig)) continue;
        if (unlock) {
            g_res_unlock_fps = 1;
            for (const R3Word* w = ps->unlock_data; w->addr; w++) wr32(w->addr, w->value);
            fprintf(stderr, "[patch] %s: unlock fps%s\n", ps->name,
                    getenv("PS3_VBLANK_HZ") ? "" : " (vblank stays 62.5 Hz: PS3_VBLANK_HZ to change)");
        }
        if (fov_s && *fov_s) {
            const float f = (float)atof(fov_s);
            if (f > 0.1f && f < 4.0f) {
                wrf32(ps->fov, f);
                fprintf(stderr, "[patch] %s: fov %.3f\n", ps->name, f);
            } else {
                fprintf(stderr, "[patch] RES_FOV=%s ignored (0.1 .. 4)\n", fov_s);
            }
        }
        return;
    }
    fprintf(stderr, "[patch] RES_UNLOCK_FPS/RES_FOV: no patch set matches this ELF "
                    "(tools/r3_survey.py --write-insn port/patches, then re-lift); nothing applied\n");
}
