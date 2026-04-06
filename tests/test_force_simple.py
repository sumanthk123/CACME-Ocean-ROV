"""Test force application - runs inside Kit via --exec flag."""

import asyncio
import carb
import omni.kit.app
import omni.timeline
import omni.usd
import numpy as np
from pxr import Gf, UsdGeom, UsdPhysics, PhysxSchema, UsdUtils, PhysicsSchemaTools

async def run_test():
    R = "/tmp/force_test_results.txt"
    with open(R, "w") as f:
        f.write("Force Application Test\n")

    stage = omni.usd.get_context().get_stage()

    # Create rigid body cube
    prim_path = "/World/test_box"
    xform = UsdGeom.Xform.Define(stage, prim_path)
    cube = UsdGeom.Cube.Define(stage, prim_path + "/mesh")
    cube.GetSizeAttr().Set(0.1)
    UsdPhysics.RigidBodyAPI.Apply(xform.GetPrim())
    mass_api = UsdPhysics.MassAPI.Apply(xform.GetPrim())
    mass_api.GetMassAttr().Set(5.0)
    UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
    xform.AddTranslateOp().Set(Gf.Vec3f(0, 2, 0))

    await omni.kit.app.get_app().next_update_async()
    await omni.kit.app.get_app().next_update_async()

    prim = xform.GetPrim()

    def get_pos():
        p = prim.GetAttribute('xformOp:translate').Get()
        return [float(p[0]), float(p[1]), float(p[2])]

    def log(msg):
        carb.log_warn(msg)
        with open(R, "a") as f:
            f.write(msg + "\n")

    pos0 = get_pos()
    log(f"Initial: {pos0}")

    # ===== Test A: PhysxForceAPI mode=force worldFrame=True =====
    log("\n--- Test A: PhysxForceAPI (force/world) ---")
    fa = PhysxSchema.PhysxForceAPI.Apply(prim)
    fa.CreateModeAttr().Set("force")
    fa.CreateWorldFrameEnabledAttr().Set(True)

    timeline = omni.timeline.get_timeline_interface()
    timeline.play()
    for i in range(60):
        fa.GetForceAttr().Set(Gf.Vec3f(0, 100, 0))
        await omni.kit.app.get_app().next_update_async()
    timeline.pause()
    posA = get_pos()
    log(f"After 60 frames 100N up: {[round(x,4) for x in posA]}")
    log(f"Y delta: {posA[1]-pos0[1]:.4f} -> {'WORKS' if posA[1]-pos0[1] > 0.01 else 'BROKEN'}")

    # Reset
    timeline.stop()
    fa.GetForceAttr().Set(Gf.Vec3f(0, 0, 0))
    await omni.kit.app.get_app().next_update_async()
    prim.GetAttribute('xformOp:translate').Set(Gf.Vec3f(0, 2, 0))
    await omni.kit.app.get_app().next_update_async()

    # ===== Test B: PhysxForceAPI default (acceleration/local) =====
    log("\n--- Test B: PhysxForceAPI (accel/local) ---")
    fa.CreateModeAttr().Set("acceleration")
    fa.CreateWorldFrameEnabledAttr().Set(False)

    timeline.play()
    for i in range(60):
        fa.GetForceAttr().Set(Gf.Vec3f(10, 0, 0))
        await omni.kit.app.get_app().next_update_async()
    timeline.pause()
    posB = get_pos()
    log(f"After 60 frames 10 accel X: {[round(x,4) for x in posB]}")
    log(f"X delta: {posB[0]:.4f} -> {'WORKS' if abs(posB[0]) > 0.01 else 'BROKEN'}")

    # Reset
    timeline.stop()
    fa.GetForceAttr().Set(Gf.Vec3f(0, 0, 0))
    fa.CreateModeAttr().Set("force")
    await omni.kit.app.get_app().next_update_async()
    prim.GetAttribute('xformOp:translate').Set(Gf.Vec3f(0, 2, 0))
    await omni.kit.app.get_app().next_update_async()

    # ===== Test C: physx_simulation_interface =====
    log("\n--- Test C: PSI apply_force_at_pos ---")
    from omni.physx import get_physx_simulation_interface
    stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
    body_id = PhysicsSchemaTools.sdfPathToInt(prim.GetPath())
    psi = get_physx_simulation_interface()

    timeline.play()
    for i in range(60):
        psi.apply_force_at_pos(stage_id, body_id, carb.Float3(0, 100, 0), carb.Float3(0, 2, 0))
        await omni.kit.app.get_app().next_update_async()
    timeline.pause()
    posC = get_pos()
    log(f"After 60 frames 100N up via PSI: {[round(x,4) for x in posC]}")
    log(f"Y delta: {posC[1]-2.0:.4f} -> {'WORKS' if posC[1]-2.0 > 0.01 else 'BROKEN'}")

    # Reset
    timeline.stop()
    await omni.kit.app.get_app().next_update_async()
    prim.GetAttribute('xformOp:translate').Set(Gf.Vec3f(0, 2, 0))
    await omni.kit.app.get_app().next_update_async()

    # ===== Test D: Forward 50N via PSI =====
    log("\n--- Test D: PSI 50N forward ---")
    timeline.play()
    for i in range(60):
        psi.apply_force_at_pos(stage_id, body_id, carb.Float3(50, 0, 0), carb.Float3(0, 2, 0))
        await omni.kit.app.get_app().next_update_async()
    timeline.pause()
    posD = get_pos()
    log(f"After 60 frames 50N fwd via PSI: {[round(x,4) for x in posD]}")
    log(f"X delta: {posD[0]:.4f} -> {'WORKS' if abs(posD[0]) > 0.01 else 'BROKEN'}")

    log("\nDONE")
    omni.kit.app.get_app().post_quit()

asyncio.ensure_future(run_test())
