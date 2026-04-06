# Omniverse import
import numpy as np
from pxr import Gf, PhysxSchema, UsdLux, UsdGeom, UsdShade, Sdf

# Isaac sim import
from isaacsim.core.prims import SingleRigidPrim, SingleGeometryPrim
from isaacsim.core.utils.prims import get_prim_path, get_prim_at_path, delete_prim, create_prim
from isaacsim.core.utils.stage import get_current_stage, add_reference_to_stage
from isaacsim.core.utils.semantics import add_update_semantics

_REFERENCE_INTENSITY = 50000.0

# Built-in primitive types that can be spawned instantly (no USD file needed)
_BUILTIN_PRIMS = {"Cube", "Sphere", "Cylinder", "Cone", "Capsule", "Torus"}


class MHL_Sensor_Example_Scenario():
    def __init__(self):
        self._rob = None
        self._sonar = None
        self._cam = None
        self._DVL = None
        self._baro = None
        self._ctrl_mode = None
        self._running_scenario = False
        self._time = 0.0
        self._env_light_path = "/World/env_dashboard_light"
        self._rov_physics = None
        self._use_rov_physics = False

    def setup_scenario(self, rob, sonar, cam, DVL, baro, ctrl_mode, use_rov_physics=False):
        self._rob = rob
        self._sonar = sonar
        self._cam = cam
        self._DVL = DVL
        self._baro = baro
        self._ctrl_mode = ctrl_mode
        self._use_rov_physics = use_rov_physics
        if use_rov_physics:
            from ...utils.rov_physics import ROVPhysicsModel
            self._rov_physics = ROVPhysicsModel(prim=self._rob)
            self._rov_physics.reset()
        if self._sonar is not None:
            self._sonar.sonar_initialize(include_unlabelled=True)
            from isaacsim.oceansim.modules.sonar_web_dashboard.sonar_bridge import register_sonar
            register_sonar(self._sonar._name, self._sonar)
        if self._cam is not None:
            self._cam.initialize()
            from isaacsim.oceansim.modules.sonar_web_dashboard.environment_bridge import register_camera
            register_camera(self._cam._name, self._cam)
        if self._DVL is not None:
            self._DVL_reading = [0.0, 0.0, 0.0]
        if self._baro is not None:
            self._baro_reading = 101325.0

        if ctrl_mode == "Manual control":
            from ...utils.keyboard_cmd import keyboard_cmd
            self._rob_forceAPI = PhysxSchema.PhysxForceAPI.Apply(self._rob)
            if use_rov_physics:
                import carb
                carb.log_warn("[ROV PHYSICS] Physics model enabled (no PhysX mods)")
            self._force_cmd = keyboard_cmd(base_command=np.array([0.0, 0.0, 0.0]),
                                      input_keyboard_mapping={
                                        "W": [10.0, 0.0, 0.0], "S": [-10.0, 0.0, 0.0],
                                        "A": [0.0, 10.0, 0.0], "D": [0.0, -10.0, 0.0],
                                        "UP": [0.0, 0.0, 10.0], "DOWN": [0.0, 0.0, -10.0],
                                      })
            self._torque_cmd = keyboard_cmd(base_command=np.array([0.0, 0.0, 0.0]),
                                      input_keyboard_mapping={
                                        "J": [0.0, 0.0, 10.0], "L": [0.0, 0.0, -10.0],
                                        "I": [0.0, -10.0, 0.0], "K": [0.0, 10.0, 0.0],
                                        "LEFT": [-10.0, 0.0, 0.0], "RIGHT": [10.0, 0.0, 0.0],
                                      })
        self._running_scenario = True

    def setup_waypoints(self, waypoint_path, default_waypoint_path):
        def read_data_from_file(file_path):
            data = []
            with open(file_path, 'r') as file:
                for line in file:
                    float_strings = line.strip().split()
                    floats = [float(x) for x in float_strings]
                    data.append(floats)
            return data
        try:
            self.waypoints = read_data_from_file(waypoint_path)
            print('Waypoints loaded successfully.')
            print(f'Waypoint[0]: {self.waypoints[0]}')
        except:
            self.waypoints = read_data_from_file(default_waypoint_path)
            print('Fail to load this waypoints. Back to default waypoints.')

    def teardown_scenario(self):
        if self._sonar is not None:
            from isaacsim.oceansim.modules.sonar_web_dashboard.sonar_bridge import unregister_sonar
            unregister_sonar(self._sonar._name)
            self._sonar.close()
        if self._cam is not None:
            from isaacsim.oceansim.modules.sonar_web_dashboard.environment_bridge import unregister_camera
            unregister_camera(self._cam._name)
            self._cam.close()
        if self._ctrl_mode == "Manual control":
            self._force_cmd.cleanup()
            self._torque_cmd.cleanup()
        self._rob = None
        self._sonar = None
        self._cam = None
        self._DVL = None
        self._baro = None
        self._running_scenario = False
        self._time = 0.0

    def _apply_lighting(self, lighting):
        import warp as wp
        stage = get_current_stage()
        enabled = lighting.get("enabled", True)
        intensity = float(lighting["intensity"]) if enabled else 0.0
        color_temp = float(lighting["color_temperature"])
        elevation = float(lighting.get("elevation", 45.0))
        azimuth = float(lighting.get("azimuth", 0.0))

        light_prim = stage.GetPrimAtPath(self._env_light_path)
        if not light_prim.IsValid():
            light = UsdLux.DistantLight.Define(stage, self._env_light_path)
            light_prim = light.GetPrim()
            xformable = UsdGeom.Xformable(light_prim)
            xformable.AddXformOp(UsdGeom.XformOp.TypeRotateXYZ)
        else:
            light = UsdLux.DistantLight(light_prim)

        light.GetIntensityAttr().Set(intensity)
        light.GetEnableColorTemperatureAttr().Set(True)
        light.GetColorTemperatureAttr().Set(color_temp)
        light.GetAngleAttr().Set(1.0)

        xformable = UsdGeom.Xformable(light_prim)
        rot_ops = [op for op in xformable.GetOrderedXformOps() if op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ]
        if rot_ops:
            rot_ops[0].Set(Gf.Vec3f(-elevation, azimuth, 0.0))

        if self._cam is not None:
            from isaacsim.oceansim.modules.sonar_web_dashboard.environment_bridge import get_env_state
            water = get_env_state("water")
            light_scale = max(intensity / _REFERENCE_INTENSITY, 0.0) if enabled else 0.0
            self._cam._backscatter_value = wp.vec3f(
                float(water["backscatter_r"]) * light_scale,
                float(water["backscatter_g"]) * light_scale,
                float(water["backscatter_b"]) * light_scale,
            )

    def _process_spawn_queue(self):
        from isaacsim.oceansim.modules.sonar_web_dashboard.environment_bridge import (
            pop_spawn_queue, register_spawned_object,
        )
        for item in pop_spawn_queue():
            try:
                prim_name = item["prim_name"]
                prim_path = f"/World/spawned/{prim_name}"
                asset_path = item["asset_path"]
                pos = item["position"]
                rot = item["rotation"]
                scl = item["scale"]
                refl = item["reflectivity"]
                material = item.get("material", None)

                # If a material is specified and reflectivity was not explicitly overridden,
                # look up reflectivity from the acoustic materials table
                if material and refl == 1.0:
                    from isaacsim.oceansim.utils.acoustic_materials import get_reflectivity
                    refl = get_reflectivity(material)

                stage = get_current_stage()

                if asset_path in _BUILTIN_PRIMS:
                    # Create a built-in primitive shape (instant, no file loading)
                    prim = create_prim(
                        prim_path=prim_path,
                        prim_type=asset_path,
                        position=np.array(pos),
                        orientation=np.array([1.0, 0.0, 0.0, 0.0]),
                        scale=np.array(scl),
                    )
                    # Apply rotation via XformCommonAPI
                    xform = UsdGeom.XformCommonAPI(prim)
                    xform.SetRotate(Gf.Vec3f(rot[0], rot[1], rot[2]), UsdGeom.XformCommonAPI.RotationOrderXYZ)
                else:
                    # Load from USD file
                    prim = add_reference_to_stage(usd_path=asset_path, prim_path=prim_path)
                    xform = UsdGeom.XformCommonAPI(prim)
                    xform.SetTranslate(Gf.Vec3d(pos[0], pos[1], pos[2]))
                    xform.SetRotate(Gf.Vec3f(rot[0], rot[1], rot[2]), UsdGeom.XformCommonAPI.RotationOrderXYZ)
                    xform.SetScale(Gf.Vec3f(scl[0], scl[1], scl[2]))

                # Enable collision
                try:
                    SingleGeometryPrim(prim_path=prim_path, collision=True)
                except Exception:
                    pass

                # Apply sonar reflectivity
                prim_obj = stage.GetPrimAtPath(prim_path)
                add_update_semantics(prim=prim_obj, type_label='reflectivity', semantic_label=str(refl))
                for child in prim_obj.GetAllChildren():
                    if child.GetTypeName() == "Mesh":
                        add_update_semantics(prim=child, type_label='reflectivity', semantic_label=str(refl))

                register_spawned_object(prim_path, {
                    "asset_name": asset_path.split("/")[-1] if "/" in asset_path else asset_path,
                    "prim_name": prim_name,
                    "position": pos,
                    "rotation": rot,
                    "scale": scl,
                    "reflectivity": refl,
                    "material": material,
                })
                print(f'[Objects] Spawned {prim_name} ({asset_path}) at {pos}')
            except Exception as e:
                print(f'[Objects] Failed to spawn {item.get("prim_name", "?")}: {e}')

    def _process_delete_queue(self):
        from isaacsim.oceansim.modules.sonar_web_dashboard.environment_bridge import (
            pop_delete_queue, unregister_spawned_object,
        )
        for prim_path in pop_delete_queue():
            try:
                delete_prim(prim_path)
                unregister_spawned_object(prim_path)
                print(f'[Objects] Deleted {prim_path}')
            except Exception as e:
                print(f'[Objects] Failed to delete {prim_path}: {e}')

    def update_scenario(self, step: float):
        if not self._running_scenario:
            return

        self._time += step

        if self._sonar is not None:
            from isaacsim.oceansim.modules.sonar_web_dashboard.sonar_bridge import get_params
            self._sonar.make_sonar_data(**get_params(self._sonar._name))

        from isaacsim.oceansim.modules.sonar_web_dashboard.environment_bridge import get_dirty, get_env_state, clear_dirty

        if self._cam is not None:
            if get_dirty("water"):
                import warp as wp
                water = get_env_state("water")
                self._cam._backscatter_value = wp.vec3f(water["backscatter_r"], water["backscatter_g"], water["backscatter_b"])
                self._cam._backscatter_coeff = wp.vec3f(water["backscatter_coeff_r"], water["backscatter_coeff_g"], water["backscatter_coeff_b"])
                self._cam._atten_coeff = wp.vec3f(water["attenuation_coeff_r"], water["attenuation_coeff_g"], water["attenuation_coeff_b"])
                clear_dirty("water")
            self._cam.render()

        if self._sonar is not None and get_dirty("sonar_water"):
            from isaacsim.oceansim.modules.sonar_web_dashboard.sonar_bridge import set_params as sonar_set_params
            sonar_water = get_env_state("sonar_water")
            sonar_set_params(self._sonar._name, {
                "attenuation": sonar_water["acoustic_attenuation"],
                "gau_noise_param": sonar_water["gau_noise"],
                "ray_noise_param": sonar_water["ray_noise"],
            })
            clear_dirty("sonar_water")

        if get_dirty("lighting"):
            lighting = get_env_state("lighting")
            self._apply_lighting(lighting)
            clear_dirty("lighting")

        self._process_spawn_queue()
        self._process_delete_queue()

        if self._DVL is not None:
            self._DVL_reading = self._DVL.get_linear_vel()
        if self._baro is not None:
            self._baro_reading = self._baro.get_pressure()

        if self._ctrl_mode == "Manual control":
            # Get keyboard commands (same for both modes)
            fc = np.array(self._force_cmd._base_command, dtype=np.float64)
            tc = np.array(self._torque_cmd._base_command, dtype=np.float64)

            if self._use_rov_physics and self._rov_physics is not None:
                try:
                    # Get body velocity for drag computation
                    if not hasattr(self, '_rob_rigid_prim'):
                        self._rob_rigid_prim = SingleRigidPrim(prim_path=get_prim_path(self._rob))
                    lin_vel_world = np.array(self._rob_rigid_prim.get_linear_velocity())
                    ang_vel_world = np.array(self._rob_rigid_prim.get_angular_velocity())

                    # Get orientation for frame conversion
                    orient_attr = self._rob.GetAttribute('xformOp:orient')
                    quat = orient_attr.Get()
                    if quat is not None:
                        w_q = float(quat.GetReal())
                        im = quat.GetImaginary()
                        x_q, y_q, z_q = float(im[0]), float(im[1]), float(im[2])
                        R = np.array([
                            [1-2*(y_q*y_q+z_q*z_q), 2*(x_q*y_q-w_q*z_q),   2*(x_q*z_q+w_q*y_q)],
                            [2*(x_q*y_q+w_q*z_q),   1-2*(x_q*x_q+z_q*z_q), 2*(y_q*z_q-w_q*x_q)],
                            [2*(x_q*z_q-w_q*y_q),   2*(y_q*z_q+w_q*x_q),   1-2*(x_q*x_q+y_q*y_q)],
                        ])
                        body_lin = R.T @ lin_vel_world
                        body_ang = R.T @ ang_vel_world
                        cp = np.cos(np.arcsin(np.clip(-R[2, 0], -1, 1)))
                        pitch = np.arcsin(np.clip(-R[2, 0], -1, 1))
                        roll = np.arctan2(R[2, 1], R[2, 2]) if abs(cp) > 1e-6 else 0.0
                        yaw = np.arctan2(R[1, 0], R[0, 0]) if abs(cp) > 1e-6 else 0.0
                    else:
                        body_lin = lin_vel_world
                        body_ang = ang_vel_world
                        roll, pitch, yaw = 0.0, 0.0, 0.0

                    body_vel = [float(body_lin[0]), float(body_lin[1]), float(body_lin[2]),
                                float(body_ang[0]), float(body_ang[1]), float(body_ang[2])]

                    # Map keyboard to thruster commands [-1, 1]
                    max_cmd = 10.0
                    thruster_cmds = [
                        float(fc[0] / max_cmd), float(fc[1] / max_cmd), float(fc[2] / max_cmd),
                        float(tc[0] / max_cmd), float(tc[1] / max_cmd), float(tc[2] / max_cmd),
                    ]

                    # Compute hydro forces (body frame, Newtons)
                    force, torque = self._rov_physics.compute_forces(
                        body_vel, [roll, pitch, yaw], thruster_cmds, dt=step
                    )

                    # Convert to acceleration (PhysxForceAPI uses acceleration mode)
                    mass = self._rov_physics.mass
                    fc = force / mass
                    tc = torque / mass

                    # Clamp accelerations to prevent instability
                    max_accel = 20.0  # m/s^2 (about 2g)
                    fc = np.clip(fc, -max_accel, max_accel)
                    tc = np.clip(tc, -max_accel, max_accel)

                    if not hasattr(self, '_phys_frame_count'):
                        self._phys_frame_count = 0
                    self._phys_frame_count += 1
                    if self._phys_frame_count % 30 == 1:
                        import carb
                        carb.log_warn(f"[ROV PHYSICS] f={self._phys_frame_count} accel={[round(float(x),2) for x in fc]} vel={[round(float(x),2) for x in body_vel[:3]]} rpy={[round(float(x),2) for x in [roll,pitch,yaw]]}")
                except Exception as e:
                    import carb
                    carb.log_warn(f"[ROV PHYSICS] Error (using keyboard fallback): {e}")
                    import traceback
                    carb.log_warn(f"[ROV PHYSICS] {traceback.format_exc()}")
                    # fc and tc remain as keyboard values (fallback)

            # Apply via PhysxForceAPI (acceleration mode, local frame — proven working)
            self._rob_forceAPI.CreateForceAttr().Set(Gf.Vec3f(float(fc[0]), float(fc[1]), float(fc[2])))
            self._rob_forceAPI.CreateTorqueAttr().Set(Gf.Vec3f(float(tc[0]), float(tc[1]), float(tc[2])))
        elif self._ctrl_mode == "Waypoints":
            if len(self.waypoints) > 0:
                waypoints = self.waypoints[0]
                self._rob.GetAttribute('xformOp:translate').Set(Gf.Vec3f(waypoints[0], waypoints[1], waypoints[2]))
                self._rob.GetAttribute('xformOp:orient').Set(Gf.Quatd(waypoints[3], waypoints[4], waypoints[5], waypoints[6]))
                self.waypoints.pop(0)
            else:
                print('Waypoints finished')
        elif self._ctrl_mode == "Straight line":
            SingleRigidPrim(prim_path=get_prim_path(self._rob)).set_linear_velocity(np.array([0.5, 0, 0]))
