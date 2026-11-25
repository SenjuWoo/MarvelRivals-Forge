"""Runs inside UnrealEditor-Cmd (-run=pythonscript). Job JSON path in env MRFORGE_UE_JOB.

Builds a post-process AnimBlueprint at the vanilla path of the skin's lobby (or any) Post_<skin>_*Physics asset:
1. import the mesh FBX at a scratch path so its skeleton exists, then move that skeleton to the vanilla path
2. create the AnimBlueprint (parent AnimInstance) on that skeleton
3. rebuild the vanilla graph from the FModel JSON with the KawaiiPhysicsRivals importer (stubs for referenced assets)
4. MrforgeAnimTools: link the graph input/output, append spring-bone jiggle nodes, compile
Only the AnimBlueprint is collected after the cook; the mesh, skeleton and stubs never leave the project.
Prints one line `MRFORGE_JSON:{...}`.
"""
import json
import os

import unreal

job = json.load(open(os.environ["MRFORGE_UE_JOB"], encoding="utf-8"))
tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
report = {"steps": [], "warnings": []}


def done(**kw):
    print("MRFORGE_JSON:" + json.dumps({**report, **kw}))


def step(msg):
    report["steps"].append(msg)
    unreal.log("MRFORGE " + msg)


for p in (job["abp_path"], job["skeleton_path"], job["mesh_tmp_path"]):
    if eal.does_asset_exist(p):
        eal.delete_asset(p)

folder, name = job["mesh_tmp_path"].rsplit("/", 1)
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
ui.set_editor_property("create_physics_asset", False)
sk = ui.get_editor_property("skeletal_mesh_import_data")
sk.set_editor_property("import_morph_targets", False)
sk.set_editor_property("convert_scene", True)
task.set_editor_property("options", ui)
tools.import_asset_tasks([task])
mesh = eal.load_asset(job["mesh_tmp_path"])
if not mesh:
    done(error="FBX import produced no skeletal mesh")
    raise SystemExit(1)
skel = mesh.get_editor_property("skeleton")
if not eal.rename_asset(skel.get_path_name().split(".")[0], job["skeleton_path"]):
    done(error="skeleton rename failed")
    raise SystemExit(1)
skel = eal.load_asset(job["skeleton_path"])
step(f"skeleton {job['skeleton_path']} ({len(skel.get_editor_property('bone_tree')) if hasattr(skel, 'bone_tree') else '?'} bones)")

af, an = job["abp_path"].rsplit("/", 1)
fac = unreal.AnimBlueprintFactory()
fac.set_editor_property("target_skeleton", skel)
fac.set_editor_property("parent_class", unreal.AnimInstance)
bp = tools.create_asset(an, af, unreal.AnimBlueprint, fac)
if not bp:
    done(error="AnimBlueprint not created")
    raise SystemExit(1)
step("AnimBlueprint " + job["abp_path"])

imported = {"nodes": 0}
if job.get("fmodel_json"):
    res = unreal.KawaiiPhysicsJsonImporter.import_from_json_file(bp, job["fmodel_json"], True, True)
    imported = {"ok": bool(res.success), "nodes": int(res.nodes_created), "links": int(res.links_restored),
                "skipped_node_types": [str(x) for x in res.skipped_node_types],
                "stubs": [str(x) for x in res.created_stub_assets],
                "unresolved": [str(x) for x in res.unresolved_asset_references], "message": str(res.message)}
    report["import"] = imported
    if not res.success:
        done(error="vanilla graph import failed: " + str(res.message))
        raise SystemExit(1)
    if imported["skipped_node_types"] and not job.get("allow_skipped"):
        # A skipped node would be bridged by the input-pose wiring and silently drop vanilla behaviour.
        done(error="importer skipped node types: " + ", ".join(imported["skipped_node_types"]))
        raise SystemExit(1)
    step(f"vanilla graph: {imported['nodes']} nodes, {imported['links']} links, {len(imported['stubs'])} stubs")

fin = json.loads(unreal.MrforgeAnimGraphLibrary.finish_post_process_graph(bp, json.dumps(job["spec"])))
report["finish"] = fin
report["graph"] = json.loads(unreal.MrforgeAnimGraphLibrary.describe_anim_graph(bp))
if not fin.get("ok"):
    done(error="graph finish/compile failed: " + "; ".join(fin.get("messages", [])) + " " + str(fin.get("status")))
    raise SystemExit(1)
step(f"graph finished: {fin.get('springs')} springs after {fin.get('tail')}, compiled")

eal.save_directory("/Game", only_if_is_dirty=False, recursive=True)
step("saved")
done(ok=True)
