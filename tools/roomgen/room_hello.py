# -*- coding: utf-8 -*-
"""room_hello.py —— 最小「3D 小房间短剧场所」生成器（Blender bpy，无头可跑）

跑法（宿主侧）：
    bin/win10-blender.sh tools/roomgen/room_hello.py --job hello1 -- --samples 32

它做的事：清空场景 → 按尺寸搭一间房（地/顶/四面墙，门洞 + 窗洞）→ 摆一套家具道具
→ 布光（窗外夜景 + 吸顶灯 + 台灯 + 太阳光）→ 3 个机位各渲一张 PNG → 存 .blend →
自检（文件在不在、图黑不黑、机位够不够）并打印末行 `__SELFTEST__ <断言数> <失败数>`。

口径：
  * 只用 Cycles CPU —— 客机是无 GPU 直通的 KVM，EEVEE 在无头下要 GL 上下文，靠不住。
  * 一切尺寸单位是米，房间内壁：x∈[-w/2,w/2], y∈[-d/2,d/2], z∈[0,h]。
  * 输出目录由父进程（bin/win10-blender.sh）用 `-- --outdir ...` 指定，默认脚本同级 out/。
"""
import argparse
import json
import math
import os
import sys

import bpy
from mathutils import Vector

T = 0.12          # 墙厚
FPS = 25


# ---------------------------------------------------------------- 基础设施
def log(msg):
    print("[room] " + msg, flush=True)


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser()
    p.add_argument("--outdir", default=os.path.join(here, "..", "out"))
    p.add_argument("--blend", default=None)
    p.add_argument("--name", default="room-hello")
    p.add_argument("--w", type=float, default=4.2)      # 房间开间（X）
    p.add_argument("--d", type=float, default=3.6)      # 进深（Y）
    p.add_argument("--h", type=float, default=2.70)     # 层高（Z）
    p.add_argument("--samples", type=int, default=48)
    p.add_argument("--res", default="960x540")
    p.add_argument("--shots", default="all")
    a = p.parse_args(argv)
    a.outdir = os.path.abspath(a.outdir).replace("\\", "/")
    a.blend = os.path.abspath(a.blend).replace("\\", "/") if a.blend else os.path.join(a.outdir, a.name + ".blend")
    return a


ARGS = parse_args()
W, D, H = ARGS.w, ARGS.d, ARGS.h


def mat(name, color, rough=0.7, metal=0.0, emit=None, emit_strength=0.0, transmission=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if transmission and "Transmission Weight" in b.inputs:
        b.inputs["Transmission Weight"].default_value = transmission
    if emit is not None:
        key = "Emission Color" if "Emission Color" in b.inputs else "Emission"
        b.inputs[key].default_value = (emit[0], emit[1], emit[2], 1.0)
        b.inputs["Emission Strength"].default_value = emit_strength
    return m


def _finish(o, name, m):
    o.name = name
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if m:
        o.data.materials.append(m)
    return o


def box(name, size, loc, m=None, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale = size
    return _finish(o, name, m)


def cyl(name, r, h, loc, m=None, rot=(0, 0, 0), verts=32):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=loc, rotation=rot)
    return _finish(bpy.context.active_object, name, m)


def sphere(name, r, loc, m=None, seg=24):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=seg, ring_count=seg // 2, location=loc)
    o = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    return _finish(o, name, m)


def blob(name, size, loc, m=None, rot=(0, 0, 0)):
    """压扁的球：枕头/靠垫这类软东西比方块像样得多"""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, segments=28, ring_count=14, location=loc, rotation=rot)
    o = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    o.scale = size
    return _finish(o, name, m)


def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def new_light(name, kind, loc, energy, color=(1, 1, 1), size=None, aim=None):
    li = bpy.data.lights.new(name, type=kind)
    li.energy = energy
    li.color = color
    if kind == 'AREA' and size:
        li.size = size
    if kind == 'SUN':
        li.angle = math.radians(2.0)
    o = bpy.data.objects.new(name, li)
    o.location = loc
    bpy.context.collection.objects.link(o)
    if aim:
        look_at(o, aim)
    return o


def new_camera(name, loc, aim, lens):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.sensor_fit = 'HORIZONTAL'
    o = bpy.data.objects.new(name, cam)
    o.location = loc
    bpy.context.collection.objects.link(o)
    look_at(o, aim)
    return o


# ---------------------------------------------------------------- 材质表
M = {}


def make_materials():
    M["wall"] = mat("M_wall", (0.76, 0.73, 0.68), rough=0.92)
    M["floor"] = mat("M_floor", (0.36, 0.24, 0.15), rough=0.55)
    M["ceil"] = mat("M_ceiling", (0.90, 0.90, 0.88), rough=0.95)
    M["wood"] = mat("M_wood", (0.28, 0.18, 0.11), rough=0.45)
    M["wood2"] = mat("M_wood_light", (0.55, 0.40, 0.26), rough=0.5)
    M["cloth"] = mat("M_cloth", (0.35, 0.42, 0.55), rough=0.95)
    M["sheet"] = mat("M_sheet", (0.86, 0.85, 0.82), rough=0.9)
    M["pillow"] = mat("M_pillow", (0.92, 0.90, 0.86), rough=0.95)
    M["rug"] = mat("M_rug", (0.55, 0.30, 0.28), rough=0.98)
    M["metal"] = mat("M_metal", (0.62, 0.63, 0.66), rough=0.35, metal=0.9)
    M["dark"] = mat("M_dark", (0.08, 0.08, 0.09), rough=0.5)
    M["screen"] = mat("M_screen", (0.05, 0.06, 0.08), rough=0.2, emit=(0.35, 0.55, 0.85), emit_strength=1.6)
    M["lamp"] = mat("M_lamp_bulb", (1.0, 0.95, 0.85), rough=0.3, emit=(1.0, 0.88, 0.68), emit_strength=12.0)
    M["plant"] = mat("M_plant", (0.13, 0.32, 0.14), rough=0.85)
    M["pot"] = mat("M_pot", (0.45, 0.22, 0.16), rough=0.8)
    M["frame"] = mat("M_frame", (0.15, 0.14, 0.13), rough=0.6)
    M["art"] = mat("M_art", (0.85, 0.68, 0.35), rough=0.9)
    M["night"] = mat("M_night", (0.02, 0.03, 0.07), rough=1.0, emit=(0.10, 0.16, 0.35), emit_strength=1.2)


# ---------------------------------------------------------------- 房间壳体
def wall_x(name, y, x0, x1, m, hole=None):
    """沿 X 方向展开的墙（法线朝 Y）。hole=(x0,x1,z0,z1) 时在墙上留洞。"""
    if hole is None:
        box(name, (x1 - x0, T, H), ((x0 + x1) / 2, y, H / 2), m)
        return
    hx0, hx1, hz0, hz1 = hole
    if hx0 > x0:
        box(name + "_L", (hx0 - x0, T, H), ((x0 + hx0) / 2, y, H / 2), m)
    if hx1 < x1:
        box(name + "_R", (x1 - hx1, T, H), ((hx1 + x1) / 2, y, H / 2), m)
    if hz0 > 0:
        box(name + "_sill", (hx1 - hx0, T, hz0), ((hx0 + hx1) / 2, y, hz0 / 2), m)
    if hz1 < H:
        box(name + "_head", (hx1 - hx0, T, H - hz1), ((hx0 + hx1) / 2, y, (hz1 + H) / 2), m)


def wall_y(name, x, y0, y1, m, hole=None):
    """沿 Y 方向展开的墙（法线朝 X）。hole=(y0,y1,z0,z1)。"""
    if hole is None:
        box(name, (T, y1 - y0, H), (x, (y0 + y1) / 2, H / 2), m)
        return
    hy0, hy1, hz0, hz1 = hole
    if hy0 > y0:
        box(name + "_A", (T, hy0 - y0, H), (x, (y0 + hy0) / 2, H / 2), m)
    if hy1 < y1:
        box(name + "_B", (T, y1 - hy1, H), (x, (hy1 + y1) / 2, H / 2), m)
    if hz0 > 0:
        box(name + "_sill", (T, hy1 - hy0, hz0), (x, (hy0 + hy1) / 2, hz0 / 2), m)
    if hz1 < H:
        box(name + "_head", (T, hy1 - hy0, H - hz1), (x, (hy0 + hy1) / 2, (hz1 + H) / 2), m)


DOOR = dict(x0=0.55, x1=1.45, z1=2.05)          # 门洞（前墙）
WIN = dict(y0=-0.70, y1=0.70, z0=0.95, z1=2.15)  # 窗洞（右墙）


def build_shell():
    box("floor", (W, D, T), (0, 0, -T / 2), M["floor"])
    box("ceiling", (W, D, T), (0, 0, H + T / 2), M["ceil"])
    wall_x("wall_back", -(D / 2 + T / 2), -W / 2 - T, W / 2 + T, M["wall"])
    wall_y("wall_left", -(W / 2 + T / 2), -D / 2, D / 2, M["wall"])
    wall_y("wall_right", (W / 2 + T / 2), -D / 2, D / 2, M["wall"],
           hole=(WIN["y0"], WIN["y1"], WIN["z0"], WIN["z1"]))
    wall_x("wall_front", (D / 2 + T / 2), -W / 2, W / 2, M["wall"],
           hole=(DOOR["x0"], DOOR["x1"], 0.0, DOOR["z1"]))
    # 踢脚线（一圈细木条，纯装饰但很提气质）
    for i, (nm, sz, lc) in enumerate([
        ("sk_back", (W, 0.03, 0.09), (0, -D / 2 + 0.015, 0.045)),
        ("sk_front_L", (DOOR["x0"] + W / 2, 0.03, 0.09), ((-W / 2 + DOOR["x0"]) / 2, D / 2 - 0.015, 0.045)),
        ("sk_front_R", (W / 2 - DOOR["x1"], 0.03, 0.09), ((DOOR["x1"] + W / 2) / 2, D / 2 - 0.015, 0.045)),
        ("sk_left", (0.03, D, 0.09), (-W / 2 + 0.015, 0, 0.045)),
    ]):
        box(nm, sz, lc, M["wood2"])


def build_door():
    x0, x1, z1 = DOOR["x0"], DOOR["x1"], DOOR["z1"]
    y = D / 2 + T / 2
    jt = 0.07
    box("door_jamb_L", (jt, T + 0.03, z1 + jt), (x0 - jt / 2, y, (z1 + jt) / 2), M["wood2"])
    box("door_jamb_R", (jt, T + 0.03, z1 + jt), (x1 + jt / 2, y, (z1 + jt) / 2), M["wood2"])
    box("door_head", (x1 - x0 + 2 * jt, T + 0.03, jt), ((x0 + x1) / 2, y, z1 + jt / 2), M["wood2"])
    # 门扇朝**走廊侧**开（+Y）：铰链在 x0 墙上，叶片不许扫进屋里挡机位
    L = (x1 - x0) - 0.02
    ang = math.radians(68)
    box("door_leaf", (L, 0.045, z1 - 0.05),
        (x0 + L / 2 * math.cos(ang), y + L / 2 * math.sin(ang), (z1 - 0.05) / 2),
        M["wood"], rot=(0, 0, ang))
    box("door_knob", (0.05, 0.05, 0.05),
        (x0 + (L - 0.12) * math.cos(ang), y + (L - 0.12) * math.sin(ang), 1.02), M["metal"])


def build_window():
    y0, y1, z0, z1 = WIN["y0"], WIN["y1"], WIN["z0"], WIN["z1"]
    x = W / 2 + T / 2
    ft = 0.06
    box("win_sill", (T + 0.10, y1 - y0 + 0.16, 0.04), (x, (y0 + y1) / 2, z0 - 0.02), M["wood2"])
    box("win_bottom", (T + 0.02, y1 - y0, ft), (x, (y0 + y1) / 2, z0 + ft / 2), M["wood2"])
    box("win_top", (T + 0.02, y1 - y0, ft), (x, (y0 + y1) / 2, z1 - ft / 2), M["wood2"])
    box("win_left", (T + 0.02, ft, z1 - z0), (x, y0 + ft / 2, (z0 + z1) / 2), M["wood2"])
    box("win_right", (T + 0.02, ft, z1 - z0), (x, y1 - ft / 2, (z0 + z1) / 2), M["wood2"])
    box("win_mullion", (T + 0.02, 0.04, z1 - z0), (x, (y0 + y1) / 2, (z0 + z1) / 2), M["wood2"])
    # 窗外夜景板：给窗子一个冷色发光面，省掉室外建模
    box("night_plate", (0.05, 6.0, 4.0), (x + 2.0, 0, 1.8), M["night"])


# ---------------------------------------------------------------- 家具道具
def build_furniture():
    bx = -W / 2 + 0.75          # 床中心 X
    bed_w, bed_l = 1.35, 2.00
    by = -D / 2 + bed_l / 2 + 0.05
    box("bed_frame", (bed_w, bed_l, 0.30), (bx, by, 0.15), M["wood"])
    box("bed_headboard", (bed_w, 0.08, 0.95), (bx, -D / 2 + 0.08, 0.48), M["wood"])
    box("bed_mattress", (bed_w - 0.06, bed_l - 0.06, 0.22), (bx, by, 0.41), M["sheet"])
    box("bed_blanket", (bed_w - 0.02, bed_l * 0.62, 0.10), (bx, by + bed_l * 0.19, 0.55), M["cloth"])
    blob("bed_pillow1", (0.72, 0.42, 0.17), (bx - 0.28, by - bed_l / 2 + 0.30, 0.60), M["pillow"])
    blob("bed_pillow2", (0.72, 0.42, 0.17), (bx + 0.28, by - bed_l / 2 + 0.30, 0.62), M["pillow"], rot=(0, 0, math.radians(8)))
    box("bed_book", (0.16, 0.22, 0.03), (bx - 0.40, by + 0.22, 0.62), M["pillow"])

    # 床头柜 + 小台灯（床右侧）
    nx = bx + bed_w / 2 + 0.26
    box("nightstand", (0.42, 0.40, 0.48), (nx, -D / 2 + 0.28, 0.24), M["wood"])
    box("nightstand_drawer", (0.34, 0.03, 0.16), (nx, -D / 2 + 0.48, 0.32), M["wood2"])
    cyl("bedside_lamp_base", 0.055, 0.02, (nx, -D / 2 + 0.28, 0.49), M["metal"])
    cyl("bedside_lamp_pole", 0.010, 0.20, (nx, -D / 2 + 0.28, 0.59), M["metal"])
    cyl("bedside_lamp_shade", 0.075, 0.11, (nx, -D / 2 + 0.28, 0.72), mat("M_shade2", (0.96, 0.90, 0.76), rough=0.6))

    # 衣柜：贴**后墙**（把左前角让给全景机位）
    wx, wy = 0.75, -D / 2 + 0.30
    box("wardrobe", (0.90, 0.60, 2.10), (wx, wy, 1.05), M["wood2"])
    box("wardrobe_split", (0.02, 0.02, 2.00), (wx, wy + 0.305, 1.05), M["dark"])
    cyl("wardrobe_knob1", 0.02, 0.06, (wx - 0.13, wy + 0.32, 1.05), M["metal"], rot=(math.pi / 2, 0, 0))
    cyl("wardrobe_knob2", 0.02, 0.06, (wx + 0.13, wy + 0.32, 1.05), M["metal"], rot=(math.pi / 2, 0, 0))

    # 书桌：贴右墙（窗户底下）
    dx = W / 2 - 0.30
    box("desk_top", (0.60, 1.40, 0.05), (dx, 0.0, 0.75), M["wood2"])
    for sx, sy in [(0.26, 0.64), (0.26, -0.64), (-0.26, 0.64), (-0.26, -0.64)]:
        box("desk_leg", (0.05, 0.05, 0.75), (dx + sx, sy, 0.375), M["wood"])
    bk = mat("M_book", (0.72, 0.25, 0.22), rough=0.85)
    for i in range(4):
        box("book%d" % i, (0.16, 0.05, 0.22 - 0.01 * i), (dx, -0.35 + i * 0.055, 0.885), bk)
    box("desk_laptop_base", (0.24, 0.33, 0.02), (dx + 0.04, 0.28, 0.785), M["dark"])
    lx = dx + 0.04 + 0.12
    lean = math.radians(20)
    box("desk_laptop_lid", (0.02, 0.33, 0.22),
        (lx + 0.11 * math.sin(lean), 0.28, 0.795 + 0.11 * math.cos(lean)), M["screen"],
        rot=(0, lean, 0))
    cyl("desk_mug", 0.045, 0.10, (dx - 0.10, -0.10, 0.83), mat("M_mug", (0.85, 0.85, 0.88), rough=0.3))
    # 台灯
    cyl("desk_lamp_base", 0.06, 0.02, (dx - 0.05, -0.58, 0.79), M["metal"])
    cyl("desk_lamp_pole", 0.012, 0.42, (dx - 0.05, -0.58, 1.00), M["metal"])
    cyl("desk_lamp_shade", 0.09, 0.12, (dx - 0.05, -0.58, 1.22), mat("M_shade", (0.95, 0.88, 0.72), rough=0.6))

    # 椅子
    cx, cy = W / 2 - 0.95, 0.0
    box("chair_seat", (0.44, 0.44, 0.06), (cx, cy, 0.45), M["wood"])
    box("chair_back", (0.06, 0.44, 0.50), (cx + 0.19, cy, 0.70), M["wood"])
    for sx, sy in [(0.18, 0.18), (0.18, -0.18), (-0.18, 0.18), (-0.18, -0.18)]:
        box("chair_leg", (0.04, 0.04, 0.45), (cx + sx, cy + sy, 0.225), M["wood"])

    # 地毯
    box("rug", (2.20, 1.60, 0.02), (-0.25, 0.75, 0.012), M["rug"])

    # 绿植
    cyl("plant_pot", 0.13, 0.24, (W / 2 - 0.30, D / 2 - 0.35, 0.12), M["pot"])
    sphere("plant_leaf1", 0.20, (W / 2 - 0.30, D / 2 - 0.35, 0.45), M["plant"])
    sphere("plant_leaf2", 0.14, (W / 2 - 0.42, D / 2 - 0.28, 0.32), M["plant"])

    # 墙上挂画（床头正上方）
    box("art_frame", (0.52, 0.03, 0.38), (-1.35, -D / 2 + 0.03, 1.70), M["frame"])
    box("art_canvas", (0.46, 0.02, 0.32), (-1.35, -D / 2 + 0.05, 1.70), M["art"])

    # 吸顶灯
    cyl("lamp_rose", 0.06, 0.03, (0, 0, H - 0.015), M["dark"])
    cyl("lamp_cord", 0.008, 0.28, (0, 0, H - 0.16), M["dark"])
    sphere("lamp_bulb", 0.11, (0, 0, H - 0.33), M["lamp"])


# ---------------------------------------------------------------- 灯与机位
def build_lights():
    # 世界环境：暗夜里一点点冷底光
    wd = bpy.data.worlds.new("World")
    bpy.context.scene.world = wd
    wd.use_nodes = True
    bg = wd.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.035, 0.040, 0.058, 1.0)
    bg.inputs[1].default_value = 1.0

    new_light("key_ceiling", 'POINT', (0, 0.15, H - 0.38), 62.0, color=(1.0, 0.88, 0.72))
    new_light("bedside_lamp", 'POINT', (-0.42, -D / 2 + 0.28, 0.74), 6.0, color=(1.0, 0.80, 0.58))
    new_light("desk_lamp", 'POINT', (W / 2 - 0.35, -0.58, 1.20), 12.0, color=(1.0, 0.82, 0.60))
    new_light("moon_sun", 'SUN', (W / 2 + 3.0, 0.8, 3.0), 1.2, color=(0.72, 0.82, 1.0), aim=(0, 0, 1.0))
    new_light("fill_door", 'AREA', (0.4, D / 2 - 0.1, 1.9), 10.0, color=(0.85, 0.90, 1.0), size=1.2, aim=(0, -0.5, 1.2))
    new_light("soft_room", 'AREA', (-0.4, 0.4, H - 0.12), 12.0, color=(1.0, 0.94, 0.86), size=2.0, aim=(-0.4, -0.4, 0.0))


SHOTS = [
    dict(name="01-establishing", lens=19.0, loc=(-1.68, 1.45, 1.62), aim=(0.55, -1.05, 1.00), note="左前角全景：床/衣柜/书桌/窗一眼看全"),
    dict(name="02-medium", lens=35.0, loc=(-0.10, 0.60, 1.18), aim=(-1.40, -1.15, 0.58), note="中景：床边（床上戏、对手戏常用机位）"),
    dict(name="03-closeup", lens=45.0, loc=(0.72, 0.80, 1.28), aim=(1.88, 0.12, 0.86), note="特写：书桌/笔记本（打字戏、伏案戏）"),
]


def build_cameras():
    out = []
    for s in SHOTS:
        out.append((s, new_camera("cam_" + s["name"], s["loc"], s["aim"], s["lens"])))
    return out


# ---------------------------------------------------------------- 渲染
def setup_render():
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = ARGS.samples
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 3
    sc.cycles.glossy_bounces = 2
    sc.cycles.transmission_bounces = 2
    sc.render.use_persistent_data = True
    sc.render.threads_mode = 'AUTO'
    sc.render.resolution_percentage = 100
    rx, ry = ARGS.res.split("x")
    sc.render.resolution_x, sc.render.resolution_y = int(rx), int(ry)
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGB'
    sc.render.image_settings.compression = 70
    sc.render.fps = FPS
    sc.view_settings.exposure = -0.9
    for vt in ('AgX', 'Filmic', 'Standard'):
        try:
            sc.view_settings.view_transform = vt
            break
        except TypeError:
            continue
    return sc


def brightness(path):
    import numpy as np
    img = bpy.data.images.load(path)
    try:
        px = np.array(img.pixels[:], dtype="float32").reshape(-1, 4)
        return float(px[:, :3].mean()), float(px[:, :3].max())
    finally:
        bpy.data.images.remove(img)


def main():
    log("blender %s / python %s" % (bpy.app.version_string, sys.version.split()[0]))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    make_materials()
    build_shell()
    build_door()
    build_window()
    build_furniture()
    build_lights()
    shots = build_cameras()
    sc = setup_render()
    os.makedirs(ARGS.outdir, exist_ok=True)

    assert_count = 0
    fails = []
    made = []
    want = [s["name"] for s, _ in shots] if ARGS.shots == "all" else ARGS.shots.split(",")
    for s, cam in shots:
        if s["name"] not in want:
            continue
        sc.camera = cam
        p = "%s/%s.png" % (ARGS.outdir, s["name"])
        sc.render.filepath = p
        log("渲染 %s（%s，%d samples，%s）" % (s["name"], s["note"], ARGS.samples, ARGS.res))
        bpy.ops.render.render(write_still=True)
        made.append(p)
        assert_count += 1
        if not os.path.exists(p):
            fails.append("缺图 " + p)
            continue
        b, mx = brightness(p)
        log("  %s  平均亮度=%.4f 峰值=%.4f  %.1f KB" % (os.path.basename(p), b, mx, os.path.getsize(p) / 1024.0))
        assert_count += 2
        if b < 0.02:
            fails.append("图过暗(疑似全黑) " + p)
        if mx < 0.3:
            fails.append("无高光/无光源 " + p)

    bpy.ops.wm.save_as_mainfile(filepath=ARGS.blend)
    assert_count += 1
    if not os.path.exists(ARGS.blend):
        fails.append("blend 没存下 " + ARGS.blend)

    report = dict(name=ARGS.name, blender=bpy.app.version_string, room=dict(w=W, d=D, h=H),
                  samples=ARGS.samples, res=ARGS.res, engine='CYCLES/CPU',
                  objects=len([o for o in bpy.data.objects if o.type == 'MESH']),
                  lights=len([o for o in bpy.data.objects if o.type == 'LIGHT']),
                  shots=[dict(name=s["name"], lens=s["lens"], loc=list(s["loc"]), aim=list(s["aim"]), note=s["note"]) for s, _ in shots],
                  renders=[os.path.basename(p) for p in made], blend=os.path.basename(ARGS.blend))
    rp = os.path.join(ARGS.outdir, "scene_report.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    assert_count += 3
    if report["objects"] < 30:
        fails.append("家具太少 objects=%d" % report["objects"])
    if report["lights"] < 4:
        fails.append("灯太少 lights=%d" % report["lights"])
    if len(report["shots"]) != len(SHOTS):
        fails.append("机位不是 %d 个" % len(SHOTS))

    log("场景物件 %d 个（灯 %d），出图 %d 张，blend %s" % (report["objects"], report["lights"], len(made), ARGS.blend))
    print("__SELFTEST__ %d %d" % (assert_count, len(fails)), flush=True)
    for f in fails:
        print("[room] FAIL: " + f, flush=True)
    if fails:
        sys.exit(2)


main()
