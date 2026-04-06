"""Headless test for OceanSim - verifies physics, materials, bridges."""

import sys
import os

# Add OceanSim to path
sys.path.insert(0, '/home/Talik/isaacsim/extsUser/OceanSim')

# Isaac Sim standalone startup
from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": True})

# Now we can import everything
import numpy as np
import carb

print("=" * 60)
print("OceanSim Headless Test")
print("=" * 60)

passed = 0
failed = 0

# ===== Test 1: ROV Physics Module =====
print("\n[TEST 1] ROV Physics Module")
try:
    from isaacsim.oceansim.utils.rov_physics import ROVPhysicsModel
    model = ROVPhysicsModel()

    f, t = model.compute_forces([0,0,0,0,0,0], [0,0,0])
    assert f[1] > 0, f"Expected positive Y force (buoyancy), got {f[1]}"
    print(f"  At rest: force={f.round(3)} - buoyancy OK ({f[1]:.3f}N up)")

    model.reset()
    f, t = model.compute_forces([1.0,0,0,0,0,0], [0,0,0])
    assert f[0] < 0, f"Expected negative X force (drag), got {f[0]}"
    print(f"  Moving fwd 1m/s: force={f.round(3)} - drag OK ({f[0]:.3f}N)")

    model.reset()
    f, t = model.compute_forces([0,0,0,0,0,0], [0,0,0], thruster_cmds=[1,0,0,0,0,0])
    assert f[0] > 0, f"Expected positive X force (thrust), got {f[0]}"
    print(f"  Full surge thrust: force={f.round(3)} - thrust OK ({f[0]:.3f}N)")

    model.reset()
    f, t = model.compute_forces([0,0,0,0,0,0], [0.3,0,0])
    assert t[0] < 0, f"Expected negative roll torque (restoring), got {t[0]}"
    print(f"  Rolled 17deg: torque={t.round(3)} - restoring OK ({t[0]:.3f}Nm)")

    print("  [PASS]")
    passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    failed += 1

# ===== Test 2: Acoustic Materials =====
print("\n[TEST 2] Acoustic Materials")
try:
    from isaacsim.oceansim.utils.acoustic_materials import get_reflectivity, list_materials

    assert get_reflectivity("steel") == 0.93
    assert get_reflectivity("mud") == 0.19
    assert get_reflectivity("STEEL") == 0.93, "Case insensitive failed"
    assert get_reflectivity("unknown") == 1.0, "Default fallback failed"
    assert len(list_materials()) >= 8

    print(f"  Materials: {list_materials()}")
    print("  [PASS]")
    passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    failed += 1

# ===== Test 3: Sonar Bridge (merge) =====
print("\n[TEST 3] Sonar Bridge")
try:
    from isaacsim.oceansim.modules.sonar_web_dashboard.sonar_bridge import (
        register_sonar, set_params, get_params, list_sonars, unregister_sonar
    )

    register_sonar("test_sonar", None)
    assert get_params("test_sonar") == {}

    set_params("test_sonar", {"attenuation": 0.5})
    set_params("test_sonar", {"gau_noise_param": 0.3})
    p = get_params("test_sonar")
    assert p["attenuation"] == 0.5, f"Merge lost attenuation: {p}"
    assert p["gau_noise_param"] == 0.3, f"Merge lost noise: {p}"

    unregister_sonar("test_sonar")
    print("  set_params merges correctly (not replaces)")
    print("  [PASS]")
    passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    failed += 1

# ===== Test 4: Environment Bridge =====
print("\n[TEST 4] Environment Bridge")
try:
    from isaacsim.oceansim.modules.sonar_web_dashboard.environment_bridge import (
        get_env_state, set_env_state, get_dirty, clear_dirty
    )

    sw = get_env_state("sonar_water")
    assert "acoustic_attenuation" in sw
    assert "gau_noise" in sw
    assert "ray_noise" in sw

    set_env_state("sonar_water", {"acoustic_attenuation": 0.7})
    assert get_dirty("sonar_water")
    assert get_env_state("sonar_water")["acoustic_attenuation"] == 0.7
    clear_dirty("sonar_water")
    assert not get_dirty("sonar_water")

    print(f"  sonar_water state works correctly")
    print("  [PASS]")
    passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    failed += 1

# ===== Test 5: Water Condition Presets =====
print("\n[TEST 5] Water Condition Presets")
try:
    from isaacsim.oceansim.modules.sonar_web_dashboard.models import WATER_CONDITION_PRESETS

    for name in ["clear_ocean", "murky_harbor", "coastal", "turbid_river"]:
        assert name in WATER_CONDITION_PRESETS, f"Missing preset: {name}"
        preset = WATER_CONDITION_PRESETS[name]
        assert "sonar" in preset and "water" in preset
        print(f"  {name}: attenuation={preset['sonar']['acoustic_attenuation']}")

    print("  [PASS]")
    passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    failed += 1

# ===== Test 6: Noise kernel fix verification =====
print("\n[TEST 6] Sonar Noise Kernel Fix")
try:
    with open('/home/Talik/isaacsim/extsUser/OceanSim/isaacsim/oceansim/utils/ImagingSonar_kernels.py') as f:
        src = f.read()
    assert "(0.5 + gau_noise" not in src, "Old 0.5 bias still present!"
    assert "(1.0 + gau_noise" in src, "1.0 fix not found"
    print("  Noise multiplier correctly set to 1.0")
    print("  [PASS]")
    passed += 1
except Exception as e:
    print(f"  [FAIL] {e}")
    failed += 1

print("\n" + "=" * 60)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 60)

simulation_app.close()
sys.exit(0 if failed == 0 else 1)
