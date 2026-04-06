"""Global environment registry for bridging OceanSim environment controls to the web API."""

import os

_env_state = {
    "water": {
        "backscatter_r": 0.0, "backscatter_g": 0.31, "backscatter_b": 0.24,
        "backscatter_coeff_r": 0.05, "backscatter_coeff_g": 0.05, "backscatter_coeff_b": 0.2,
        "attenuation_coeff_r": 0.05, "attenuation_coeff_g": 0.05, "attenuation_coeff_b": 0.05,
    },
    "sonar_water": {
        "acoustic_attenuation": 0.2,
        "gau_noise": 0.05,
        "ray_noise": 0.02,
    },
    "lighting": {
        "intensity": 50000.0,
        "color_temperature": 6500.0,
        "elevation": 45.0,
        "azimuth": 0.0,
        "enabled": True,
    },
}

_dirty_flags = {
    "water": False,
    "sonar_water": False,
    "lighting": False,
}

_registered_cameras = {}

# Object spawning queue (thread-safe: written by API thread, read by physics thread)
_spawn_queue = []      # list of dicts: {asset_path, prim_name, position, rotation, scale, reflectivity}
_delete_queue = []     # list of prim_path strings
_spawned_objects = {}  # prim_path -> {asset_name, position, rotation, scale, reflectivity}


def get_env_state(category=None):
    if category is None:
        return dict(_env_state)
    return dict(_env_state.get(category, {}))


def set_env_state(category, params):
    if category in _env_state:
        _env_state[category].update(params)
        _dirty_flags[category] = True


def get_dirty(category):
    return _dirty_flags.get(category, False)


def clear_dirty(category):
    _dirty_flags[category] = False


def register_camera(name, cam):
    _registered_cameras[name] = cam


def unregister_camera(name):
    _registered_cameras.pop(name, None)


def get_camera(name):
    return _registered_cameras.get(name)


def list_cameras():
    return list(_registered_cameras.keys())


# ===== Object management =====

def queue_spawn(asset_path, prim_name, position, rotation, scale, reflectivity, material=None):
    _spawn_queue.append({
        "asset_path": asset_path,
        "prim_name": prim_name,
        "position": position,
        "rotation": rotation,
        "scale": scale,
        "reflectivity": reflectivity,
        "material": material,
    })


def queue_delete(prim_path):
    _delete_queue.append(prim_path)


def pop_spawn_queue():
    items = list(_spawn_queue)
    _spawn_queue.clear()
    return items


def pop_delete_queue():
    items = list(_delete_queue)
    _delete_queue.clear()
    return items


def register_spawned_object(prim_path, info):
    _spawned_objects[prim_path] = info


def unregister_spawned_object(prim_path):
    _spawned_objects.pop(prim_path, None)


def list_spawned_objects():
    return dict(_spawned_objects)


def scan_assets(assets_root):
    """Scan asset directory for USD files and return a catalog."""
    catalog = []
    if not os.path.isdir(assets_root):
        return catalog
    for root, dirs, files in os.walk(assets_root):
        for f in files:
            if f.endswith(('.usd', '.usda', '.usdc')):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, assets_root)
                name = os.path.splitext(f)[0]
                catalog.append({
                    "name": name,
                    "file": f,
                    "rel_path": rel_path,
                    "full_path": full_path,
                })
    return catalog
