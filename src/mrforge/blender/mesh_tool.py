"""Headless Blender helper for mrforge (run: blender -b --factory-startup --python mesh_tool.py -- <cmd> ...).

Commands
  import <addon_parent> <file.uemodel> <out.blend>   import with ueformat-blender (never installed), save
  fbx <in.blend> <out.fbx>                           export FBX without leaf bones
  summary <in.blend>                                 print bones, material slots, vertex groups, counts
  inflate <in.blend> <spec.json>                     scale the skin around bones by their weights, save in place
  render <in.blend> <out_prefix> [focus_bone]        front + side workbench renders (<prefix>_front.png, _side.png)
Every command prints one line `MRFORGE_JSON:{...}`.
"""
import hashlib
import json
import sys
from pathlib import Path

import bpy


def summary() -> dict:
    meshes, arms = [], []
    for ob in bpy.data.objects:
        if ob.type == "MESH":
            me = ob.data
            me.calc_loop_triangles()
            meshes.append({"name": ob.name, "vertices": len(me.vertices), "triangles": len(me.loop_triangles),
                           "material_slots": [s.material.name if s.material else s.name for s in ob.material_slots],
                           "vertex_groups": [g.name for g in ob.vertex_groups]})
        elif ob.type == "ARMATURE":
            bones = [{"name": b.name, "parent": b.parent.name if b.parent else None} for b in ob.data.bones]
            h = hashlib.sha256(json.dumps(bones).encode()).hexdigest()
            arms.append({"name": ob.name, "bone_count": len(bones), "bones": bones, "hierarchy_sha256": h})
    return {"meshes": meshes, "armatures": arms}


def inflate(spec: dict) -> dict:
    """Push vertices away from (factor > 1) or toward (< 1) each listed bone's head, scaled by how much the vertex
    follows that bone or its children. Bones, weights and material slots stay as they are; shape keys get the same
    offset so their deltas are kept."""
    from mathutils import Vector
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if len(arms) != 1:
        raise SystemExit(f"expected one armature, found {len(arms)}")
    arm = arms[0]
    report = []
    for ob in [o for o in bpy.data.objects if o.type == "MESH"]:
        me = ob.data
        to_obj = ob.matrix_world.inverted() @ arm.matrix_world
        moved, max_off = 0, 0.0
        offsets = [Vector((0.0, 0.0, 0.0)) for _ in me.vertices]
        for item in spec["bones"]:
            bone = arm.data.bones.get(item["bone"])
            if bone is None:
                raise SystemExit(f"bone {item['bone']} not in the armature")
            names = {bone.name} | ({c.name for c in bone.children_recursive} if spec.get("children", True) else set())
            groups = {g.index for g in ob.vertex_groups if g.name in names}
            if not groups:
                continue
            center = to_obj @ bone.head_local
            f = float(item.get("factor", spec.get("factor", 1.2))) - 1.0
            for v in me.vertices:
                w = min(1.0, sum(e.weight for e in v.groups if e.group in groups))
                if w <= 0.0:
                    continue
                offsets[v.index] += (v.co - center) * (f * w)
        keys = me.shape_keys.key_blocks if me.shape_keys else None
        for v, off in zip(me.vertices, offsets):
            if off.length == 0.0:
                continue
            moved += 1
            max_off = max(max_off, off.length)
            v.co += off
            if keys:
                for kb in keys:
                    kb.data[v.index].co += off
        me.update()
        report.append({"mesh": ob.name, "moved_vertices": moved, "max_offset": round(max_off, 4)})
    return {"inflate": report}


def render(prefix: str, focus: str | None) -> dict:
    import math
    from mathutils import Vector
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if focus and focus in arm.data.bones:
        center = arm.matrix_world @ arm.data.bones[focus].head_local
        scale = 0.6
    else:
        pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        center, scale = (lo + hi) / 2, max(hi - lo) * 1.05
    sc = bpy.context.scene
    for o in list(bpy.data.objects):
        if o.type not in ("MESH", "ARMATURE"):
            bpy.data.objects.remove(o)
    cam = bpy.data.cameras.new("mrf_cam")
    cam.type, cam.ortho_scale = "ORTHO", scale
    co = bpy.data.objects.new("mrf_cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "SINGLE"
    sc.render.resolution_x = sc.render.resolution_y = 512
    out = {}
    # The character faces -Y (Unreal forward imported by UEFormat): front camera on -Y, side camera on +X.
    for view, off, rot in (("front", Vector((0, -3, 0)), (math.radians(90), 0, 0)),
                           ("side", Vector((3, 0, 0)), (math.radians(90), 0, math.radians(90)))):
        co.location = center + off
        co.rotation_euler = rot
        sc.render.filepath = f"{prefix}_{view}.png"
        bpy.ops.render.render(write_still=True)
        out[view] = sc.render.filepath
    return {"renders": out}


def main(argv):
    cmd = argv[0]
    if cmd == "import":
        addon_parent, src, out = argv[1], Path(argv[2]), argv[3]
        bpy.ops.wm.read_factory_settings(use_empty=True)  # empty scene: no default cube in the summary
        sys.path.insert(0, addon_parent)
        import io_scene_ueformat
        io_scene_ueformat.register()
        # Sockets would come in as extra bones (some without a parent), so the armature would no longer equal the
        # mesh's reference skeleton and Unreal refuses multiple roots. The game keeps its sockets on its side.
        bpy.context.scene.uf_settings.import_sockets = False
        bpy.context.scene.uf_settings.import_virtual_bones = False
        r = bpy.ops.uf.import_uemodel(files=[{"name": src.name}], directory=str(src.parent))
        bpy.ops.wm.save_as_mainfile(filepath=out)
        res = {"result": list(r), **summary()}
    elif cmd == "fbx":
        bpy.ops.wm.open_mainfile(filepath=argv[1])
        arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
        if len(arms) == 1:
            # Unreal's FBX importer drops an armature object named "Armature"; any other name becomes an extra root
            # bone and the hierarchy no longer matches the game's skeleton.
            arms[0].name = "Armature"
        if len(argv) > 3:
            # One unique material per slot, named exactly like the game's slot. Blender names materials after the
            # material asset, so two slots sharing one material would merge into a single FBX material.
            names = json.load(open(argv[3], encoding="utf-8"))
            meshes = [o for o in bpy.data.objects if o.type == "MESH"]
            if len(meshes) != 1:
                raise SystemExit(f"expected one mesh object, found {len(meshes)}")
            ob = meshes[0]
            if len(ob.material_slots) != len(names):
                raise SystemExit(f"mesh has {len(ob.material_slots)} slots, game has {len(names)}")
            old = {sl.material for sl in ob.material_slots if sl.material}
            fresh = []
            for i, sl in enumerate(ob.material_slots):
                m = bpy.data.materials.new(name=f"__mrf_slot_{i}")
                sl.material = m
                fresh.append(m)
            for m in old:
                if m.users == 0:
                    bpy.data.materials.remove(m)
            for m, name in zip(fresh, names):
                m.name = name
            got = [sl.material.name for sl in ob.material_slots]
            if got != names:
                raise SystemExit(f"slot names did not apply: {got}")
        bpy.ops.export_scene.fbx(filepath=argv[2], add_leaf_bones=False, use_selection=False,
                                 object_types={"ARMATURE", "MESH"}, mesh_smooth_type="FACE")
        res = {"fbx": argv[2], **summary()}
    elif cmd == "inflate":
        bpy.ops.wm.open_mainfile(filepath=argv[1])
        res = inflate(json.load(open(argv[2], encoding="utf-8")))
        bpy.ops.wm.save_as_mainfile(filepath=argv[1])
        res.update(summary())
    elif cmd == "render":
        bpy.ops.wm.open_mainfile(filepath=argv[1])
        res = render(argv[2], argv[3] if len(argv) > 3 else None)
    elif cmd == "summary":
        bpy.ops.wm.open_mainfile(filepath=argv[1])
        res = summary()
    else:
        raise SystemExit(f"unknown command {cmd}")
    print("MRFORGE_JSON:" + json.dumps(res))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
