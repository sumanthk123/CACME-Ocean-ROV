"""ROV hydrodynamics model based on Fossen's 6-DOF equations.

Extracted and adapted from MarineGym (MIT license, github.com/Marine-RL/MarineGym).
Implements: buoyancy, added mass, Coriolis (added mass), linear + quadratic damping,
and T200 thruster model for BlueROV2 Heavy.

Coordinate convention: Isaac Sim uses a right-handed Y-up frame internally.
Fossen's equations use NED (North-East-Down) body frame. This module handles
the conversion at the boundaries (input velocities and output forces).
"""

import numpy as np


# ===== BlueROV2 Heavy default coefficients (from MarineGym / UUV Simulator) =====

BLUEROV2_HEAVY_PARAMS = {
    "mass": 11.5,           # kg (dry mass)
    "volume": 0.0113459,    # m^3 (displaced water volume, slightly positive buoyancy)
    "water_density": 997.0, # kg/m^3 (freshwater; use 1025 for seawater)
    "gravity": 9.81,        # m/s^2
    "cob_offset": 0.01,     # m (center of buoyancy above center of gravity)

    # Added mass coefficients [surge, sway, heave, roll, pitch, yaw]
    "added_mass": [5.5, 12.7, 14.57, 0.12, 0.12, 0.12],

    # Linear damping coefficients [surge, sway, heave, roll, pitch, yaw]
    "linear_damping": [4.03, 6.22, 5.18, 0.07, 0.07, 0.07],

    # Quadratic damping coefficients [surge, sway, heave, roll, pitch, yaw]
    "quadratic_damping": [18.18, 21.66, 36.99, 1.55, 1.55, 1.55],
}


# ===== T200 Thruster model =====
# BlueROV2 Heavy: 8 thrusters
# 4 horizontal (vectored at 45 deg for surge/sway/yaw)
# 4 vertical (for heave/roll/pitch)

_cos45 = np.cos(np.radians(45))
BLUEROV2_HEAVY_ALLOCATION = np.array([
    # Horizontal thrusters (contribute to surge, sway, yaw)
    [ _cos45, -_cos45, 0, 0, 0,  1],  # front-right
    [ _cos45,  _cos45, 0, 0, 0, -1],  # front-left
    [-_cos45, -_cos45, 0, 0, 0, -1],  # rear-right
    [-_cos45,  _cos45, 0, 0, 0,  1],  # rear-left
    # Vertical thrusters (contribute to heave, roll, pitch)
    [0, 0, 1,  1,  1, 0],  # front-right vertical
    [0, 0, 1, -1,  1, 0],  # front-left vertical
    [0, 0, 1,  1, -1, 0],  # rear-right vertical
    [0, 0, 1, -1, -1, 0],  # rear-left vertical
])

# T200 thruster: max thrust ~5.25 kgf forward, ~4.1 kgf reverse
T200_MAX_THRUST_FWD = 5.25 * 9.81  # N
T200_MAX_THRUST_REV = 4.1 * 9.81   # N
T200_TAU = 0.1  # first-order lag time constant (seconds)


def t200_thrust(command, dt=None, prev_thrust=None):
    """Convert a [-1, 1] command to thrust in Newtons for a T200 thruster."""
    command = np.clip(command, -1.0, 1.0)
    if command >= 0:
        target = command * T200_MAX_THRUST_FWD
    else:
        target = command * T200_MAX_THRUST_REV

    if dt is not None and prev_thrust is not None:
        alpha = dt / (T200_TAU + dt)
        return prev_thrust + alpha * (target - prev_thrust)
    return target


class ROVPhysicsModel:
    """6-DOF hydrodynamics model for an underwater ROV.

    Call compute_forces() each physics step with the current body-frame velocities,
    orientation, and thruster commands. Apply the returned forces/torques via PhysxForceAPI.
    """

    def __init__(self, params=None):
        p = params or BLUEROV2_HEAVY_PARAMS
        self.mass = p["mass"]
        self.volume = p["volume"]
        self.rho = p["water_density"]
        self.g = p["gravity"]
        self.cob_offset = p["cob_offset"]
        self.M_A = np.array(p["added_mass"], dtype=np.float64)
        self.D_l = np.array(p["linear_damping"], dtype=np.float64)
        self.D_q = np.array(p["quadratic_damping"], dtype=np.float64)

        self._prev_vel = np.zeros(6)
        self._prev_thrust = np.zeros(8)
        self._alpha_acc = 0.3  # acceleration smoothing factor

    def compute_forces(self, body_vel, orientation_rpy, thruster_cmds=None, dt=0.016):
        """Compute all hydrodynamic forces and torques in the body frame.

        Args:
            body_vel: [vx, vy, vz, wx, wy, wz] body-frame linear + angular velocity
                      (Isaac Sim convention: X-forward, Y-up, Z-right)
            orientation_rpy: [roll, pitch, yaw] in radians
            thruster_cmds: array of 6 floats [surge, sway, heave, roll, pitch, yaw] in [-1, 1]
                           mapped through allocation matrix to 8 thrusters.
                           Or 8 floats for direct per-thruster control.
                           None = no thruster forces.
            dt: physics timestep in seconds

        Returns:
            (force_xyz, torque_xyz) each as numpy arrays of 3 floats, in Isaac Sim body frame
        """
        vel = np.array(body_vel, dtype=np.float64)

        # Convert Isaac Sim (X-fwd, Y-up, Z-right) to Fossen NED (X-fwd, Y-right, Z-down)
        vel_ned = vel.copy()
        vel_ned[1], vel_ned[2] = vel[2], -vel[1]
        vel_ned[4], vel_ned[5] = vel[5], -vel[4]

        roll, pitch, yaw = orientation_rpy

        # Compute hydrodynamic forces in NED body frame
        f_buoy = self._buoyancy(roll, pitch)
        f_damping = self._damping(vel_ned)
        f_added_mass = self._added_mass(vel_ned, dt)
        f_coriolis = self._coriolis(vel_ned)

        hydro = f_buoy + f_damping + f_added_mass + f_coriolis

        # Convert NED back to Isaac Sim frame
        hydro[1], hydro[2] = -hydro[2], hydro[1]
        hydro[4], hydro[5] = -hydro[5], hydro[4]

        # Thruster forces
        thrust_force = np.zeros(6)
        if thruster_cmds is not None:
            cmds = np.array(thruster_cmds, dtype=np.float64)
            if len(cmds) == 6:
                # A^T maps 8 thrusters -> 6 DOF forces, so pinv(A^T) maps 6 DOF -> 8 thrusters
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
        """Restoring forces from buoyancy vs gravity."""
        W = self.mass * self.g
        B = self.rho * self.g * self.volume
        d = self.cob_offset

        f = np.zeros(6)
        f[0] = (W - B) * np.sin(pitch)
        f[1] = -(W - B) * np.cos(pitch) * np.sin(roll)
        f[2] = -(W - B) * np.cos(pitch) * np.cos(roll)
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
        acc = self._alpha_acc * acc  # smoothed
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
        """Reset internal state (call when resetting the simulation)."""
        self._prev_vel = np.zeros(6)
        self._prev_thrust = np.zeros(8)
