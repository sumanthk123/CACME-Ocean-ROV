"""ROV hydrodynamics model based on Fossen's 6-DOF equations.

Extracted and adapted from MarineGym (MIT license, github.com/Marine-RL/MarineGym).
Implements: buoyancy, added mass, Coriolis (added mass), linear + quadratic damping,
and T200 thruster model for BlueROV2 Heavy.

Coordinate convention: Isaac Sim uses a right-handed Y-up frame internally.
Fossen's equations use NED (North-East-Down) body frame. This module handles
the conversion at the boundaries (input velocities and output forces).

Design: Mass and volume are read from the USD prim at setup time, so the physics
is accurate for any ROV model without manual coefficient tuning. Drag and added mass
coefficients default to BlueROV2 Heavy values but can be overridden.
"""

import numpy as np


# ===== BlueROV2 Heavy default hydrodynamic coefficients =====
# These are shape-dependent and come from published experimental data.
# For a new vehicle, these should be re-identified or estimated from geometry.

BLUEROV2_HEAVY_HYDRO = {
    "cob_offset": 0.01,     # m (center of buoyancy above center of gravity)
    "water_density": 997.0, # kg/m^3 (freshwater; use 1025 for seawater)

    # Added mass coefficients [surge, sway, heave, roll, pitch, yaw]
    "added_mass": [5.5, 12.7, 14.57, 0.12, 0.12, 0.12],

    # Linear damping coefficients [surge, sway, heave, roll, pitch, yaw]
    "linear_damping": [4.03, 6.22, 5.18, 0.07, 0.07, 0.07],

    # Quadratic damping coefficients [surge, sway, heave, roll, pitch, yaw]
    "quadratic_damping": [18.18, 21.66, 36.99, 1.55, 1.55, 1.55],
}


# ===== T200 Thruster model =====

_cos45 = np.cos(np.radians(45))
BLUEROV2_HEAVY_ALLOCATION = np.array([
    [ _cos45, -_cos45, 0, 0, 0,  1],  # front-right horizontal
    [ _cos45,  _cos45, 0, 0, 0, -1],  # front-left horizontal
    [-_cos45, -_cos45, 0, 0, 0, -1],  # rear-right horizontal
    [-_cos45,  _cos45, 0, 0, 0,  1],  # rear-left horizontal
    [0, 0, 1,  1,  1, 0],  # front-right vertical
    [0, 0, 1, -1,  1, 0],  # front-left vertical
    [0, 0, 1,  1, -1, 0],  # rear-right vertical
    [0, 0, 1, -1, -1, 0],  # rear-left vertical
])

T200_MAX_THRUST_FWD = 5.25 * 9.81  # N (~51.5N)
T200_MAX_THRUST_REV = 4.1 * 9.81   # N (~40.2N)
T200_TAU = 0.1  # first-order lag time constant (seconds)


def t200_thrust(command, dt=None, prev_thrust=None):
    """Convert a [-1, 1] command to thrust in Newtons for a T200 thruster."""
    command = np.clip(command, -1.0, 1.0)
    target = command * (T200_MAX_THRUST_FWD if command >= 0 else T200_MAX_THRUST_REV)
    if dt is not None and prev_thrust is not None:
        alpha = dt / (T200_TAU + dt)
        return prev_thrust + alpha * (target - prev_thrust)
    return target


def estimate_hydro_coefficients_from_bbox(bbox_size):
    """Estimate drag and added mass coefficients from bounding box dimensions.

    Uses empirical correlations for bluff bodies. This gives reasonable defaults
    for any vehicle shape — not as accurate as CFD or tank tests, but avoids
    the need for manual coefficient entry.

    Args:
        bbox_size: [length_x, height_y, width_z] in meters

    Returns:
        dict with estimated added_mass, linear_damping, quadratic_damping
    """
    lx, ly, lz = bbox_size
    rho = 997.0  # water density

    # Cross-sectional areas for each DOF
    A_surge = ly * lz      # frontal area (sway x heave)
    A_sway = lx * ly       # side area (surge x heave)
    A_heave = lx * lz      # top area (surge x sway)

    # Added mass ~ C_a * rho * characteristic_volume
    # For a rectangular body, C_a ~ 0.5-1.0
    C_a = 0.7
    am_surge = C_a * rho * A_surge * lx
    am_sway = C_a * rho * A_sway * lz
    am_heave = C_a * rho * A_heave * ly
    # Rotational added mass (rough estimate)
    am_rot = 0.1 * C_a * rho * lx * ly * lz

    # Quadratic drag: F = 0.5 * rho * Cd * A * |v| * v
    # Cd ~ 1.0-1.2 for bluff bodies
    Cd = 1.1
    dq_surge = 0.5 * rho * Cd * A_surge
    dq_sway = 0.5 * rho * Cd * A_sway
    dq_heave = 0.5 * rho * Cd * A_heave
    dq_rot = 0.5 * rho * Cd * max(A_surge, A_sway) * 0.1

    # Linear drag (skin friction, much smaller than quadratic for ROVs)
    dl_factor = 0.1  # linear drag ~ 10% of quadratic at 1 m/s
    dl_surge = dq_surge * dl_factor
    dl_sway = dq_sway * dl_factor
    dl_heave = dq_heave * dl_factor
    dl_rot = dq_rot * dl_factor

    return {
        "added_mass": [am_surge, am_sway, am_heave, am_rot, am_rot, am_rot],
        "linear_damping": [dl_surge, dl_sway, dl_heave, dl_rot, dl_rot, dl_rot],
        "quadratic_damping": [dq_surge, dq_sway, dq_heave, dq_rot, dq_rot, dq_rot],
    }


def compute_mesh_volume_from_prim(prim):
    """Compute the volume of a USD mesh prim for buoyancy calculation.

    Falls back to bounding box volume if mesh volume computation fails.
    Must be called within Isaac Sim runtime (needs USD/PhysX).

    Returns:
        (volume_m3, bbox_size, mass) tuple
    """
    from pxr import UsdGeom, UsdPhysics, Gf
    import carb

    mass = 10.0  # default
    bbox_size = [0.5, 0.3, 0.4]  # default BlueROV2-ish

    # Try to get mass from physics mass API
    mass_api = UsdPhysics.MassAPI(prim)
    if mass_api:
        mass_attr = mass_api.GetMassAttr()
        if mass_attr and mass_attr.HasValue():
            mass = mass_attr.Get()
            carb.log_info(f"[ROV PHYSICS] Read mass from prim: {mass} kg")

    # Compute bounding box
    bbox_cache = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_])
    bbox = bbox_cache.ComputeWorldBound(prim)
    bbox_range = bbox.ComputeAlignedRange()
    if not bbox_range.IsEmpty():
        min_pt = bbox_range.GetMin()
        max_pt = bbox_range.GetMax()
        bbox_size = [
            max_pt[0] - min_pt[0],
            max_pt[1] - min_pt[1],
            max_pt[2] - min_pt[2],
        ]
        carb.log_info(f"[ROV PHYSICS] Bounding box: {[round(x,3) for x in bbox_size]} m")

    # Volume estimate from bounding box
    # ROV frames are mostly open (thrusters, electronics tubes, empty space)
    # Typical fill factor is 15-25% for frame-style ROVs like BlueROV2
    # We target slightly positive buoyancy: volume = mass/rho + small excess
    bbox_volume = bbox_size[0] * bbox_size[1] * bbox_size[2]
    # Use mass-based estimate if mass is known (slightly positive buoyancy)
    volume_for_neutral = mass / rho
    volume = volume_for_neutral * 1.02  # 2% positive buoyancy

    carb.log_info(f"[ROV PHYSICS] Estimated volume: {volume:.6f} m^3, mass: {mass} kg")

    return volume, bbox_size, mass


class ROVPhysicsModel:
    """6-DOF hydrodynamics model for an underwater ROV.

    Can be initialized two ways:
    1. From a USD prim (auto-computes mass, volume, and estimates coefficients)
    2. From explicit parameters (for known vehicles like BlueROV2)
    """

    def __init__(self, params=None, prim=None):
        """Initialize the physics model.

        Args:
            params: dict of hydro coefficients. If None, uses BlueROV2 Heavy defaults.
            prim: USD prim to read mass/volume from. If provided, mass and volume
                  are computed from the mesh, and drag coefficients are estimated
                  from the bounding box. Explicit params override auto-computed values.
        """
        hydro = dict(BLUEROV2_HEAVY_HYDRO)
        self.mass = 11.5
        self.volume = 0.011735
        self.g = 9.81

        if prim is not None:
            # Auto-compute from mesh
            try:
                vol, bbox, mass = compute_mesh_volume_from_prim(prim)
                self.mass = mass
                self.volume = vol
                # Estimate hydro coefficients from bounding box
                estimated = estimate_hydro_coefficients_from_bbox(bbox)
                hydro.update(estimated)
                import carb
                carb.log_warn(f"[ROV PHYSICS] Auto-configured: mass={mass:.2f}kg, volume={vol:.6f}m^3, bbox={[round(x,3) for x in bbox]}")
            except Exception as e:
                import carb
                carb.log_warn(f"[ROV PHYSICS] Auto-config failed, using defaults: {e}")

        # Explicit params override auto-computed
        if params:
            if "mass" in params:
                self.mass = params["mass"]
            if "volume" in params:
                self.volume = params["volume"]
            hydro.update(params)

        self.rho = hydro.get("water_density", 997.0)
        self.cob_offset = hydro.get("cob_offset", 0.01)
        self.M_A = np.array(hydro["added_mass"], dtype=np.float64)
        self.D_l = np.array(hydro["linear_damping"], dtype=np.float64)
        self.D_q = np.array(hydro["quadratic_damping"], dtype=np.float64)

        self._prev_vel = np.zeros(6)
        self._prev_thrust = np.zeros(8)
        self._alpha_acc = 0.3

    def compute_forces(self, body_vel, orientation_rpy, thruster_cmds=None, dt=0.016):
        """Compute all hydrodynamic forces and torques in the body frame.

        Args:
            body_vel: [vx, vy, vz, wx, wy, wz] body-frame velocity (Isaac Sim frame)
            orientation_rpy: [roll, pitch, yaw] in radians
            thruster_cmds: 6 floats [surge,sway,heave,roll,pitch,yaw] in [-1,1]
                           or 8 floats for direct per-thruster control. None = no thrust.
            dt: physics timestep in seconds

        Returns:
            (force_xyz, torque_xyz) in Isaac Sim body frame
        """
        vel = np.array(body_vel, dtype=np.float64)

        # Isaac Sim (X-fwd, Y-up, Z-right) -> Fossen NED (X-fwd, Y-right, Z-down)
        vel_ned = vel.copy()
        vel_ned[1], vel_ned[2] = vel[2], -vel[1]
        vel_ned[4], vel_ned[5] = vel[5], -vel[4]

        roll, pitch, yaw = orientation_rpy

        f_buoy = self._buoyancy(roll, pitch)
        f_damping = self._damping(vel_ned)
        f_added_mass = self._added_mass(vel_ned, dt)
        f_coriolis = self._coriolis(vel_ned)

        hydro = f_buoy + f_damping + f_added_mass + f_coriolis

        # NED -> Isaac Sim frame
        hydro[1], hydro[2] = -hydro[2], hydro[1]
        hydro[4], hydro[5] = -hydro[5], hydro[4]

        # Thruster forces
        thrust_force = np.zeros(6)
        if thruster_cmds is not None:
            cmds = np.array(thruster_cmds, dtype=np.float64)
            if len(cmds) == 6:
                alloc_pinv = np.linalg.pinv(BLUEROV2_HEAVY_ALLOCATION.T)
                per_thruster = np.clip(alloc_pinv @ cmds, -1.0, 1.0)
            elif len(cmds) == 8:
                per_thruster = cmds
            else:
                per_thruster = np.zeros(8)

            thrusts = np.zeros(8)
            for i in range(8):
                thrusts[i] = t200_thrust(per_thruster[i], dt, self._prev_thrust[i])
            self._prev_thrust = thrusts
            thrust_force = BLUEROV2_HEAVY_ALLOCATION.T @ thrusts

        total_force = hydro[:3] + thrust_force[:3]
        total_torque = hydro[3:] + thrust_force[3:]

        return total_force, total_torque

    def _buoyancy(self, roll, pitch):
        """Full buoyancy force to counteract PhysX gravity + restoring moments.

        PhysX applies gravity (W = mg), so we apply the FULL buoyancy force
        (B = rho*g*V) upward. The net effect is B - W, which should be slightly
        positive for a properly trimmed ROV. Restoring moments come from the
        center-of-buoyancy offset above center-of-gravity.
        """
        B = self.rho * self.g * self.volume
        d = self.cob_offset

        f = np.zeros(6)
        # Full buoyancy (upward in NED = negative Z)
        f[0] = -B * np.sin(pitch)
        f[1] = B * np.cos(pitch) * np.sin(roll)
        f[2] = B * np.cos(pitch) * np.cos(roll)
        # Restoring torques
        f[3] = -d * B * np.cos(pitch) * np.sin(roll)
        f[4] = -d * B * np.sin(pitch)
        f[5] = 0.0
        return f

    def _damping(self, vel_ned):
        """Linear + quadratic drag in body frame."""
        f = np.zeros(6)
        for i in range(6):
            f[i] = -(self.D_l[i] * vel_ned[i] + self.D_q[i] * abs(vel_ned[i]) * vel_ned[i])
        return f

    def _added_mass(self, vel_ned, dt):
        """Added mass force: -M_A * acceleration."""
        acc = (vel_ned - self._prev_vel) / max(dt, 1e-6)
        acc = self._alpha_acc * acc
        self._prev_vel = vel_ned.copy()
        f = np.zeros(6)
        for i in range(6):
            f[i] = -self.M_A[i] * acc[i]
        return f

    def _coriolis(self, vel_ned):
        """Coriolis force from added mass (rigid-body Coriolis handled by PhysX)."""
        v = vel_ned[:3]
        w = vel_ned[3:]
        ma_v = self.M_A[:3] * v
        ma_w = self.M_A[3:] * w

        f = np.zeros(6)
        f[0] = -(ma_v[1] * w[2] - ma_v[2] * w[1])
        f[1] = -(ma_v[2] * w[0] - ma_v[0] * w[2])
        f[2] = -(ma_v[0] * w[1] - ma_v[1] * w[0])
        f[3] = -(ma_v[1] * v[2] - ma_v[2] * v[1]) - (ma_w[1] * w[2] - ma_w[2] * w[1])
        f[4] = -(ma_v[2] * v[0] - ma_v[0] * v[2]) - (ma_w[2] * w[0] - ma_w[0] * w[2])
        f[5] = -(ma_v[0] * v[1] - ma_v[1] * v[0]) - (ma_w[0] * w[1] - ma_w[1] * w[0])
        return f

    def reset(self):
        """Reset internal state."""
        self._prev_vel = np.zeros(6)
        self._prev_thrust = np.zeros(8)
