"""Cycles CPU smoke test -- used by selftest.sh. Needs NO GPU.

Run:  blender --factory-startup -b --python-exit-code 1 --python smoke_cpu.py -- \
        --out /tmp/smoke.png --res 320x180 --samples 8

Prints one machine-readable line:  __SMOKE__ ok=<0|1> bytes=<n> seconds=<f>
"""
import argparse
import json
import os
import sys
import time

import bpy


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--res", default="320x180")
    ap.add_argument("--samples", type=int, default=8)
    a = ap.parse_args(argv)

    w, h = (int(x) for x in a.res.lower().split("x"))
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = a.samples
    sc.cycles.use_denoising = False
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = a.out
    sc.render.use_file_extension = False

    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    dt = time.time() - t0

    cand = [a.out, a.out + ".png"]
    path = next((p for p in cand if os.path.exists(p)), a.out)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    ok = size > 1024
    print(json.dumps({"out": path, "bytes": size, "seconds": round(dt, 2), "ok": ok}))
    print("__SMOKE__ ok=%d bytes=%d seconds=%.2f" % (1 if ok else 0, size, dt))
    if not ok:
        sys.exit(3)


main()
