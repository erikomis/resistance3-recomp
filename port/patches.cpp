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
#include <chrono>
#include <cstdlib>
#include <string>
#include <thread>
#include <vector>
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

/* RES_PEEK=<hex addr>:<bytes>[,<hex addr>:<bytes>...]: a debugging aid. A
 * host thread prints those guest ranges as big-endian words every
 * RES_PEEK_MS (default 2000) ms, when they changed since the last print, for
 * the first RES_PEEK_MAX (default 60) prints, starting RES_PEEK_FROM seconds
 * in (default 0). For watching a job queue or a flag a thread waits on
 * without stopping the game. */
static void peek_thread(std::string spec, unsigned ms)
{
    const char* mx = getenv("RES_PEEK_MAX");
    const char* from = getenv("RES_PEEK_FROM");
    const int max_prints = mx ? atoi(mx) : 60;
    if (from) std::this_thread::sleep_for(std::chrono::seconds(atoi(from)));
    /* An entry is <hex addr>:<bytes>, or a pointer chain
     * *<hex addr>[+<hex off>...]:<bytes> -- each '+' first loads the u32 at
     * the address so far, then adds the offset (resolved again every
     * print): *11FD31C+10+200:96 is *(*(0x11FD31C)+0x10)+0x200. */
    struct Range { uint32_t addr, len; std::vector<uint8_t> last; std::vector<uint32_t> chain; };
    std::vector<Range> ranges;
    for (size_t at = 0; at < spec.size();) {
        size_t end = spec.find(',', at);
        std::string one = spec.substr(at, end == std::string::npos ? std::string::npos : end - at);
        unsigned a = 0, n = 0;
        if (!one.empty() && one[0] == '*') {
            std::vector<uint32_t> chain;
            size_t colon = one.find(':');
            if (colon == std::string::npos) { at = end == std::string::npos ? spec.size() : end + 1; continue; }
            std::string path = one.substr(1, colon - 1);
            n = (unsigned)atoi(one.c_str() + colon + 1);
            size_t q = 0;
            while (q <= path.size()) {
                size_t plus = path.find('+', q);
                chain.push_back((uint32_t)strtoul(path.substr(q, plus == std::string::npos ? std::string::npos : plus - q).c_str(), nullptr, 16));
                if (plus == std::string::npos) break;
                q = plus + 1;
            }
            if (n && n <= 4096 && chain.size() >= 2) ranges.push_back({0, (n + 3) & ~3u, {}, chain});
        } else if (sscanf(one.c_str(), "%x:%u", &a, &n) == 2 && n && n <= 4096)
            ranges.push_back({a & ~3u, (n + 3) & ~3u, {}, {}});
        if (end == std::string::npos) break;
        at = end + 1;
    }
    for (int printed = 0; printed < max_prints;) {
        std::this_thread::sleep_for(std::chrono::milliseconds(ms));
        for (Range& r : ranges) {
            if (!r.chain.empty()) {
                uint32_t p = r.chain[0];
                for (size_t k = 1; k < r.chain.size(); k++) {
                    const uint8_t* b = vm_base + (p & ~3u);
                    p = ((uint32_t)b[0] << 24 | (uint32_t)b[1] << 16 | (uint32_t)b[2] << 8 | b[3]) + r.chain[k];
                }
                if (!p || p >= 0xF0000000u) continue;
                r.addr = p & ~3u;
            }
            std::vector<uint8_t> now(vm_base + r.addr, vm_base + r.addr + r.len);
            if (now == r.last) continue;
            r.last = now;
            printed++;
            for (uint32_t o = 0; o < r.len; o += 32) {
                char line[160];
                int k = snprintf(line, sizeof line, "[peek] %08X:", r.addr + o);
                for (uint32_t i = o; i < o + 32 && i < r.len; i += 4)
                    k += snprintf(line + k, sizeof line - k, " %02X%02X%02X%02X",
                                  now[i], now[i + 1], now[i + 2], now[i + 3]);
                fprintf(stderr, "%s\n", line);
            }
        }
    }
}

extern "C" void res_apply_patches(void)
{
    if (const char* peek = getenv("RES_PEEK")) {
        const char* ms = getenv("RES_PEEK_MS");
        if (vm_base && *peek)
            std::thread(peek_thread, std::string(peek), ms ? (unsigned)atoi(ms) : 2000u).detach();
    }
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
