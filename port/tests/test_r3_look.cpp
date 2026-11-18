/* port/r3_look.cpp: the turn math (a yaw toward the right row, a pitch
 * toward up, clamped, rows kept a level rotation), the zoom factor, and when
 * the hook takes the motion or leaves it to the stick, on a fake guest.
 *
 *   clang++ -std=c++17 port/tests/test_r3_look.cpp -o /tmp/test_r3_look && /tmp/test_r3_look
 */
#include <cassert>
#include <cstdlib>

static int (*g_look)(double, double);
static int (*g_menu)(void);
extern "C" void cellPad_set_look_hook(int (*f)(double, double)) { g_look = f; }
extern "C" void cellPad_set_menu_query(int (*f)(void)) { g_menu = f; }
extern "C" { uint8_t* vm_base; }

#include "../r3_look.cpp"

static bool close(double a, double b, double t = 1e-4) { return std::fabs(a - b) < t; }
static double deg(double r) { return r * 180.0 / M_PI; }

static void stf(uint32_t a, float f) { uint32_t w; memcpy(&w, &f, 4); st32(a, w); }

static void test_turn_math()
{
    /* Facing +z; the first row (the hero's left) is (f.z, 0, -f.x), as in the
     * game, where a turn to the right lowers atan2(f.x, f.z). */
    V3 r{1, 0, 0}, u{0, 1, 0}, f{0, 0, 1};
    r3_turn(r, u, f, 90, 0);
    assert(close(f.x, -1) && close(f.z, 0) && close(r.z, 1));    /* right: forward went opposite the first row */
    r3_turn(r, u, f, -90, 0);
    assert(close(f.z, 1) && close(r.x, 1));
    r3_turn(r, u, f, 0, 30);
    assert(close(deg(std::asin(f.y)), 30) && close(u.y, std::cos(M_PI / 6)) && close(r.y, 0));
    assert(is_rotation(r, u, f, 1e-6));
    r3_turn(r, u, f, 37, 200);                                    /* clamped */
    assert(close(deg(std::asin(f.y)), kPitchMax) && is_rotation(r, u, f, 1e-6) && u.y > 0);
    r3_turn(r, u, f, 0, -500);
    assert(close(deg(std::asin(f.y)), -kPitchMax) && u.y > 0);
    /* Many small turns: no drift. */
    V3 r2{0.8, 0, 0.6}, u2{0, 1, 0}, f2{0.6, 0, -0.8};
    for (int i = 0; i < 3600; i++) r3_turn(r2, u2, f2, 0.1, (i & 1) ? 0.05 : -0.05);
    assert(is_rotation(r2, u2, f2, 1e-6) && close(f2.x, 0.6, 1e-3) && close(f2.z, -0.8, 1e-3));
}

/* A hero at the camera, in the game, facing +z. */
constexpr uint32_t kHero = 0x00200000u;
static void stage(void)
{
    memset(vm_base + kHero, 0, 0x400);
    st32(kHeroSlots[0], 0); st32(kHeroSlots[1], kHero);
    stv(kHero + kHeroRows, {1, 0, 0}); stv(kHero + kHeroRows + 16, {0, 1, 0}); stv(kHero + kHeroRows + 32, {0, 0, 1});
    stv(kCamera + 32, {0, 0, 1}); stv(kCamera + 48, {5, 11.6f, 7}); stv(kHeroFeet, {5, 10, 7});
    vm_base[kMenuFlag] = 0; vm_base[kPressStart] = 0;
    stf(kViewFov, 74);
    s_wrote_hero = 0;
}

static void test_hook()
{
    vm_base = (uint8_t*)calloc(1, 0x01600000);
    r3_look_init();
    assert(g_look && g_menu);
    uint32_t rows; V3 r, u, f;

    stage();
    assert(g_look(10, 5) == 1);
    f = ldv(kHero + kHeroRows + 32);
    assert(close(deg(std::atan2(f.x, f.z)), -10, 1e-3) && close(deg(std::asin(f.y)), 5, 1e-3));
    /* The camera has not followed yet: our own rows still count. */
    assert(g_look(10, 0) == 1);
    /* Someone else turned the rows away from the camera: a cutscene. */
    stv(kHero + kHeroRows, {-1, 0, 0}); stv(kHero + kHeroRows + 32, {0, 0, -1});
    assert(g_look(1, 0) == 0);

    stage(); vm_base[kMenuFlag] = 1;
    assert(g_look(1, 0) == 0 && g_menu() == 1);
    vm_base[kPressStart] = 1;                       /* "Press START": START it is */
    assert(g_menu() == 0);
    stage(); stv(kCamera + 48, {50, 11, 7});        /* camera away from the hero */
    assert(g_look(1, 0) == 0);
    stage(); st32(kHeroSlots[1], 0);                /* no hero */
    assert(g_look(1, 0) == 0);
    stage(); stv(kHero + kHeroRows + 32, {0, 0, 2}); /* not a rotation */
    assert(r3_look_rows(&rows, &r, &u, &f) != nullptr);

    /* Aiming at 60.2 degrees: the turn is tan(30.1)/tan(37) of the hip's. */
    stage(); stf(kViewFov, 60.2f);
    const double k = std::tan(30.1 * M_PI / 180) / std::tan(37 * M_PI / 180);
    assert(close(r3_zoom_scale(), k, 1e-5));
    assert(g_look(10, 0) == 1);
    f = ldv(kHero + kHeroRows + 32);
    assert(close(deg(std::atan2(f.x, f.z)), -10 * k, 1e-3));
    stf(kViewFov, 74);
    assert(r3_zoom_scale() == 1.0);
}

int main()
{
    test_turn_math();
    test_hook();
    printf("test_r3_look: ok\n");
    return 0;
}
