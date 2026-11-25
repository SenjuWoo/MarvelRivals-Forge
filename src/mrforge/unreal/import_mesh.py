"""Runs inside UnrealEditor-Cmd (-run=pythonscript). Job JSON path in env MRFORGE_UE_JOB.

Imports the FBX at the vanilla package path and binds it to placeholder assets created at the vanilla paths of
the skeleton, physics asset, post-process AnimBP and material instances. The placeholders keep the cooked
mesh's imports pointing at the game's own assets; they are never packed.
Prints one line `MRFORGE_JSON:{...}` with what was created.
"""
import json
import os

import unreal

job = json.load(open(os.environ["MRFORGE_UE_JOB"], encoding="utf-8"))
tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
report = {"steps": [], "warnings": []}


def split(path):
    folder, name = path.rsplit("/", 1)
    return folder, name


def step(msg):
    report["steps"].append(msg)
    unreal.log("MRFORGE " + msg)


for p in [job["mesh_path"], job["skeleton_path"], job.get("physics_path"), job.get("postprocess_path")] + \
        [m["path"] for m in job["materials"]]:
    if p and eal.does_asset_exist(p):
        eal.delete_asset(p)

folder, name = split(job["mesh_path"])
task = unreal.AssetImportTask()
task.set_editor_property("filename", job["fbx"])
task.set_editor_property("destination_path", folder)
task.set_editor_property("destination_name", name)
task.set_editor_property("automated", True)
task.set_editor_property("replace_existing", True)
task.set_editor_property("save", False)
ui = unreal.FbxImportUI()
ui.set_editor_property("import_mesh", True)
ui.set_editor_property("import_as_skeletal", True)
ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
ui.set_editor_property("import_materials", False)
ui.set_editor_property("import_textures", False)
ui.set_editor_property("import_animations", False)
ui.set_editor_property("create_physics_asset", bool(job.get("physics_path")))
sk = ui.get_editor_property("skeletal_mesh_import_data")
sk.set_editor_property("import_morph_targets", True)
sk.set_editor_property("use_t0_as_ref_pose", False)
sk.set_editor_property("convert_scene", True)
# Keep the FBX's normals (they equal vanilla); with the scripted default Unreal recomputed them and seams at the
# waist, hands and head shaded faceted (measured 2026-11-25: p95 13 deg off vanilla).
sk.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
task.set_editor_property("options", ui)
tools.import_asset_tasks([task])
mesh = eal.load_asset(job["mesh_path"])
if not mesh:
    print("MRFORGE_JSON:" + json.dumps({"error": "FBX import produced no skeletal mesh", **report}))
    raise SystemExit(1)
step("imported " + job["mesh_path"])

skel = mesh.get_editor_property("skeleton")
if eal.rename_asset(skel.get_path_name().split(".")[0], job["skeleton_path"]):
    step("skeleton -> " + job["skeleton_path"])
else:
    report["warnings"].append("skeleton rename failed")

if job.get("physics_path"):
    phys = mesh.get_editor_property("physics_asset")
    if phys and eal.rename_asset(phys.get_path_name().split(".")[0], job["physics_path"]):
        step("physics asset -> " + job["physics_path"])
    else:
        report["warnings"].append("physics asset missing or rename failed")

if job.get("postprocess_path"):
    pf, pn = split(job["postprocess_path"])
    fac = unreal.AnimBlueprintFactory()
    fac.set_editor_property("target_skeleton", eal.load_asset(job["skeleton_path"]))
    fac.set_editor_property("parent_class", unreal.AnimInstance)
    bp = tools.create_asset(pn, pf, unreal.AnimBlueprint, fac)
    if bp:
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        mesh.set_editor_property("post_process_anim_blueprint", unreal.BlueprintEditorLibrary.generated_class(bp))
        step("post-process AnimBP -> " + job["postprocess_path"])
    else:
        report["warnings"].append("post-process AnimBP not created")

parent = unreal.load_asset("/Engine/EngineMaterials/WorldGridMaterial")
by_slot = {m["slot"]: m["path"] for m in job["materials"]}
mats = mesh.get_editor_property("materials")
slots = []
new = []
for sm in mats:
    slot = str(sm.get_editor_property("material_slot_name"))
    slots.append(slot)
    target = by_slot.get(slot)
    if not target:
        report["warnings"].append(f"slot {slot} has no vanilla material")
        new.append(sm)
        continue
    mf, mn = split(target)
    mi = eal.load_asset(target) if eal.does_asset_exist(target) else \
        tools.create_asset(mn, mf, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if mi.get_editor_property("parent") is None:
        mi.set_editor_property("parent", parent)
    sm.set_editor_property("material_interface", mi)
    new.append(sm)
mesh.set_editor_property("materials", new)
step(f"{len(slots)} material slots bound")

# Per-slot gameplay tags as RivalsMeshMaterialManager user data; UAssetTool injects them into
# FSkeletalMaterial::GameplayTagContainer when packing and strips the user data.
tag_entries = []
bad_tags = []
for m in job["materials"]:
    e = unreal.MaterialSlotTagEntry()
    e.set_editor_property("material_slot_name", m["slot"])
    gts = []
    for t in m["tags"]:
        g = unreal.GameplayTag()
        g.import_text('(TagName="%s")' % t)
        if str(g.get_editor_property("tag_name")) != t:
            bad_tags.append(t)
        ge = unreal.GameplayTagEntry()
        ge.set_editor_property("tag", g)
        gts.append(ge)
    e.set_editor_property("gameplay_tags", gts)
    tag_entries.append(e)
ud = unreal.new_object(unreal.MaterialTagAssetUserData, outer=mesh)
ud.set_editor_property("material_slot_tags", tag_entries)
mesh.set_editor_property("asset_user_data", [ud])
if bad_tags:
    report["warnings"].append(f"tags not registered: {sorted(set(bad_tags))}")
step(f"material tag user data: {sum(len(m['tags']) for m in job['materials'])} tags on {len(tag_entries)} slots")
report["slots"] = slots
report["vanilla_slots"] = [m["slot"] for m in job["materials"]]
report["slot_order_matches"] = slots == report["vanilla_slots"]
eal.save_directory("/Game/Marvel", only_if_is_dirty=False, recursive=True)
step("saved")
print("MRFORGE_JSON:" + json.dumps(report))
