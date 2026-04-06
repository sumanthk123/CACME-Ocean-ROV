"""Headless test: verify that forces actually move rigid bodies in Isaac Sim.

Tests both PhysxForceAPI and physx_simulation_interface approaches to determine
which one actually works for applying external forces per physics step.
"""

import sys
sys.path.insert(0, '/home/Talik/isaacsim/extsUser/OceanSim')

from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": True})

import numpy as np
import carb
import omni.timeline
from pxr import Gf, UsdGeom, UsdPhysics, PhysxSchema, Sdf, UsdUtils, PhysicsSchemaTools
from isaacsim.core.utils.stage import get_current_stage
from isaacsim.core.prims import SingleRigidPrim

# Let extensions load
for _ in range(10):
    simulation_app.update()

stage = get_current_stage()

print("=" * 60)
print("Force Application Test")
print("=" * 60)

# Create a simple rigid body cube
prim_path = "/World/test_cube"
xform = UsdGeom.Xform.Define(stage, prim_path)
cube = UsdGeom.Cube.Define(stage, prim_path + "/mesh")
cube.GetSizeAttr().Set(0.1)

# Add rigid body physics
UsdPhysics.RigidBodyAPI.Apply(xform.GetPrim())
UsdPhysics.MassAPI.Apply(xform.GetPrim())
mass_api = UsdPhysics.MassAPI(xform.GetPrim())
mass_api.GetMassAttr().Set(5.0)

# Add collision
UsdPhysics.CollisionAPI.Apply(cube.GetPrim())

# Set initial position
xform.AddTranslateOp().Set(Gf.Vec3f(0, 2, 0))

# Create ground plane so gravity has something to interact with
# (without it the cube just falls forever)

simulation_app.update()
simulation_app.update()

prim = xform.GetPrim()
rob_prim = SingleRigidPrim(prim_path=prim_path)

# Get initial position
pos0 = np.array(rob_prim.get_world_pose()[0])
print(f"\nInitial position: {pos0.round(4)}")

# ===== Test 1: PhysxForceAPI with mode='force', worldFrame=True =====
print("\n--- Test 1: PhysxForceAPI (mode=force, worldFrame=True) ---")
force_api = PhysxSchema.PhysxForceAPI.Apply(prim)
force_api.CreateModeAttr().Set("force")
force_api.CreateWorldFrameEnabledAttr().Set(True)

# Apply 100N upward for 60 frames
timeline = omni.timeline.get_timeline_interface()
timeline.play()

for i in range(60):
    force_api.GetForceAttr().Set(Gf.Vec3f(0, 100, 0))
    simulation_app.update()

timeline.pause()
pos1 = np.array(rob_prim.get_world_pose()[0])
delta1 = pos1 - pos0
print(f"Position after 60 frames of 100N up: {pos1.round(4)}")
print(f"Delta: {delta1.round(4)}")
print(f"Moved upward: {'YES' if delta1[1] > 0.01 else 'NO'}")

# Reset position
timeline.stop()
simulation_app.update()
xform.GetPrim().GetAttribute('xformOp:translate').Set(Gf.Vec3f(0, 2, 0))
simulation_app.update()
simulation_app.update()

# ===== Test 2: PhysxForceAPI with default mode (acceleration) =====
print("\n--- Test 2: PhysxForceAPI (default mode=acceleration, localFrame) ---")
force_api2 = PhysxSchema.PhysxForceAPI.Apply(prim)
# Reset to defaults
force_api2.CreateModeAttr().Set("acceleration")
force_api2.CreateWorldFrameEnabledAttr().Set(False)

timeline.play()
for i in range(60):
    force_api2.GetForceAttr().Set(Gf.Vec3f(10, 0, 0))
    simulation_app.update()

timeline.pause()
pos2 = np.array(rob_prim.get_world_pose()[0])
delta2 = pos2 - np.array([0, 2, 0])
print(f"Position after 60 frames of 10 accel X: {pos2.round(4)}")
print(f"Delta: {delta2.round(4)}")
print(f"Moved in X: {'YES' if abs(delta2[0]) > 0.01 else 'NO'}")

# Reset
timeline.stop()
simulation_app.update()
xform.GetPrim().GetAttribute('xformOp:translate').Set(Gf.Vec3f(0, 2, 0))
simulation_app.update()
simulation_app.update()

# ===== Test 3: physx_simulation_interface.apply_force_at_pos =====
print("\n--- Test 3: physx_simulation_interface.apply_force_at_pos ---")
from omni.physx import get_physx_simulation_interface

stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
body_id = PhysicsSchemaTools.sdfPathToInt(prim.GetPath())

# Clear any PhysxForceAPI forces
force_api.GetForceAttr().Set(Gf.Vec3f(0, 0, 0))

timeline.play()
psi = get_physx_simulation_interface()
for i in range(60):
    psi.apply_force_at_pos(
        stage_id, body_id,
        carb.Float3(0, 100, 0),  # 100N upward
        carb.Float3(0, 2, 0)     # at position
    )
    simulation_app.update()

timeline.pause()
pos3 = np.array(rob_prim.get_world_pose()[0])
delta3 = pos3 - np.array([0, 2, 0])
print(f"Position after 60 frames of 100N up via PSI: {pos3.round(4)}")
print(f"Delta: {delta3.round(4)}")
print(f"Moved upward: {'YES' if delta3[1] > 0.01 else 'NO'}")

# Reset
timeline.stop()
simulation_app.update()
xform.GetPrim().GetAttribute('xformOp:translate').Set(Gf.Vec3f(0, 2, 0))
simulation_app.update()
simulation_app.update()

# ===== Test 4: Forward thrust via PSI =====
print("\n--- Test 4: Forward thrust 50N via PSI ---")
force_api.GetForceAttr().Set(Gf.Vec3f(0, 0, 0))

timeline.play()
for i in range(60):
    psi.apply_force_at_pos(
        stage_id, body_id,
        carb.Float3(50, 0, 0),   # 50N forward
        carb.Float3(0, 2, 0)
    )
    simulation_app.update()

timeline.pause()
pos4 = np.array(rob_prim.get_world_pose()[0])
delta4 = pos4 - np.array([0, 2, 0])
print(f"Position after 60 frames of 50N forward via PSI: {pos4.round(4)}")
print(f"Delta: {delta4.round(4)}")
print(f"Moved in X: {'YES' if abs(delta4[0]) > 0.01 else 'NO'}")

print("\n" + "=" * 60)
print("SUMMARY:")
print(f"  PhysxForceAPI (force/world):    {'WORKS' if delta1[1] > 0.01 else 'BROKEN'}")
print(f"  PhysxForceAPI (accel/local):    {'WORKS' if abs(delta2[0]) > 0.01 else 'BROKEN'}")
print(f"  PSI apply_force_at_pos (up):    {'WORKS' if delta3[1] > 0.01 else 'BROKEN'}")
print(f"  PSI apply_force_at_pos (fwd):   {'WORKS' if abs(delta4[0]) > 0.01 else 'BROKEN'}")
print("=" * 60)

simulation_app.close()
