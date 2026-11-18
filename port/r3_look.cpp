/*
 * Resistance 3 port: the mouse turns the view directly, and the keyboard
 * knows when a menu is up (cellPad_set_look_hook, cellPad_set_menu_query).
 *
 * The game keeps the player's view as the hero object's orientation: three
 * rows (right, up, forward; big-endian floats, 16 bytes apart) at
 * hero+0x370 (the first row points to the hero's left as the game turns
 * it). It has no separate yaw or pitch; each frame it turns those rows
 * by the right stick and copies them into the camera. So a mouse turn is
 * written straight into the rows: a yaw about the world's up and a pitch in
 * the forward/up plane, clamped short of straight up or down. A stick asks
 * for a turn rate, which the game caps (about 206 degrees/s across) and
 * ramps; written rows have neither. The rows are only taken when they are a
 * level rotation and the camera sits at the hero's eyes looking the hero's
 * way, so menus, cutscenes and deaths leave the motion to the stick.
 *
 * Guest addresses (EBOOT 01.00 BCUS98176; checked at run time with the
 * R3_LOOK_SCAN / R3_LOOK_SNAP / R3_LOOK_LOG aids below, see each constant):
 *
 * Knobs:
 *   R3_MOUSE_LOOK=0     no look hook: the mouse is the right stick
 *   R3_ZOOM_SENS=<f>    while aiming, scale the turn by
 *                       (tan(fov/2)/tan(hipfov/2))^f: 1 (default) keeps what
 *                       the mouse sweeps across the screen, 0 is off
 *   R3_MENU_QUERY=0     Return/Escape stay START in menus, capture stays
 *   R3_LOOK_LOG=<ms>    print the look state every <ms> ms
 *
 * Discovery aids:
 *   R3_LOOK_SCAN=<s>[,<s>...]  at those seconds after start, print hero
 *          candidates (a data word pointing to an object with a rotation at
 *          +0x370), camera candidates (rotation + position rows in the data
 *          segment) and data floats that read like a field of view;
 *   R3_LOOK_SNAP=<s>,<s>,<s>   snapshot the data segment three times and
 *          print the bytes equal at the first and third and different at the
 *          second, all 0 or 1 (game, pause menu, game: the menu flag).
 */

#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include <mach/mach.h>
#include <mach/mach_vm.h>

extern "C" {
extern uint8_t* vm_base;
void cellPad_set_look_hook(int (*look)(double yaw_deg, double pitch_deg));
void cellPad_set_menu_query(int (*in_menu)(void));
}

namespace {

constexpr uint32_t kDataLo = 0x00EC0000u, kDataHi = 0x015842A8u;   /* EBOOT 01.00's data + bss */

uint32_t ld32(uint32_t a)
{
    const uint8_t* p = vm_base + a;
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}

float ldf(uint32_t a)
{
    const uint32_t w = ld32(a);
    float f;
    memcpy(&f, &w, 4);
    return f;
}

struct V3 { double x, y, z; };
V3 ldv(uint32_t a) { return { ldf(a), ldf(a + 4), ldf(a + 8) }; }
double dot(const V3& a, const V3& b) { return a.x * b.x + a.y * b.y + a.z * b.z; }

/* The guest's mapped ranges (EA), for reading through pointers safely. */
struct Range { uint32_t lo, hi; };
std::vector<Range> mapped_ranges()
{
    std::vector<Range> out;
    mach_vm_address_t addr = (mach_vm_address_t)vm_base;
    const mach_vm_address_t end = (mach_vm_address_t)vm_base + 0x100000000ull;
    while (addr < end) {
        mach_vm_size_t size = 0; natural_t depth = 1;
        vm_region_submap_info_data_64_t info; mach_msg_type_number_t cnt = VM_REGION_SUBMAP_INFO_COUNT_64;
        if (mach_vm_region_recurse(mach_task_self(), &addr, &size, &depth,
                                   (vm_region_recurse_info_t)&info, &cnt) != KERN_SUCCESS) break;
        if (addr >= end) break;
        mach_vm_address_t a1 = addr + size > end ? end : addr + size;
        const mach_vm_address_t a0 = addr < (mach_vm_address_t)vm_base ? (mach_vm_address_t)vm_base : addr;
        if ((info.protection & VM_PROT_READ) && !info.is_submap) {
            const uint32_t lo = (uint32_t)(a0 - (mach_vm_address_t)vm_base);
            const uint32_t hi = (uint32_t)(a1 - (mach_vm_address_t)vm_base - 1);
            if (!out.empty() && out.back().hi + 1 == lo) out.back().hi = hi;
            else out.push_back({lo, hi});
        }
        addr = a1;
    }
    return out;
}

bool in_ranges(const std::vector<Range>& rs, uint32_t a, uint32_t len)
{
    for (const Range& r : rs)
        if (a >= r.lo && a + len - 1 <= r.hi && a + len - 1 >= a) return true;
    return false;
}

bool is_rotation(const V3& r, const V3& u, const V3& f, double t)
{
    for (const V3* v : { &r, &u, &f })
        if (!(std::fabs(dot(*v, *v) - 1.0) < t)) return false;
    return std::fabs(dot(r, u)) < t && std::fabs(dot(r, f)) < t && std::fabs(dot(u, f)) < t;
}

void scan_once(double t)
{
    const std::vector<Range> rs = mapped_ranges();
    fprintf(stderr, "[r3look] scan t=%.0f s (%zu mapped ranges)\n", t, rs.size());
    int n = 0;
    for (uint32_t s = kDataLo; s < kDataHi && n < 120; s += 4) {
        const uint32_t o = ld32(s);
        if (!o || (o & 15) || !in_ranges(rs, o + 0x370, 0x40)) continue;
        const V3 r = ldv(o + 0x370), u = ldv(o + 0x380), f = ldv(o + 0x390);
        if (!is_rotation(r, u, f, 0.02) || std::fabs(r.y) > 0.02 || u.y <= 0.0) continue;
        if (std::fabs(f.y) < 1e-6 && std::fabs(u.y - 1.0) < 1e-6 && f.z == 1.0) continue;   /* identity */
        const V3 p = ldv(o + 0x3A0);
        fprintf(stderr, "[r3look] hero? slot %08X -> %08X f=(%.4f %.4f %.4f) u.y=%.4f p+3A0=(%.2f %.2f %.2f)\n",
                s, o, f.x, f.y, f.z, u.y, p.x, p.y, p.z);
        n++;
    }
    n = 0;
    for (uint32_t a = kDataLo; a + 0x40 <= kDataHi && n < 200; a += 16) {
        const V3 r = ldv(a), u = ldv(a + 16), f = ldv(a + 32);
        if (!is_rotation(r, u, f, 0.01) || std::fabs(r.y) > 0.02) continue;
        if (r.x == 1.0 && u.y == 1.0) continue;   /* identity */
        const V3 p = ldv(a + 48);
        if (!(std::fabs(p.x) < 1e5 && std::fabs(p.y) < 1e5 && std::fabs(p.z) < 1e5)) continue;
        fprintf(stderr, "[r3look] cam? %08X f=(%.4f %.4f %.4f) p=(%.2f %.2f %.2f) +150=%.3f\n",
                a, f.x, f.y, f.z, p.x, p.y, p.z, ldf(a + 0x150));
        n++;
    }
    n = 0;
    for (uint32_t a = kDataLo; a < kDataHi && n < 200; a += 4) {
        const float v = ldf(a);
        if (v == 74.0f || v == 70.0f || v == 60.0f || v == 65.0f || v == 75.0f || v == 80.0f) {
            fprintf(stderr, "[r3look] fov? %08X = %.3f\n", a, v);
            n++;
        }
    }
}

void scan_thread(std::string spec)
{
    const auto t0 = std::chrono::steady_clock::now();
    for (const char* p = spec.c_str(); *p;) {
        const double t = strtod(p, (char**)&p);
        while (*p == ',' || *p == ' ') p++;
        std::this_thread::sleep_until(t0 + std::chrono::milliseconds((long long)(t * 1000)));
        scan_once(t);
    }
}

void snap_thread(std::string spec)
{
    const auto t0 = std::chrono::steady_clock::now();
    double ts[3] = {0, 0, 0};
    sscanf(spec.c_str(), "%lf,%lf,%lf", &ts[0], &ts[1], &ts[2]);
    std::vector<uint8_t> s[3];
    for (int i = 0; i < 3; i++) {
        std::this_thread::sleep_until(t0 + std::chrono::milliseconds((long long)(ts[i] * 1000)));
        s[i].assign(vm_base + kDataLo, vm_base + kDataHi);
        fprintf(stderr, "[r3look] snap %d at %.0f s\n", i, ts[i]);
    }
    int n = 0;
    for (size_t i = 0; i < s[0].size() && n < 400; i++) {
        if (s[0][i] != s[2][i] || s[0][i] == s[1][i] || s[0][i] > 1 || s[1][i] > 1) continue;
        fprintf(stderr, "[r3look] flag? %08X %u -> %u -> %u\n", (unsigned)(kDataLo + i), s[0][i], s[1][i], s[2][i]);
        n++;
    }
    fprintf(stderr, "[r3look] snap diff: %d byte(s)\n", n);
}


/* ---- the look hook ---------------------------------------------------- */

/* Data-segment globals, the same in BCUS98176 01.00 as in the EU disc a
 * GPL port documents; each was checked here before use (R3_LOOK_SCAN,
 * R3_LOOK_SNAP, R3_LOOK_LOG and the scripted turns). */
constexpr uint32_t kHeroSlots[] = { 0x0112336Cu, 0x011E0A68u };  /* the hero object (either; one is cleared on death) */
constexpr uint32_t kHeroRows    = 0x370u;       /* right, up, forward in it */
constexpr uint32_t kCamera      = 0x0105B4A0u;  /* view matrix: right, up, forward, position */
constexpr uint32_t kViewFov     = 0x0105B5F0u;  /* the view's horizontal field of view, degrees */
constexpr uint32_t kHeroFeet    = 0x01069950u;  /* the hero's position (feet) */
constexpr uint32_t kMenuFlag    = 0x00F09020u;  /* byte: 1 while a menu is up */
constexpr uint32_t kPressStart  = 0x00F08EBCu;  /* byte: 1 up to the "Press START" screen */

constexpr double kHipFov    = 74.0;
constexpr double kPitchMax  = 80.0;   /* degrees; the game's own clamp is a little wider */
constexpr double kRowTol    = 0.02;

void st32(uint32_t a, uint32_t v)
{
    uint8_t* p = vm_base + a;
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}

void stv(uint32_t a, const V3& v)
{
    const float f[3] = { (float)v.x, (float)v.y, (float)v.z };
    for (int i = 0; i < 3; i++) {
        uint32_t w;
        memcpy(&w, &f[i], 4);
        st32(a + 4 * i, w);
    }
}

double env_num(const char* name, double def)
{
    const char* e = getenv(name);
    return e && *e ? strtod(e, nullptr) : def;
}

int r3_in_menu(void)
{
    return vm_base[kMenuFlag] == 1 && vm_base[kPressStart] == 0;
}

/* The hero object, or 0. A pointer is checked against the guest's mapped
 * memory once, then trusted while it stays the same. */
uint32_t r3_hero()
{
    static uint32_t known;
    for (const uint32_t slot : kHeroSlots) {
        const uint32_t o = ld32(slot);
        if (!o) continue;
        if (o == known) return o;
        if ((o & 15) || o < 0x10000u || o > 0xE0000000u) return 0;
        if (!in_ranges(mapped_ranges(), o + kHeroRows, 0x30)) return 0;
        known = o;
        return o;
    }
    return 0;
}

V3 s_wrote_f;          /* the forward row this hook wrote last (pad thread) */
uint32_t s_wrote_hero;

/* Why the view is not the hero's to turn now, or nullptr. */
const char* r3_look_rows(uint32_t* rows, V3* r, V3* u, V3* f)
{
    if (r3_in_menu()) return "menu";
    const uint32_t hero = r3_hero();
    if (!hero) return "no hero";
    *rows = hero + kHeroRows;
    *r = ldv(*rows); *u = ldv(*rows + 16); *f = ldv(*rows + 32);
    if (!is_rotation(*r, *u, *f, kRowTol)) return "not a rotation";
    if (std::fabs(r->y) > kRowTol || u->y <= 0.1) return "rolled";
    const V3 cp = ldv(kCamera + 48), feet = ldv(kHeroFeet), cf = ldv(kCamera + 32);
    const double up = cp.y - feet.y;
    if (std::hypot(cp.x - feet.x, cp.z - feet.z) > 1.5 || !(up > -0.5 && up < 2.5)) return "camera away";
    /* The camera follows the rows a frame later; the pad is read several
     * times a frame, so rows this hook just wrote need not match it yet. */
    const bool ours = hero == s_wrote_hero && f->x == (float)s_wrote_f.x && f->y == (float)s_wrote_f.y &&
                      f->z == (float)s_wrote_f.z;
    if (!ours && !(dot(cf, *f) > 0.5)) return "camera elsewhere";
    return nullptr;
}

/* While aiming the view narrows; the turn narrows with it. */
double r3_zoom_scale()
{
    static const double k = std::fmax(0.0, std::fmin(2.0, env_num("R3_ZOOM_SENS", 1.0)));
    const double fov = ldf(kViewFov);
    if (k == 0.0 || !(fov > 5.0 && fov < kHipFov - 0.1)) return 1.0;
    const double h = M_PI / 360.0;
    return std::pow(std::tan(fov * h) / std::tan(kHipFov * h), k);
}

/* Yaw about the world's up, then pitch toward the up row; the rows are
 * rebuilt from the new forward so they stay a rotation. A turn to the right
 * (as the stick's: measured, the stick held right lowers atan2(f.x, f.z))
 * takes forward away from the first row, which points to the hero's left. */
void r3_turn(V3& r, V3& u, V3& f, double yaw_deg, double pitch_deg)
{
    const double d2r = M_PI / 180.0;
    double hl = std::hypot(f.x, f.z);
    V3 fh = hl > 1e-6 ? V3{ f.x / hl, 0, f.z / hl } : V3{ -u.x, 0, -u.z };   /* looking straight up/down: from up */
    hl = std::hypot(fh.x, fh.z);
    fh = { fh.x / hl, 0, fh.z / hl };
    /* r is level; its sign says which way is left. */
    V3 rh = { r.x, 0, r.z };
    const double rl = std::hypot(rh.x, rh.z);
    rh = { rh.x / rl, 0, rh.z / rl };
    rh = { rh.x - fh.x * dot(rh, fh), 0, rh.z - fh.z * dot(rh, fh) };
    const double rl2 = std::hypot(rh.x, rh.z);
    rh = { rh.x / rl2, 0, rh.z / rl2 };

    const double a = -yaw_deg * d2r, ca = std::cos(a), sa = std::sin(a);
    const V3 fh2 = { fh.x * ca + rh.x * sa, 0, fh.z * ca + rh.z * sa };
    const V3 rh2 = { rh.x * ca - fh.x * sa, 0, rh.z * ca - fh.z * sa };

    const double lim = kPitchMax * d2r;
    double p = std::asin(std::fmax(-1.0, std::fmin(1.0, f.y))) + pitch_deg * d2r;
    p = std::fmax(-lim, std::fmin(lim, p));
    const double cp = std::cos(p), sp = std::sin(p);
    f = { fh2.x * cp, sp, fh2.z * cp };
    u = { -fh2.x * sp, cp, -fh2.z * sp };
    r = rh2;
}

int r3_mouse_look(double yaw_deg, double pitch_deg)
{
    uint32_t rows;
    V3 r, u, f;
    if (r3_look_rows(&rows, &r, &u, &f)) return 0;
    const double z = r3_zoom_scale();
    r3_turn(r, u, f, yaw_deg * z, pitch_deg * z);
    stv(rows, r);
    stv(rows + 16, u);
    stv(rows + 32, f);
    s_wrote_f = f;
    s_wrote_hero = rows - kHeroRows;
    return 1;
}

void log_thread(unsigned ms)
{
    for (;;) {
        std::this_thread::sleep_for(std::chrono::milliseconds(ms));
        uint32_t rows = 0;
        V3 r{}, u{}, f{};
        const char* why = r3_look_rows(&rows, &r, &u, &f);
        const V3 cp = ldv(kCamera + 48), feet = ldv(kHeroFeet), cf = ldv(kCamera + 32);
        fprintf(stderr, "[r3look] menu=%u pstart=%u hero=%08X yaw=%.2f pitch=%.2f r=(%.3f %.3f %.3f) u.y=%.3f "
                        "camf=(%.3f %.3f %.3f) cam=(%.2f %.2f %.2f) feet=(%.2f %.2f %.2f) fov=%.2f opt=%08X %08X %08X%s%s\n",
                vm_base[kMenuFlag], vm_base[kPressStart], r3_hero(),
                std::atan2(f.x, f.z) * 180 / M_PI, std::asin(std::fmax(-1.0, std::fmin(1.0, f.y))) * 180 / M_PI,
                r.x, r.y, r.z, u.y, cf.x, cf.y, cf.z, cp.x, cp.y, cp.z, feet.x, feet.y, feet.z, ldf(kViewFov),
                ld32(0x011CB200u), ld32(0x011CB204u), ld32(0x011CB208u), why ? " no: " : "", why ? why : "");
    }
}

}  // namespace

extern "C" void r3_look_init(void)
{
    if (!vm_base) return;
    if (const char* e = getenv("R3_LOOK_SCAN")) std::thread(scan_thread, std::string(e)).detach();
    if (const char* e = getenv("R3_LOOK_SNAP")) std::thread(snap_thread, std::string(e)).detach();
    if (const char* e = getenv("R3_LOOK_LOG")) if (atoi(e) > 0) std::thread(log_thread, (unsigned)atoi(e)).detach();
    const char* look = getenv("R3_MOUSE_LOOK");
    if (!(look && look[0] == '0')) cellPad_set_look_hook(r3_mouse_look);
    const char* menu = getenv("R3_MENU_QUERY");
    if (!(menu && menu[0] == '0')) cellPad_set_menu_query(r3_in_menu);
}
