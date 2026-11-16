# ps3recomp v0.19 backports

The port stays on v0.17.0 (`a6d76c8`) plus its toolkit patch. These changes
were taken from the v0.19 history, in increasing adaptation difficulty:

| Change | Upstream commit | Integration |
|---|---|---|
| VMX scaled integer/float conversions without `ldexpf` per lane | `9632fcca1629a388409d225cbbd69330955d7744` | Applied |
| MFC parameter writes latch directly in the SPU context | `d12c076fce71902c46b63b5a12f17e5e4288f175` | Applied |
| Per-thread PPU indirect-target and profiler caches | `86353eb33ae3b79eb10b1ee41509c252b9be481e` | Applied |
| Per-thread HLE NID cache and idle GCM pump fast path | `cd926aa1e20de9db3b2cf4c99ba3bc9bdfcf5068` | HLE applied; pump adapted around R3's existing serialization guard |
| Published guest GCM offset tables follow map/unmap | `30d88c35b3190309fa11c9080a97d8fd58208a95` | Applied with upstream regression |
| Exact NEON `fi` interpolation on ARM64 | `0b874166c7bb5caa389d351863a417367ffb4362` | Adapted; retained this port's existing `cflts`/`cfltu` fast paths |

The scalar `spu_fi_exact` remains available as the reference and the fallback
with `SPU_SCALAR_HELPERS`. The cache of indirect-call targets invalidates on
every registration, including replacement without an increased function
count. The HLE cache tracks both registration-table sizes, so late handlers
and context-handler priority remain visible.

## Validation

Run from the repository root:

```sh
.venv/bin/python tools/test_toolkit_v019.py
.venv/bin/python ps3recomp/tools/test_ppu_dispatch_depth.py
.venv/bin/python ps3recomp/tools/test_ppu_sjlj.py
cmake --build build/BCUS98176 --parallel 2
```

The targeted suite covers 1,280,000 VMX conversion vectors (all 32 scales,
saturation, special values and destination/source aliases), HLE and PPU
cache collisions and late registrations, another calling thread, real DMA
GET/PUT and stalled-list ownership (564 checks), and guest offset-table
updates. The imported NEON fixture compares 5,600,000 vectors with scalar
references in normal FPCR and round-toward-zero/flush-to-zero modes; it is
also run with the scalar fallback selected.

Validation completed on macOS/arm64: the targeted suite, coroutine dispatch
depth and guest setjmp/longjmp regressions passed, and the full
`build/BCUS98176/ResistanceRecomp` executable rebuilt successfully.

These checks establish correctness of the exercised paths. They do not
measure FPS or validate a complete campaign session. The new-style FIFO
JUMP change (#675), already reverted after an R3 hang, is not part of this
batch. Depth-bounds emulation, SPURS2 and a full toolkit upgrade are also
outside this batch.

Two older standalone runners were also tried: `test_spu_dma_repeat.py` and
`test_gcm_flip_stream.py`. Their fixtures lack R3's SPURS lane-bridge and
draw-engine timing symbols, respectively, and do not link in this tree.
The targeted suite instead links a dedicated DMA fixture with the existing
ownership/stalled-list tests, and checks the callback pump independently of
the FIFO walker. It does not claim those older standalone suites passed.

Toolkit sources and fixtures are shipped through
`patches/ps3recomp-a6d76c8-resistance3.patch`, regenerated with
`tools/export_toolkit_patch.sh` and checked against a pristine v0.17.0 tree.
