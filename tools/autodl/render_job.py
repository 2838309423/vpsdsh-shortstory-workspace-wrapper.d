"""render_job.py -- headless Cycles job renderer for the AutoDL image (CUDA / OPTIX / CPU).

Invoked by run-job.sh as:
  blender --factory-startup -b <scene.blend> --python-exit-code 1 --python render_job.py -- \
      --out <dir-or-file> --device CUDA --res 1080x1920 --samples 24 \
      [--scene SceneA] [--start 1] [--end 408] [--denoise on|off] [--report report.json]

Hard rules encoded here (learned the hard way):
  * device is explicit -- request CUDA/OPTIX and NOTHING is found -> exit 4 (never silently bill a GPU for a CPU render)
  * `use_file_extension` handling so PNG frame numbers land where the caller expects
  * one machine-readable line at the end: __RENDER__ ok=<0|1> ...  (parsed by run-job.sh)
"""
import argparse
import json
import os
import sys
import time

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="output dir (animation) or .png path (still)")
    ap.add_argument("--device", default="CUDA", choices=["CUDA", "OPTIX", "CPU"])
    ap.add_argument("--res", default=None, help="WxH")
    ap.add_argument("--samples", type=int, default=None)
    ap.add_argument("--scene", default=None, help="scene name; default = active scene")
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--denoise", default="on", choices=["on", "off"])
    ap.add_argument("--report", default=None)
    ap.add_argument("--threads", type=int, default=0)
    return ap.parse_args(argv)


def configure_device(sc, dev):
    """Returns (ok, detail). Mirrors the Blender 4.x Cycles GPU setup."""
    prefs_addon = bpy.context.preferences.addons.get("cycles")
    if prefs_addon is None:
        return (dev == "CPU"), "cycles addon missing"
    cp = prefs_addon.preferences
    if dev != "CPU":
        cp.compute_device_type = dev
    cp.get_devices()
    seen = []
    for d in cp.devices:
        d.use = (d.type != "CPU") if dev != "CPU" else (d.type == "CPU")
        if d.use:
            seen.append("%s:%s" % (d.type, d.name))
    if dev == "CPU":
        sc.cycles.device = "CPU"
        return True, "CPU"
    gpu_devs = [d for d in cp.devices if d.use and d.type != "CPU"]
    if not gpu_devs:
        return False, "no %s device visible (devices: %s)" % (dev, [d.type for d in cp.devices])
    sc.cycles.device = "GPU"
    return True, ",".join(seen)


def main():
    a = parse_args()
    sc = bpy.data.scenes.get(a.scene) if a.scene else bpy.context.scene
    if sc is None:
        print("__RENDER__ ok=0 error=scene_not_found name=%s" % a.scene)
        sys.exit(3)
    bpy.context.window.scene = sc if getattr(bpy.context, "window", None) else None

    sc.render.engine = "CYCLES"
    ok, detail = configure_device(sc, a.device)
    print("[render_job] device=%s detail=%s" % (a.device, detail))
    if not ok:
        print("__RENDER__ ok=0 error=gpu_not_available device=%s detail=%s" % (a.device, detail))
        sys.exit(4)

    if a.res:
        w, h = (int(x) for x in a.res.lower().split("x"))
        sc.render.resolution_x, sc.render.resolution_y = w, h
        sc.render.resolution_percentage = 100
    if a.samples:
        sc.cycles.samples = a.samples
    sc.cycles.use_denoising = (a.denoise == "on")
    if a.threads:
        sc.render.threads_mode = "FIXED"
        sc.render.threads = a.threads

    animation = a.start is not None and a.end is not None
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    if animation:
        sc.frame_start, sc.frame_end = a.start, a.end
        os.makedirs(a.out, exist_ok=True)
        sc.render.filepath = os.path.join(a.out, "frame_")
        sc.render.use_file_extension = True
    else:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        sc.render.filepath = a.out
        sc.render.use_file_extension = False

    n = (a.end - a.start + 1) if animation else 1
    print("[render_job] engine=CYCLES res=%dx%d samples=%d denoise=%s frames=%d out=%s"
          % (sc.render.resolution_x, sc.render.resolution_y, sc.cycles.samples,
             a.denoise, n, sc.render.filepath))

    t0 = time.time()
    bpy.ops.render.render(animation=animation)
    dt = time.time() - t0

    if animation:
        files = [f for f in sorted(os.listdir(a.out)) if f.endswith(".png")]
    else:
        cand = [a.out, a.out + ".png"]
        hit = next((p for p in cand if os.path.exists(p)), None)
        files = [hit] if hit else []
    ok = len(files) >= n
    spf = dt / max(n, 1)
    rep = {
        "ok": ok, "device": a.device, "device_detail": detail, "engine": "CYCLES",
        "res": "%dx%d" % (sc.render.resolution_x, sc.render.resolution_y),
        "samples": sc.cycles.samples, "denoise": a.denoise,
        "frames": n, "png_found": len(files),
        "seconds": round(dt, 2), "seconds_per_frame": round(spf, 2),
        "out": a.out, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if a.report:
        with open(a.report, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=2)
    print(json.dumps(rep, ensure_ascii=False))
    print("__RENDER__ ok=%d frames=%d png=%d seconds=%.2f spf=%.2f device=%s"
          % (1 if ok else 0, n, len(files), dt, spf, a.device))
    sys.exit(0 if ok else 5)


main()
