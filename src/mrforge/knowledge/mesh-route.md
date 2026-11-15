# Mesh route (v0.2) and physics

Status in v0.1: not shipped. `mrforge doctor` shows `mesh-export` and `mesh-build` availability.

Planned flow (decisions D6/D7):
1. Export: fmodel-mcp over stdio -> `.uemodel` + material JSON + PNG. When a deployed mod overrides the target, the
   export comes from the mod; v0.2 uses a temporary vanilla view (hardlinks of the top-level containers).
2. Blender: ueformat-blender imported headless (no add-on install). Edit, keep bone names, material slot names
   and their order, export FBX without leaf bones.
3. Unreal Engine 5.3.2: project named `Marvel`, IoStore off, plugins KawaiiPhysicsRivals 2.1.0 and
   RivalsMeshMaterialManager 1.2.0. Import the FBX at the vanilla package path bound to placeholder Skeleton and
   material assets at the vanilla paths; cook; pack the cooked mesh without the placeholders.
4. Validate: no skeleton/physics leak, material slot tags equal vanilla (`skeletal_mesh_info`), lobby mesh paired.

Verified so far: fmodel-mcp export of `SK_1061_1061303` (17 s), Blender import (81,410 vertices, 18 materials,
488 bones), material slots and `MaterialTag.*` tags via `skeletal_mesh_info`, UE 5.3.2 detection.

Physics (jiggle/cloth): later; `retoc-rivals-cli fix-kawaii-physics` and `--kawaii-options-json` are the base.
