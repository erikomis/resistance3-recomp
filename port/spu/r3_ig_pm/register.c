/* Resistance 3 (BCUS98176 01.00) "igPm" SPURS policy module, embedded as raw
 * data in EBOOT.elf: EBOOT VA 0x00E28F80, 560 bytes, loaded into SPU LS at 0xA00.
 * The FNV-1a matches spu_workload_fingerprint over those exact bytes
 * (tools/prepare_r3_ig_pm.py lifts them and checks it). */
#include "spu_workload.h"

extern void spu_begin_image(int image_id);
extern void r3_ig_pm_spu_recomp_register(void);
extern void r3_ig_pm_spu_func_00000A00(spu_context*);

enum { R3_IG_PM_IMAGE_ID = 930002 };

__attribute__((constructor)) static void r3_ig_pm_register(void)
{
    spu_begin_image(R3_IG_PM_IMAGE_ID);
    r3_ig_pm_spu_recomp_register();
    spu_workload_register_img(0xCA191E29E59B1967ULL,
                              r3_ig_pm_spu_func_00000A00,
                              R3_IG_PM_IMAGE_ID, "r3_ig_pm_E28F80");
    spu_begin_image(0);
}
