/*
 * ps3recomp game project -- entry point template.
 *
 * This is the runner. It boots a lifted title through the toolkit's PPU
 * scaffold: allocate the flat guest VM, load the PPU ELF named on the command
 * line, register the lifted function table and the HLE NID handlers, start a
 * frame clock, and dispatch the entry OPD.
 *
 * The scaffold does the work; nothing below reimplements it. ppu_load_elf,
 * ppu_recomp_register, ppu_hle_init, ppu_sysprx_register, ppu_fs_register,
 * lv2_init_syscalls and ppu_run all come from the toolkit, compiled into this
 * project from PS3RECOMP_DIR (see CMakeLists.txt). What is left here is the
 * part a port owns: which backend to present through, how the frame clock is
 * paced, and whatever diagnostics the title turns out to need.
 *
 * runtime/ppu/tests/boot_main.cpp in the toolkit is the same boot in its
 * fully-instrumented form -- crash filter, hang watchdog, guest-PC sampling
 * profiler. Read it when a boot goes wrong; copy from it what the title
 * needs. It is deliberately not what a fresh project starts with.
 *
 * The one part that IS duplicated from it is the frame clock below, because a
 * port is expected to change its pacing and a shared one would be the wrong
 * shape for that. It was copied faithfully, comments and all. If a pacing bug
 * is fixed in one of the two, look at the other.
 *
 * This builds on Windows, macOS and Linux. CI builds and runs it against the
 * boot smoke title on the last two, and compile-checks it against clang-cl on
 * the first (tools/check_ppu_scaffold.py).
 */

/* The lifter's generated header, which declares ppu_context and the function
 * table. It comes first: everything below is written against that struct. */
#include "ppu_recomp.h"

/* The Win32 names -- Sleep, GetTickCount64, CreateThread, InterlockedIncrement,
 * VirtualAlloc, the scalar typedefs -- from one place. On Windows this is a
 * passthrough to <windows.h>; off Windows the toolkit's shim supplies the same
 * names over pthreads and mmap, so the call sites below are written once. */
#include "win32_compat.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(__APPLE__)
#include <CoreFoundation/CoreFoundation.h>   /* the main thread's run loop */
#include <pthread.h>
#endif

#ifndef _WIN32
#include <sys/mman.h>   /* mmap: the guest arena, see alloc_guest_vm */
#endif

#ifdef _WIN32
/* timeBeginPeriod: <windows.h> arrives with WIN32_LEAN_AND_MEAN set, which
 * excludes the multimedia timer API, so it is asked for by name -- and after
 * windows.h, since timeapi.h uses UINT. No shim exists off Windows because
 * there is nothing to shim: the 15.6 ms default timer granularity this works
 * around is a Windows problem. */
#include <timeapi.h>
#endif

/* ---------------------------------------------------------------------------
 * What the scaffold gives this file
 * -----------------------------------------------------------------------*/
extern "C" {
uint32_t ppu_load_elf(const char* path);      /* ELF -> guest RAM, returns entry OPD */
void     ppu_recomp_register(void);           /* generated: lifted table -> address map */
void     ppu_hle_init(void);                  /* firmware import NID -> HLE handler */
void     ppu_sysprx_register(void);           /* boot-critical CRT (sys_initialize_tls, ...) */
void     ppu_fs_register(void);               /* cellFs over the real game directory */
void     lv2_init_syscalls(void);             /* the lv2 syscall table */
int      ppu_run(uint32_t entry_opd, uint32_t stack_top);
void     cellGame_init_from_paramsfo(const char* sfo_path);

/* This project's own: load whatever real system PRX modules the title needs
 * into guest RAM and register their exports. stubs.cpp has the empty version
 * a game with no lifted PRX wants. */
void     ps3_load_prx_modules(void);

extern const char* ppu_vfs_root;              /* host dir the PS3 mount points map into */

/* sys_ppu_thread.c: the main thread's stack for get_stack_information. */
extern uint32_t g_ppu_main_stack_addr;
extern uint32_t g_ppu_main_stack_size;

/* The status the guest handed to sys_process_exit. A title that exits that way
 * never returns through ppu_run, so this is only read on the path where the
 * entry function unwound instead. */
extern int     g_sys_process_exit_called;
extern int32_t g_sys_process_exit_code;

/* Host-provided symbols the runtime and the HLE libraries link against. */
uint8_t* vm_base = nullptr;
extern uint32_t ppu_vm_size;                  /* ppu_loader.cpp: the OOB guard */

/* Guest-callback dispatch. g_ps3_guest_caller is the hook the HLE runtime
 * calls back into recompiled code through -- cellSysutil events and the GCM
 * vblank/flip handlers. ppu_guest_call does the OPD -> dispatch. */
typedef void (*ps3_guest_caller_fn)(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t,
                                    uint64_t, uint64_t, uint64_t, uint64_t);
extern ps3_guest_caller_fn g_ps3_guest_caller;
uint64_t ppu_guest_call(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t,
                        uint64_t, uint64_t, uint64_t, uint64_t);

/* The GCM half of the frame clock. */
void     cellGcmTickVBlank(void);
void     cellGcmTickFlip(void);
int      cellGcm_take_flip_pending(void);
void     cellGcm_rsx_process_fifo(void);      /* drain get -> put */
unsigned cellGcm_flip_request_count(void);

/* PS3_TELEMETRY: draws in the last frame, and every guest thread's lr. */
uint32_t rsx_draw_engine_guest_draws(void);
uint64_t rsx_metal_tele_gpu_ns(void) __attribute__((weak));
#ifdef __APPLE__
void* objc_autoreleasePoolPush(void);
void  objc_autoreleasePoolPop(void* pool);
#endif
extern unsigned long long g_spu_interp_tele;
extern unsigned long long g_spu_depth_restarts;
void     ppu_report_guest_lrs(void);
}

/* ---------------------------------------------------------------------------
 * RSX present backend
 * -----------------------------------------------------------------------*/
/* D3D12 on Windows, Metal on Apple, and the null backend's headless software
 * path anywhere else -- the same selection runtime/host/host_posix.c and the
 * toolkit's boot harness make. All three expose the same three entry points,
 * so the frame clock below is backend-agnostic. */
#if defined(_WIN32)
extern "C" int  rsx_d3d12_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_d3d12_backend_present(void);
extern "C" int  rsx_d3d12_backend_pump_messages(void);
#  define rsx_backend_init    rsx_d3d12_backend_init
#  define rsx_backend_present rsx_d3d12_backend_present
#  define rsx_backend_pump    rsx_d3d12_backend_pump_messages
#  define RSX_BACKEND_NAME    "D3D12"
#elif defined(__APPLE__)
extern "C" int  rsx_metal_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_metal_backend_present(void);
extern "C" int  rsx_metal_backend_pump_messages(void);
#  define rsx_backend_init    rsx_metal_backend_init
#  define rsx_backend_present rsx_metal_backend_present
#  define rsx_backend_pump    rsx_metal_backend_pump_messages
#  define RSX_BACKEND_NAME    "Metal"
#else
extern "C" int  rsx_null_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_null_backend_present(void);
extern "C" int  rsx_null_backend_pump_messages(void);
#  define rsx_backend_init    rsx_null_backend_init
#  define rsx_backend_present rsx_null_backend_present
#  define rsx_backend_pump    rsx_null_backend_pump_messages
#  define RSX_BACKEND_NAME    "null (headless software)"
#endif

/* ---------------------------------------------------------------------------
 * Configuration
 * -----------------------------------------------------------------------*/
/* The flat VM must span every region the PS3 memory map uses, not just the
 * game image: sys_ppu_thread_create puts thread stacks at 0xD0000000, so a
 * smaller arena makes every spawned thread's stack access out of bounds. */
#define VM_SIZE       0x100010000ull   /* the full 32-bit guest space + a 64K guard */
#define STACK_TOP     0x0FF00000u      /* main-thread stack, below the 0x10000000 segment */
#define MAIN_STACK_SIZE 0x00100000u    /* what the main thread is told it has */
#define WINDOW_WIDTH  1280
#define WINDOW_HEIGHT 720
static int g_rsx_ready = 0;

/* patches.cpp: the optional game patches (RES_UNLOCK_FPS, RES_FOV) and
 * compatibility hooks, applied to the loaded ELF before the guest starts. */
extern "C" void res_apply_patches(void);
extern "C" double g_res_vblank_hz;   /* patches.cpp: the unlock-fps patch's vblank rate */

/* ---------------------------------------------------------------------------
 * Frame clock
 * -----------------------------------------------------------------------*/
/* On real hardware the RSX raises a vblank interrupt about 60 times a second
 * and that is what drives the game's frame loop. With no RSX it is synthesized
 * here: a host thread calls cellGcmTickVBlank/TickFlip, which invoke the
 * handlers the guest registered, and drains the GCM FIFO. Without this the
 * title initialises, registers its handlers and then waits forever.
 *
 * The ticks are driven off real elapsed time rather than off how long present()
 * took. A hidden or occluded window makes present block hard, and pacing the
 * ticks behind it paces the whole game behind it. */
static volatile LONG g_frames_presented = 0;

/* Frames handed to the backend at a guest FLIP boundary -- one per frame the
 * guest actually finished. The presents made before the guest's first flip, so
 * a fresh window is not left blank through a long boot, carry no guest frame
 * and are deliberately not counted. */
extern "C" unsigned ppu_boot_frames_presented(void)
{
    return (unsigned)g_frames_presented;
}

/* The window is closed and the process is ending (PS3_CLEAN_EXIT): the frame
 * clock keeps draining the FIFO and taking flips, but nothing is presented. */
static bool win_gone = false;

static void present_guest_frame(void)
{
    if (!win_gone) rsx_backend_present();
    /* This thread increments and guest threads read, so interlocked rather
     * than a volatile ++, which on arm64 is neither atomic nor a fence. */
    InterlockedIncrement(&g_frames_presented);
}

/* ---------------------------------------------------------------------------
 * Quitting: window closed, SIGTERM, SIGINT, SIGHUP
 * -----------------------------------------------------------------------*/
/* The launcher (tools/host_window) closes its window by setting `closed` in
 * the control page and sending SIGTERM, and kills the game 3 s later if it is
 * still there. It always was: SDL (cellPad's game-controller init, cellAudio's
 * audio init) installs its own SIGINT/SIGTERM handlers whenever they are at
 * SIG_DFL, and those only post an SDL_QUIT event that nothing here reads, so
 * the signal did nothing. The window closing only stopped the frame clock's
 * FIFO drain, so the guest spun on its RSX fence ("GPU sit and spin timeout")
 * until the SIGKILL. Every session ended that way, with the stdout buffer
 * (the [cellFs]/[cellSaveData]/... printf lines) lost.
 *
 * PS3_CLEAN_EXIT (default 1; =0 restores the old behaviour): the handlers are installed here first (and SDL is told to
 * keep out), and a close, from the window or from a signal, ends the process
 * at once: wait for a save in progress (cellSaveData, at most 2 s), flush the
 * logs, _exit(0). exit() would run the C++ static destructors and the Metal
 * and SDL teardown under guest threads that are still running.
 *
 * PS3_EXIT_REQUEST_MS=<ms> (default 0, off): first deliver
 * CELL_SYSUTIL_REQUEST_EXITGAME to the title's sysutil callbacks, as the XMB's
 * "Quit Game" does, keep the RSX running, and give it that long to call
 * sys_process_exit itself before the process is ended anyway. */
#ifndef PS3_CLEAN_EXIT_DEFAULT
#define PS3_CLEAN_EXIT_DEFAULT 1
#endif
#ifndef _WIN32
#include <signal.h>
#include <unistd.h>
#include <time.h>
#include <chrono>
#ifdef __APPLE__
#include <mach/mach.h>
#include <notify.h>
#include <sys/resource.h>
#endif
extern "C" void cellSysutilQueueEvent(int slot, uint32_t status, uint32_t param);
extern "C" int  cellSaveData_busy(void);
static int g_clean_exit = -1;            /* resolved in quit_install() */
static int g_quit_pipe[2] = { -1, -1 };
static volatile int g_quit_started = 0;

static bool clean_exit_on(void)
{
    if (g_clean_exit < 0) {
        const char* e = getenv("PS3_CLEAN_EXIT");
        g_clean_exit = e && *e ? (e[0] != '0') : PS3_CLEAN_EXIT_DEFAULT;
    }
    return g_clean_exit != 0;
}

static void quit_sleep_ms(int ms)
{
    struct timespec ts = { ms / 1000, (long)(ms % 1000) * 1000000L };
    nanosleep(&ts, nullptr);
}

/* Runs once, on the quit thread. Never returns. */
static void quit_now(const char* why)
{
    fprintf(stderr, "[boot] quit (%s)\n", why);
    const char* req = getenv("PS3_EXIT_REQUEST_MS");
    const int req_ms = req ? atoi(req) : 0;
    if (req_ms > 0) {
        /* 0x0101 = CELL_SYSUTIL_REQUEST_EXITGAME; slots the title never
         * registered are skipped by cellSysutilCheckCallback. */
        for (int slot = 0; slot < 4; slot++) cellSysutilQueueEvent(slot, 0x0101, 0);
        fprintf(stderr, "[boot] quit: REQUEST_EXITGAME sent; %d ms for the title to exit\n", req_ms);
        for (int t = 0; t < req_ms; t += 10) quit_sleep_ms(10);
        fprintf(stderr, "[boot] quit: the title did not exit in %d ms\n", req_ms);
    }
    int waited = 0;
    while (cellSaveData_busy() && waited < 2000) { quit_sleep_ms(10); waited += 10; }
    if (waited)
        fprintf(stderr, "[boot] quit: waited %d ms for a save in progress%s\n", waited,
                cellSaveData_busy() ? " (still busy)" : "");
    fflush(stdout);
    fflush(stderr);
    _exit(0);
}

static void* quit_thread(void*)
{
    for (;;) {
        unsigned char c = 0;
        const ssize_t n = read(g_quit_pipe[0], &c, 1);
        if (n == 1) {
            const char* why = c == SIGTERM ? "SIGTERM" : c == SIGINT ? "SIGINT"
                            : c == SIGHUP ? "SIGHUP" : "window closed";
            quit_now(why);
        }
        if (n == 0) return nullptr;
    }
}

static void quit_signal(int sig)
{
    const unsigned char c = (unsigned char)sig;
    const ssize_t r = write(g_quit_pipe[1], &c, 1);   /* async-signal-safe */
    (void)r;
}

/* From the frame clock: the window is gone. */
static void quit_request_window_closed(void)
{
    if (g_quit_started) return;
    g_quit_started = 1;
    const unsigned char c = 0;
    const ssize_t r = write(g_quit_pipe[1], &c, 1);
    (void)r;
}

/* Before anything initialises SDL. */
static void quit_install(void)
{
    if (!clean_exit_on()) return;
    if (pipe(g_quit_pipe) != 0) { g_clean_exit = 0; return; }
    setenv("SDL_NO_SIGNAL_HANDLERS", "1", 0);
    pthread_t th;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    if (pthread_create(&th, &attr, quit_thread, nullptr) != 0) {
        pthread_attr_destroy(&attr);
        g_clean_exit = 0;
        return;
    }
    pthread_attr_destroy(&attr);
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = quit_signal;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = SA_RESTART;
    sigaction(SIGTERM, &sa, nullptr);
    sigaction(SIGINT, &sa, nullptr);
    sigaction(SIGHUP, &sa, nullptr);
}
#else
static bool clean_exit_on(void) { return false; }
static void quit_request_window_closed(void) {}
static void quit_install(void) {}
#endif

static DWORD WINAPI frame_clock(LPVOID)
{
    fprintf(stderr, "[rsx] frame clock thread started\n");
    fflush(stderr);
    int rsx_ok = g_rsx_ready;

    /* PS3_FRAMECLOCK_US=<us>: the sleep between two passes of this loop.
     * The FIFO has no doorbell: a put the guest writes, a flip it asks for,
     * waits here until the next pass, so this is also the latency of every
     * one of those. It was a fixed 4 ms, which left the RSX thread idle up to
     * 4 ms after each flip request. Default 50 (below); 4000 is the old pacing. */
    /* Resistance 2 needed the RSX to react to a put in microseconds: it
     * links a side buffer whose JUMP back sits at put, and reuses that memory
     * for dynamic vertex data right after moving put on. At 1 ms the walker
     * read the vertex data there instead of the JUMP ("FIFO JUMP to unmapped
     * IO", the title's 5 s "GPU sit and spin timeout", corrupt geometry after
     * the resync); at 50 us none in a 440 s run into gameplay. Resistance 3
     * is the same engine three years on: kept until measured otherwise. */
    int clock_us = 50;
    { const char* e = getenv("PS3_FRAMECLOCK_US"); if (e && atoi(e) > 0) clock_us = atoi(e); }
    /* PS3_VBLANK_HZ=<hz> (10..1000): the vblank rate, which also bounds the
     * flip rate. Default one tick per 16 ms (62.5 Hz). */
    ULONGLONG vblank_us = 16000;
    const char* vhz = getenv("PS3_VBLANK_HZ");
    if (vhz || g_res_vblank_hz > 0) {
        const double hz = vhz ? atof(vhz) : g_res_vblank_hz;
        if (hz >= 10 && hz <= 1000) {
            vblank_us = (ULONGLONG)(1e6 / hz + 0.5);
            fprintf(stderr, "[rsx] vblank %.2f Hz (%llu us)\n", hz,
                    (unsigned long long)vblank_us);
        }
    }
    ULONGLONG next_tick = GetTickCount64() * 1000;   /* us */
    ULONGLONG last_pump = 0;
    /* PS3_TELEMETRY=1 (tools/play.sh turns it on): one cheap line a second with
     * the guest frames and the draws in the last frame -- a scene that keeps
     * flipping with almost no draws is a world that stopped rendering -- and,
     * once per stall, where every guest thread is when no frame has come for
     * 3 s, so a freeze in a player's session explains itself in the log. */
    const char* tele_env = getenv("PS3_TELEMETRY");
    const bool telemetry = tele_env && tele_env[0] == '1';
    ULONGLONG tele_time = GetTickCount64(), tele_last_flip_time = tele_time;
    uint32_t tele_flips = cellGcm_flip_request_count();
    bool tele_stalled = false;
    /* Who is limiting the frame, per second: time on this thread in the FIFO
     * drain and in presenting, GPU time of the finished command buffers, CPU
     * of the whole process, footprint, and macOS thermal pressure (0 nominal,
     * 1 moderate, 2 heavy, ...). A drop with drain and gpu both low is the
     * guest (PPU/SPU); therm > 0 at the same moment points at the machine. */
    uint64_t tele_drain_ns = 0, tele_present_ns = 0, tele_gpu_last = 0, tele_cpu_last = 0;
    const auto tele_span = [telemetry](uint64_t& acc, auto&& fn) {
        if (!telemetry) { fn(); return; }
        const auto t0 = std::chrono::steady_clock::now();
        fn();
        acc += (uint64_t)std::chrono::duration_cast<std::chrono::nanoseconds>(
                   std::chrono::steady_clock::now() - t0).count();
    };
    const char* stats_env = getenv("PS3RECOMP_FRAME_STATS");
    const bool frame_stats = stats_env && stats_env[0] == '1';
    ULONGLONG stats_time = GetTickCount64();
    const ULONGLONG stats_start = stats_time;
    uint32_t stats_flips = cellGcm_flip_request_count();

    /* PS3_RSX_AUTORELEASE (default 1; =0 is the old loop): drain an autorelease pool on every pass of this
     * loop. The draw engine runs here, on a plain thread with no pool, and
     * every Metal object it gets autoreleased (a texture descriptor for each
     * target it creates: Resistance 2 recreated ~25 a frame) was kept until exit:
     * +150k MTLTextureDescriptorInternal, +38 MB in 200 s of a paused menu,
     * the ~0.2 MB/s footprint growth of a long session. With the pool, the
     * same paused-menu probe has no such objects left and a flat footprint. */
#ifdef __APPLE__
    const bool rsx_pool = [] { const char* e = getenv("PS3_RSX_AUTORELEASE"); return !(e && e[0] == '0'); }();
#endif
    for (;;) {
#ifdef __APPLE__
        struct PoolScope {
            void* p;
            explicit PoolScope(bool on) : p(on ? objc_autoreleasePoolPush() : nullptr) {}
            ~PoolScope() { if (p) objc_autoreleasePoolPop(p); }
        } pool_scope(rsx_pool);
#endif
#ifdef _WIN32
        Sleep((DWORD)((clock_us + 999) / 1000));
#else
        usleep((useconds_t)clock_us);
#endif
        ULONGLONG now = GetTickCount64();
        const ULONGLONG now_us = now * 1000;
        if (frame_stats && now - stats_time >= 1000) {
            uint32_t flips = cellGcm_flip_request_count();
            fprintf(stderr, "[frame-stats] t=%.2f guest=%.2f flips=%u\n",
                    (now - stats_start) / 1000.0,
                    (flips - stats_flips) * 1000.0 / (now - stats_time), flips);
            stats_time = now; stats_flips = flips;
        }
        if (telemetry && now - tele_time >= 1000) {
            const uint32_t flips = cellGcm_flip_request_count();
            if (flips != tele_flips) {
                if (tele_stalled)
                    fprintf(stderr, "[tele] frames resumed after %.1f s without one\n",
                            (now - tele_last_flip_time) / 1000.0);
                tele_stalled = false;
                tele_last_flip_time = now;
            } else if (!tele_stalled && now - tele_last_flip_time >= 3000) {
                tele_stalled = true;
                fprintf(stderr, "[tele] FREEZE: no guest frame for %.1f s; guest threads:\n",
                        (now - tele_last_flip_time) / 1000.0);
                ppu_report_guest_lrs();
            }
            {
                const ULONGLONG ms = now - tele_time ? now - tele_time : 1;
                const uint64_t gpu = rsx_metal_tele_gpu_ns ? rsx_metal_tele_gpu_ns() : 0;
                uint64_t cpu = 0; uint32_t rss_mb = 0; int therm = -1;
#ifdef __APPLE__
                { struct rusage ru;
                  if (getrusage(RUSAGE_SELF, &ru) == 0)
                      cpu = (uint64_t)(ru.ru_utime.tv_sec + ru.ru_stime.tv_sec) * 1000000000ull +
                            (uint64_t)(ru.ru_utime.tv_usec + ru.ru_stime.tv_usec) * 1000ull; }
                { task_vm_info_data_t vi; mach_msg_type_number_t n = TASK_VM_INFO_COUNT;
                  if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&vi, &n) == KERN_SUCCESS)
                      rss_mb = (uint32_t)(vi.phys_footprint >> 20); }
                { static int tok = -1; uint64_t lvl = 0;
                  if (tok == -1 && notify_register_check("com.apple.system.thermalpressurelevel", &tok) != 0)
                      tok = -2;
                  if (tok >= 0 && notify_get_state(tok, &lvl) == 0) therm = (int)lvl; }
#endif
                const unsigned long long isteps = __atomic_load_n(&g_spu_interp_tele, __ATOMIC_RELAXED);
                const unsigned long long drest = __atomic_load_n(&g_spu_depth_restarts, __ATOMIC_RELAXED);
                static unsigned long long isteps0, drest0;
                fprintf(stderr, "[tele] frames=%u draws=%u drain=%u present=%u gpu=%u (ms/s) cpu=%u%% footprint=%uMB therm=%d"
                                " spuint=%.1fM/s spudepth=%llu\n",
                        flips - tele_flips, rsx_draw_engine_guest_draws(),
                        (unsigned)(tele_drain_ns / 1000000u * 1000u / ms),
                        (unsigned)(tele_present_ns / 1000000u * 1000u / ms),
                        (unsigned)((gpu - tele_gpu_last) / 1000000u * 1000u / ms),
                        (unsigned)((cpu - tele_cpu_last) / 10000000u * 1000u / ms),
                        rss_mb, therm, (isteps - isteps0) / 1e6 * 1000.0 / ms, drest - drest0);
                isteps0 = isteps; drest0 = drest;
                tele_drain_ns = tele_present_ns = 0;
                tele_gpu_last = gpu; tele_cpu_last = cpu;
            }
            tele_time = now; tele_flips = flips;
        }

        int fired = 0;
        while ((long long)(now_us - next_tick) >= 0 && fired < 240) {
            cellGcmTickVBlank();
            cellGcmTickFlip();
            /* Present a pending flip BEFORE draining any further. The flip
             * fires at a get==put frame boundary on the guest thread, so the
             * batch held right now is exactly the completed frame; presenting
             * after the drain races the guest's next-frame writes and shows a
             * mixed one. */
            if (rsx_ok && cellGcm_take_flip_pending())
                tele_span(tele_present_ns, [] { present_guest_frame(); });
            /* Drain the FIFO every tick. This is what writes the RSX sync-fence
             * labels the game's per-frame logic blocks on, so it has to keep
             * advancing at 60 Hz even while present() throttles. */
            if (rsx_ok) tele_span(tele_drain_ns, [] { cellGcm_rsx_process_fifo(); });
            next_tick += vblank_us;      /* ~60 Hz by default */
            fired++;
        }
        if (fired >= 240) next_tick = now_us;   /* fell too far behind -- resync */

        /* Drain at the outer cadence too, not only on the 16 ms tick: titles
         * fence every render pass on a label the drain writes, and one wave of
         * those at 16 ms apiece paces the guest into single-figure frame rates.
         * The real RSX writes them in microseconds. */
        if (rsx_ok) {
            if (cellGcm_take_flip_pending())
                tele_span(tele_present_ns, [] { present_guest_frame(); });
            tele_span(tele_drain_ns, [] { cellGcm_rsx_process_fifo(); });

            /* Window events at most every 4 ms, as before PS3_FRAMECLOCK_US:
             * a windowed pump is a dispatch_sync to the main thread, and this
             * loop now runs every 1 ms. */
            const int pump_due = now - last_pump >= 4 || now < last_pump;
            if (pump_due && !win_gone) {
                last_pump = now;
                if (rsx_backend_pump() != 0) {
                    /* Window closed. With PS3_CLEAN_EXIT the process ends
                     * (quit_now); until then the FIFO keeps draining, so a
                     * title asked to exit (PS3_EXIT_REQUEST_MS) is not left
                     * spinning on its RSX fence. Presents into a closed
                     * window are skipped by the backend. */
                    if (clean_exit_on()) {
                        win_gone = true;
                        quit_request_window_closed();
                    } else {
                        rsx_ok = 0;
                        continue;
                    }
                }
            }
            /* Present a flip the drain just reached, now: the drain stops at
             * the flip, so the batch is exactly the finished frame. Consuming
             * the pending flag here matters -- this used to present on the
             * flip count changing and leave the flag set, so the check above
             * re-showed the same frame on the next pass with no draws: every
             * frame was presented twice. Before the first flip present at the
             * pump's cadence, so the window is not blank during boot. */
            if (cellGcm_take_flip_pending())
                present_guest_frame();
            else if (pump_due && !win_gone && cellGcm_flip_request_count() == 0)
                rsx_backend_present();
        }
    }
    return 0;
}

/* ---------------------------------------------------------------------------
 * VFS root
 * -----------------------------------------------------------------------*/
/* Derive the directory holding PS3_GAME from the EBOOT path
 * <root>/PS3_GAME/USRDIR/EBOOT.elf -> <root>. $PS3_VFS_ROOT overrides. */
static char s_vfs_root[1024];

static void derive_vfs_root(const char* eboot)
{
    const char* env = getenv("PS3_VFS_ROOT");
    if (env && *env) { ppu_vfs_root = env; return; }

    strncpy(s_vfs_root, eboot, sizeof s_vfs_root - 1);
    for (char* p = s_vfs_root; *p; p++) if (*p == '\\') *p = '/';
    /* strip EBOOT.elf, USRDIR and PS3_GAME */
    for (int i = 0; i < 3; i++) { char* s = strrchr(s_vfs_root, '/'); if (s) *s = 0; }
    if (!s_vfs_root[0]) strcpy(s_vfs_root, ".");
    ppu_vfs_root = s_vfs_root;
}

/* ---------------------------------------------------------------------------
 * Guest VM
 * -----------------------------------------------------------------------*/
#ifdef _WIN32
/* Demand-paging for the flat VM: reserve the whole 4 GB guest space, which
 * costs no commit, and commit each 64 KB page on first access. Every 32-bit
 * guest offset is then valid, so a garbage guest pointer reads zero instead of
 * killing the process. Faults outside the arena fall through untouched. */
static LONG WINAPI vm_commit_veh(EXCEPTION_POINTERS* ep)
{
    if (ep->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) {
        ULONG_PTR fault = ep->ExceptionRecord->ExceptionInformation[1];
        uintptr_t base  = (uintptr_t)vm_base;
        if (vm_base && fault >= base && fault < base + VM_SIZE) {
            void* page = (void*)(fault & ~(uintptr_t)0xFFFF);
            if (VirtualAlloc(page, 0x10000, MEM_COMMIT, PAGE_READWRITE))
                return EXCEPTION_CONTINUE_EXECUTION;
        }
    }
    return EXCEPTION_CONTINUE_SEARCH;
}
#endif

static bool alloc_guest_vm(void)
{
#ifdef _WIN32
    AddVectoredExceptionHandler(1, vm_commit_veh);
    vm_base = (uint8_t*)VirtualAlloc(NULL, VM_SIZE, MEM_RESERVE, PAGE_READWRITE);
    ppu_vm_size = 0;              /* the whole space is backed; no OOB guard needed */
#else
    /* No vectored exception handlers off Windows, so the arena is mapped up
     * front and lazily backed by the OS: only pages the title touches cost
     * anything. It spans the whole 32-bit space plus the guard, as on Windows:
     * Resistance's game.self starts a raw SPU after the intro movie, and the
     * raw SPU windows (local store and problem-state registers, spu_raw.c)
     * live at 0xE0000000+. An arena that stopped there turned every MFC proxy
     * DMA register store into an "OOB access" and the level never loaded.
     * Resistance 2 starts raw SPUs too (igInitRawSpu: Bink and two level
     * programs).
     *
     * mmap, not calloc: vm_commit() hands vm_base + addr to mprotect, which
     * takes page-aligned addresses only. glibc serves an allocation this big
     * from its own mmap chunk and returns a pointer 16 bytes past the page
     * start, so every commit failed with EINVAL and sys_memory_allocate
     * answered ENOMEM to every call. mmap's base is page-aligned and zeroed. */
    void* p = mmap(NULL, VM_SIZE, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    vm_base = (p == MAP_FAILED) ? nullptr : (uint8_t*)p;
    ppu_vm_size = 0;              /* the whole space is backed; no OOB guard needed */
#endif
    return vm_base != nullptr;
}

/* ---------------------------------------------------------------------------
 * Main
 * -----------------------------------------------------------------------*/
static void harness_guest_caller(uint32_t opd, uint64_t a0, uint64_t a1,
                                 uint64_t a2, uint64_t a3, uint64_t a4,
                                 uint64_t a5, uint64_t a6, uint64_t a7)
{
    ppu_guest_call(opd, a0, a1, a2, a3, a4, a5, a6, a7);
}

int main(int argc, char** argv)
{
    if (argc < 2) {
        printf("usage: %s <PPU ELF>\n", argv[0]);
        return 2;
    }

#ifdef _WIN32
#pragma comment(lib, "winmm.lib")
    /* 1 ms timer resolution. The default granularity is about 15.6 ms, which
     * inflates every shorter wait the title makes and throttles the whole
     * thing. POSIX timers are already fine-grained. */
    timeBeginPeriod(1);
    setvbuf(stdout, NULL, _IONBF, 0);   /* unbuffered: do not lose prints on a kill */
#endif

    printf("=== ps3recomp game runner ===\n");

    /* The defaults below were what Resistance 2 needed (the same Insomniac
     * engine); each can be turned off from the environment for an A/B.
     *
     * The toolkit's SPURS kernel-style workload selection is opt-in there;
     * Resistance 1 and 2 need it. With the old round-robin selection every
     * workload but wid 0 yielded at its first poll, and the gameplay jobs
     * (igGeomCullClip, SpuBucketerDrawSort) timed out. SPURS_RPCS3_SCHED=0
     * in the environment still turns it off. */
    {
        const char* s = getenv("SPURS_RPCS3_SCHED");
#ifdef _WIN32
        if (!s) _putenv_s("SPURS_RPCS3_SCHED", "1");
        else if (strcmp(s, "0") == 0) _putenv_s("SPURS_RPCS3_SCHED", "");
#else
        if (!s) setenv("SPURS_RPCS3_SCHED", "1", 1);
        else if (strcmp(s, "0") == 0) unsetenv("SPURS_RPCS3_SCHED");
#endif
    }
    /* Resistance 3's "ig" SPURS instance runs its igPm policy module on all
     * five of its SPUs at once: the game writes each SPU's number to its SNR1
     * and igPm serves the job queue of that number (queue 2 the per-frame
     * igBucketer job, queues 3 and 4 the Bink movie jobs). The workload is
     * added with max contention 1 and ready count 5, and the toolkit's
     * kernel honours the 1, so SPURS_WIDEN=0 runs wid 0 on every SPU of its
     * instance (the other instance's wid 0 has one SPU, so it is unchanged).
     * SPU_CH_BLOCK=1: an empty SNR1 read blocks until the game writes it, as
     * on the console; without it the read returned a stale 0 and every lane
     * served queue 0, and an idle igPm spun on its lock-line wait at 100% of
     * a core instead of sleeping. Each is turned off with =off. */
    {
        const char* w = getenv("SPURS_WIDEN");
        const char* b = getenv("SPU_CH_BLOCK");
#ifdef _WIN32
        if (!w) _putenv_s("SPURS_WIDEN", "0");
        else if (strcmp(w, "off") == 0) _putenv_s("SPURS_WIDEN", "");
        if (!b) _putenv_s("SPU_CH_BLOCK", "1");
        else if (strcmp(b, "off") == 0 || strcmp(b, "0") == 0) _putenv_s("SPU_CH_BLOCK", "");
#else
        if (!w) setenv("SPURS_WIDEN", "0", 1);
        else if (strcmp(w, "off") == 0) unsetenv("SPURS_WIDEN");
        if (!b) setenv("SPU_CH_BLOCK", "1", 1);
        else if (strcmp(b, "off") == 0 || strcmp(b, "0") == 0) unsetenv("SPU_CH_BLOCK");
#endif
    }
    /* No PlayStation Eye: the toolkit's virtual EyeToy is reported attached
     * by default, and after the loading movie Resistance 3 opened "PlayStation
     * Eye is not correctly connected." and waited on it (it polls
     * cellCameraGetBufferInfoEx, which the toolkit lacks). PS3_CAMERA=1 puts
     * the virtual camera back. */
#ifdef _WIN32
    if (!getenv("PS3_CAMERA")) _putenv_s("PS3_CAMERA", "0");
#else
    setenv("PS3_CAMERA", "0", 0);
#endif
    /* The RSX engine's texture cache: Haven's streets use more than the
     * toolkit's default 1024 textures at once, so it evicted and re-uploaded
     * ~9,500 of them every 120 frames (~500 MB, 100-240 ms of uploads in a
     * frame, the game dropping to 6 fps outdoors). 4096 of the 8192 the
     * engine allows; PS3RECOMP_ENG_TEXCACHE_SLOTS still wins. */
#ifdef _WIN32
    if (!getenv("PS3RECOMP_ENG_TEXCACHE_SLOTS")) _putenv_s("PS3RECOMP_ENG_TEXCACHE_SLOTS", "4096");
#else
    setenv("PS3RECOMP_ENG_TEXCACHE_SLOTS", "4096", 0);
#endif
    /* The render-target table: 128 slots filled in Haven and evicted thousands
     * of targets a session (6,528 in one), each losing its GPU-only content;
     * a later sample of one (the pause menu's copy of the scene) read
     * garbage. 512 of the 1024 the engine allows; PS3RECOMP_ENG_SURFACE_SLOTS
     * still wins. */
#ifdef _WIN32
    if (!getenv("PS3RECOMP_ENG_SURFACE_SLOTS")) _putenv_s("PS3RECOMP_ENG_SURFACE_SLOTS", "512");
#else
    setenv("PS3RECOMP_ENG_SURFACE_SLOTS", "512", 0);
#endif
    /* The first boot's HDD install is done when the first and the last file
     * Resistance 3's installer writes are there (the toolkit's default pair
     * is Resistance 2's, which R3 never writes, so every boot asked "The game
     * will need to install data on your hard disk drive." and copied the
     * 1.5 GB again). Order seen in an install log: global_cached.psarc
     * first, the sound banks in name order last. */
#ifdef _WIN32
    if (!getenv("PS3_GAMEDATA_MARKERS"))
        _putenv_s("PS3_GAMEDATA_MARKERS", "USRDIR/packed/game/global_cached.psarc:"
                  "USRDIR/built/sound/bank/ffe79163/resident_sound.dat");
#else
    setenv("PS3_GAMEDATA_MARKERS", "USRDIR/packed/game/global_cached.psarc:"
           "USRDIR/built/sound/bank/ffe79163/resident_sound.dat", 0);
#endif
    /* Real sys_lwcond notifications instead of the 1 ms sleep-and-retry
     * fallback. Resistance 2's job/loader worker pools (func_00B11A80 x14,
     * func_007D9EB8 x8) hand work over through lwconds; at ~1.2 ms per
     * handoff the front-end load after the Insomniac movie froze the guest
     * for 5-6 s, with events ~1 s (A/B on one binary). PS3_LWCOND_EVENTS=0
     * restores the fallback. ppu_lwcond_events.h reads it once, lazily. */
    {
        /* The host mix is stereo, so offer stereo: Resistance 2 configured
         * the highest channel count it was offered and mixed for it, and a
         * 5.1 mix folded to stereo clipped (3568 clipped samples in a 365 s
         * probe, 1014 with stereo, 0 with the limiter too; highest peak 1.36).
         * PS3_AUDIO_OUT_STEREO=0 / PS3_AUDIO_LIMITER=0 turn them off. */
#ifdef _WIN32
        if (!getenv("PS3_AUDIO_OUT_STEREO")) _putenv_s("PS3_AUDIO_OUT_STEREO", "1");
        if (!getenv("PS3_AUDIO_LIMITER")) _putenv_s("PS3_AUDIO_LIMITER", "1");
#else
        setenv("PS3_AUDIO_OUT_STEREO", "1", 0);
        setenv("PS3_AUDIO_LIMITER", "1", 0);
#endif
        const char* s = getenv("PS3_LWCOND_EVENTS");
#ifdef _WIN32
        if (!s) _putenv_s("PS3_LWCOND_EVENTS", "1");
#else
        if (!s) setenv("PS3_LWCOND_EVENTS", "1", 1);
#endif
    }

    /* SIGTERM/SIGINT/SIGHUP and the window closing end the process
     * (PS3_CLEAN_EXIT). First, before the backend or anything else can
     * initialise SDL and take the signals over. */
    quit_install();

    const char* title = getenv("PS3_TITLE");
    if (!title || !*title) title = "Resistance 3";
    g_rsx_ready = (rsx_backend_init(WINDOW_WIDTH, WINDOW_HEIGHT, title) == 0);
    fprintf(stderr, "[rsx] %s backend init %s\n", RSX_BACKEND_NAME,
            g_rsx_ready ? "OK -- window open" : "FAILED");

    if (!alloc_guest_vm()) {
        fprintf(stderr, "ERROR: could not allocate the guest address space\n");
        return 1;
    }

    uint32_t entry = ppu_load_elf(argv[1]);
    if (!entry) {
        fprintf(stderr, "ERROR: could not load %s\n", argv[1]);
        return 1;
    }

    res_apply_patches();

    derive_vfs_root(argv[1]);
    printf("[boot] VFS root: %s\n", ppu_vfs_root);
    char sfo_path[1024];
    snprintf(sfo_path, sizeof(sfo_path), "%s/PS3_GAME/PARAM.SFO", ppu_vfs_root);
    cellGame_init_from_paramsfo(sfo_path);

    ppu_recomp_register();   /* lifted function table -> address map */
    ps3_load_prx_modules();  /* this game's lifted system PRX, if it has any */
    ppu_hle_init();          /* firmware import NID -> HLE handlers */
    ppu_sysprx_register();   /* boot-critical CRT */
    ppu_fs_register();       /* cellFs over the game directory */
    lv2_init_syscalls();     /* the lv2 syscall table */

    /* Install the guest-callback hook, then start the frame clock. It no-ops
     * until the title registers its vblank and flip handlers during init. */
    g_ps3_guest_caller = harness_guest_caller;
    CreateThread(NULL, 4u * 1024 * 1024, frame_clock, NULL, 0, NULL);

    printf("\n[boot] dispatching entry OPD 0x%08X (stack top 0x%08X)\n\n",
           entry, STACK_TOP);

    /* The main thread's stack, as sys_ppu_thread_get_stack_information reports
     * it: the 1 MB below STACK_TOP the guest really runs on. */
    g_ppu_main_stack_addr = STACK_TOP - MAIN_STACK_SIZE;
    g_ppu_main_stack_size = MAIN_STACK_SIZE;

    /* A process started by sys_game_process_exitspawn gets the parent's data
     * block where lv2 leaves it, just below the top of its stack (the
     * Resistance: Fall of Man port needs this for game.self). Resistance 3's
     * survey (tools/r3_survey.py) says whether it spawns a second ELF; until
     * then the block is honoured when RES_SPAWN_DATA names one. */
    uint32_t run_stack_top = STACK_TOP;
    if (const char* df = getenv("RES_SPAWN_DATA")) {
        if (FILE* f = fopen(df, "rb")) {
            uint8_t buf[0x1000];
            size_t n = fread(buf, 1, sizeof buf, f);
            fclose(f);
            memcpy(vm_base + STACK_TOP - 0x1000, buf, n);
            run_stack_top = STACK_TOP - 0x1000;
            printf("[boot] exitspawn data: %zu bytes at 0x%08X\n", n, STACK_TOP - 0x1000);
        }
        /* RES_SPAWN_KEEP=1 leaves the file for a rerun of the child alone. */
        if (!getenv("RES_SPAWN_KEEP")) remove(df);
        unsetenv("RES_SPAWN_DATA");
    }

#if defined(__APPLE__)
    /* AppKit only runs on the process's main thread: the Metal backend pumps
     * the window's events with dispatch_sync onto the main queue. With the
     * guest on the main thread nothing ever serviced that queue, so the frame
     * clock blocked in its first event pump, the FIFO never drained and the
     * title spun for ever in its "get == put" wait (func_000A00DC). The guest
     * runs on its own thread instead (the 256 MB host stack every guest thread
     * gets) and the main thread turns the run loop. Same fix as the inFAMOUS 2
     * and Resistance 1/2 ports. */
    int rc;
    {
        struct boot_args { uint32_t entry; uint32_t stack_top; int rc; volatile int done; };
        static boot_args ba;
        ba.entry = entry; ba.stack_top = run_stack_top; ba.rc = 0; ba.done = 0;
        pthread_attr_t attr;
        pthread_attr_init(&attr);
        pthread_attr_setstacksize(&attr, 256u * 1024u * 1024u);
        pthread_t th;
        auto body = [](void* a) -> void* {
            boot_args* b = (boot_args*)a;
            b->rc = ppu_run(b->entry, b->stack_top);
            __atomic_store_n(&b->done, 1, __ATOMIC_RELEASE);
            CFRunLoopStop(CFRunLoopGetMain());
            return nullptr;
        };
        if (pthread_create(&th, &attr, body, &ba) != 0) {
            fprintf(stderr, "[boot] could not start the guest thread\n");
            return 1;
        }
        pthread_attr_destroy(&attr);
        while (!__atomic_load_n(&ba.done, __ATOMIC_ACQUIRE))
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.05, false);
        pthread_join(th, nullptr);
        rc = ba.rc;
    }
#else
    int rc = ppu_run(entry, run_stack_top);
#endif
    printf("\n[boot] ppu_run returned %d (entry function unwound)\n", rc);

    /* A title that called sys_process_exit never reaches this line: that path
     * ends in the host exit(). Getting here means the entry function returned
     * instead, so hand back the status the guest published if it published
     * one. Returning a hardcoded 0 would report success for a run that never
     * got anywhere. */
    return g_sys_process_exit_called ? (int)g_sys_process_exit_code : 0;
}
