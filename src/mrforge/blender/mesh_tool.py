"""Headless Blender helper for mrforge (run: blender -b --factory-startup --python mesh_tool.py -- <cmd> ...).

Commands
  import <addon_parent> <file.uemodel> <out.blend>   import with ueformat-blender (never installed), save
  fbx <in.blend> <out.fbx>                           export FBX without leaf bones
  summary <in.blend>                                 print bones, material slots, vertex groups, counts
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


def main(argv):
    cmd = argv[0]
    if cmd == "import":
        addon_parent, src, out = argv[1], Path(argv[2]), argv[3]
        bpy.ops.wm.read_factory_settings(use_empty=True)  # empty scene: no default cube in the summary
        sys.path.insert(0, addon_parent)
        import io_scene_ueformat
        io_scene_ueformat.register()
        r = bpy.ops.uf.import_uemodel(files=[{"name": src.name}], directory=str(src.parent))
        bpy.ops.wm.save_as_mainfile(filepath=out)
        res = {"result": list(r), **summary()}
    elif cmd == "fbx":
        bpy.ops.wm.open_mainfile(filepath=argv[1])
        bpy.ops.export_scene.fbx(filepath=argv[2], add_leaf_bones=False, use_selection=False,
                                 object_types={"ARMATURE", "MESH"}, mesh_smooth_type="FACE")
        res = {"fbx": argv[2], **summary()}
    elif cmd == "summary":
        bpy.ops.wm.open_mainfile(filepath=argv[1])
        res = summary()
    else:
        raise SystemExit(f"unknown command {cmd}")
    print("MRFORGE_JSON:" + json.dumps(res))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
