/* Resistance 3 (BCUS98176 01.00) "Wws_Job" SPURS policy module, embedded as raw
 * data in EBOOT.elf: EBOOT VA 0x00EB9E00, 12,544 bytes, loaded into SPU LS at 0xA00.
 * The FNV-1a matches spu_workload_fingerprint over those exact bytes
 * (tools/prepare_r3_job_pm.py lifts them and checks it). */
#include "spu_workload.h"

extern void spu_begin_image(int image_id);
extern void r3_job_pm_spu_recomp_register(void);
extern void r3_job_pm_spu_func_00000A00(spu_context*);

enum { R3_JOB_PM_IMAGE_ID = 930001 };

__attribute__((constructor)) static void r3_job_pm_register(void)
{
    spu_begin_image(R3_JOB_PM_IMAGE_ID);
    r3_job_pm_spu_recomp_register();
    spu_workload_register_img(0xEA3A104FE30430AAULL,
                              r3_job_pm_spu_func_00000A00,
                              R3_JOB_PM_IMAGE_ID, "r3_job_pm_EB9E00");
    spu_begin_image(0);
}
