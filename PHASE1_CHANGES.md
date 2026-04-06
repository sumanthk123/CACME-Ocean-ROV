# Phase 1: Water-Condition-Linked Sonar + Material Reflectivity

## Overview
Phase 1 links sonar behavior to water conditions (previously only camera was affected), adds material-based acoustic reflectivity, and fixes the sonar noise model.

## Changes

### 1C. Multiplicative Speckle Noise Fix (COMPLETE)

**File:** `isaacsim/oceansim/utils/ImagingSonar_kernels.py`

**What changed:**
- `make_sonar_map_all` kernel (line 154): Changed `intensity *= (0.5 + gau_noise)` to `intensity *= (1.0 + gau_noise)`
- `make_sonar_map_range` kernel (line 177): Same change

**Why:**
The original `0.5` bias meant the multiplicative noise factor was centered at 0.5, effectively halving the signal and making the noise partially additive. Real sonar multiplicative speckle should be centered at 1.0 — the signal is unchanged on average, but fluctuates proportionally to intensity. Bright returns now get proportionally larger speckle (matching real sonar), dim returns get proportionally smaller speckle.

---

### 1A. Water Condition Presets (COMPLETE)

**Files modified:**
- `modules/sonar_web_dashboard/environment_bridge.py` — Added `sonar_water` state category with `acoustic_attenuation`, `gau_noise`, `ray_noise`
- `modules/sonar_web_dashboard/models.py` — Added `SonarWaterParams` model + `WATER_CONDITION_PRESETS` dict with 4 presets:
  - **Clear Ocean**: attenuation=0.2, gau_noise=0.05, ray_noise=0.02
  - **Coastal**: attenuation=0.4, gau_noise=0.15, ray_noise=0.08
  - **Murky Harbor**: attenuation=0.7, gau_noise=0.40, ray_noise=0.20
  - **Turbid River**: attenuation=0.85, gau_noise=0.60, ray_noise=0.30
- `modules/sonar_web_dashboard/api.py` — Added endpoints:
  - `GET/PUT /api/environment/sonar_water`
  - `GET /api/environment/water_presets`
  - `PUT /api/environment/water_preset/{name}` (sets both camera + sonar in one call)
- `modules/SensorExample_python/scenario.py` — Added `sonar_water` dirty check in `update_scenario` to push acoustic params to sonar bridge
- `modules/sonar_web_dashboard/web/app.js` + `index.html` — Added preset buttons + acoustic parameter sliders in Environment tab

**Why:**
Previously, water condition parameters only affected the underwater camera rendering. The sonar was completely decoupled. Now, switching a water preset changes both the camera visuals and the sonar noise/attenuation behavior simultaneously.

---

### 1B. Material-Dependent Acoustic Reflectivity (COMPLETE)

**New file:** `isaacsim/oceansim/utils/acoustic_materials.py`
- Lookup table mapping material names to acoustic reflection coefficients derived from impedance mismatch with seawater (Z_water ~ 1.54 MRayl):
  - steel=0.93, aluminum=0.84, concrete=0.66, rock=0.81, sand=0.39, mud=0.19, wood=0.15, rubber=0.04
- Helper functions: `get_reflectivity(name)`, `list_materials()`

**Files modified:**
- `modules/sonar_web_dashboard/environment_bridge.py` — Added `material` param to `queue_spawn()`
- `modules/sonar_web_dashboard/api.py` — Added `material` field to spawn endpoint + `GET /api/materials` endpoint
- `modules/SensorExample_python/scenario.py` — Spawn processing auto-lookups reflectivity from material name
- `modules/sonar_web_dashboard/web/app.js` + `index.html` — Added Material dropdown in Objects tab that auto-fills reflectivity

**Why:**
Users previously had to manually guess reflectivity values. Now they select a material (steel, concrete, rock, etc.) and get physically-grounded acoustic reflectivity values automatically. The values are derived from the acoustic impedance formula: R = (Z_material - Z_water) / (Z_material + Z_water).
