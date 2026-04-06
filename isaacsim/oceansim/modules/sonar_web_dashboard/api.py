"""REST API and WebSocket endpoints for the sonar web dashboard."""

import asyncio
import io

import numpy as np
from PIL import Image

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import Response, JSONResponse

from omni.services.core import routers

from .sonar_bridge import get_sonar, list_sonars, get_params, set_params
from .environment_bridge import (
    get_env_state, set_env_state, get_camera, list_cameras,
    queue_spawn, queue_delete, list_spawned_objects, scan_assets,
)
from .models import (
    SonarParams, SonarInfo, SonarListResponse, UpdateParamsResponse,
    WaterParams, LightingParams, SonarWaterParams, EnvironmentUpdateResponse,
    WATER_CONDITION_PRESETS,
)

router = routers.ServiceAPIRouter()


def _sonar_to_jpeg(sonar, quality=50):
    img_np = sonar.sonar_image.numpy()
    pil_img = Image.fromarray(img_np[:, :, :3])
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _camera_to_jpeg(cam, quality=70):
    if not hasattr(cam, 'uw_image') or cam.uw_image is None:
        return None
    img_np = cam.uw_image.numpy()
    pil_img = Image.fromarray(img_np[:, :, :3])
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ===== Sonar endpoints =====

@router.get("/api/sonar/list", summary="List all registered sonar sensors.", response_model=SonarListResponse)
def get_sonar_list() -> SonarListResponse:
    sonars = []
    for name in list_sonars():
        s = get_sonar(name)
        if s is not None:
            sonars.append(SonarInfo(
                name=name, min_range=s.min_range, max_range=s.max_range,
                range_res=s.range_res, hori_fov=s.hori_fov, vert_fov=s.vert_fov,
                angular_res=s.angular_res, hori_res=s.hori_res,
                sonar_map_shape=list(s.sonar_map.shape),
            ))
    return SonarListResponse(sonars=sonars)


@router.get("/api/sonar/{name}/params", summary="Get current sonar processing parameters.", response_model=SonarParams)
def get_sonar_params(name: str):
    sonar = get_sonar(name)
    if sonar is None:
        return JSONResponse(status_code=404, content={"error": f"Sonar '{name}' not found"})
    return SonarParams(**get_params(name))


@router.put("/api/sonar/{name}/params", summary="Update sonar processing parameters.", response_model=UpdateParamsResponse)
def update_sonar_params(name: str, data: SonarParams) -> UpdateParamsResponse:
    sonar = get_sonar(name)
    if sonar is None:
        return JSONResponse(status_code=404, content={"error": f"Sonar '{name}' not found"})
    set_params(name, data.dict(exclude_unset=False))
    return UpdateParamsResponse(success=True, params=data)


@router.get("/api/sonar/{name}/image", summary="Get current sonar image as JPEG.")
def get_sonar_image(name: str):
    sonar = get_sonar(name)
    if sonar is None:
        return JSONResponse(status_code=404, content={"error": f"Sonar '{name}' not found"})
    try:
        return Response(content=_sonar_to_jpeg(sonar), media_type="image/jpeg")
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/api/sonar/{name}/data", summary="Get raw sonar map data as JSON.")
def get_sonar_data(name: str):
    sonar = get_sonar(name)
    if sonar is None:
        return JSONResponse(status_code=404, content={"error": f"Sonar '{name}' not found"})
    try:
        sonar_np = sonar.sonar_map.numpy()
        return JSONResponse(content={"shape": list(sonar_np.shape), "data": sonar_np.tolist()})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


# ===== Camera endpoints =====

@router.get("/api/camera/list", summary="List all registered underwater cameras.")
def get_camera_list():
    return JSONResponse(content={"cameras": list_cameras()})


@router.get("/api/camera/{name}/image", summary="Get current underwater camera image as JPEG.")
def get_camera_image(name: str):
    cam = get_camera(name)
    if cam is None:
        return JSONResponse(status_code=404, content={"error": f"Camera '{name}' not found"})
    try:
        jpeg_bytes = _camera_to_jpeg(cam)
        if jpeg_bytes is None:
            return JSONResponse(status_code=503, content={"error": "No frame available yet"})
        return Response(content=jpeg_bytes, media_type="image/jpeg")
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


# ===== Environment endpoints =====

@router.get("/api/environment/water", summary="Get current water rendering parameters.", response_model=WaterParams)
def get_water_params():
    return WaterParams(**get_env_state("water"))


@router.put("/api/environment/water", summary="Update water rendering parameters.", response_model=EnvironmentUpdateResponse)
def update_water_params(data: WaterParams):
    try:
        set_env_state("water", data.dict(exclude_unset=False))
        return EnvironmentUpdateResponse(success=True)
    except Exception as exc:
        return EnvironmentUpdateResponse(success=False, error=str(exc))


@router.get("/api/environment/lighting", summary="Get current lighting parameters.", response_model=LightingParams)
def get_lighting_params():
    return LightingParams(**get_env_state("lighting"))


@router.put("/api/environment/lighting", summary="Update lighting parameters.", response_model=EnvironmentUpdateResponse)
def update_lighting_params(data: LightingParams):
    try:
        set_env_state("lighting", data.dict(exclude_unset=False))
        return EnvironmentUpdateResponse(success=True)
    except Exception as exc:
        return EnvironmentUpdateResponse(success=False, error=str(exc))


# ===== Sonar Water (acoustic) endpoints =====

@router.get("/api/environment/sonar_water", summary="Get current sonar water (acoustic) parameters.", response_model=SonarWaterParams)
def get_sonar_water_params():
    return SonarWaterParams(**get_env_state("sonar_water"))


@router.put("/api/environment/sonar_water", summary="Update sonar water (acoustic) parameters.", response_model=EnvironmentUpdateResponse)
def update_sonar_water_params(data: SonarWaterParams):
    try:
        set_env_state("sonar_water", data.dict(exclude_unset=False))
        return EnvironmentUpdateResponse(success=True)
    except Exception as exc:
        return EnvironmentUpdateResponse(success=False, error=str(exc))


@router.get("/api/environment/water_presets", summary="List all water condition presets.")
def get_water_presets():
    return JSONResponse(content={"presets": WATER_CONDITION_PRESETS})


@router.put("/api/environment/water_preset/{name}", summary="Apply a water condition preset (optical + acoustic).", response_model=EnvironmentUpdateResponse)
def apply_water_preset(name: str):
    if name not in WATER_CONDITION_PRESETS:
        return JSONResponse(status_code=404, content={"error": f"Preset '{name}' not found"})
    try:
        preset = WATER_CONDITION_PRESETS[name]
        set_env_state("water", preset["water"])
        set_env_state("sonar_water", preset["sonar"])
        return EnvironmentUpdateResponse(success=True)
    except Exception as exc:
        return EnvironmentUpdateResponse(success=False, error=str(exc))


# ===== Materials endpoint =====

@router.get("/api/materials", summary="List available acoustic materials with reflectivity values.")
def get_materials():
    from isaacsim.oceansim.utils.acoustic_materials import ACOUSTIC_MATERIALS, list_materials
    materials = {}
    for name in list_materials():
        mat = ACOUSTIC_MATERIALS[name]
        materials[name] = {
            "reflectivity": mat["reflectivity"],
            "impedance_mrayl": mat["impedance_mrayl"],
            "description": mat["description"],
        }
    return JSONResponse(content={"materials": materials})


# ===== Object endpoints =====

@router.get("/api/environment/assets", summary="List available USD assets.")
def get_asset_list():
    try:
        from isaacsim.oceansim.utils.assets_utils import get_oceansim_assets_path
        assets_path = get_oceansim_assets_path()
    except Exception:
        assets_path = "/home/Talik/OceanSim_assets"
    spawnable_path = assets_path + "/spawnable"
    return JSONResponse(content={"assets": scan_assets(spawnable_path)})


@router.get("/api/environment/objects", summary="List spawned objects.")
def get_objects():
    return JSONResponse(content={"objects": list_spawned_objects()})


@router.post("/api/environment/objects", summary="Spawn an object into the scene.")
def spawn_object(data: dict):
    try:
        asset_path = data.get("asset_path", "")
        prim_name = data.get("prim_name", "object")
        position = data.get("position", [0.0, 0.0, 0.0])
        rotation = data.get("rotation", [0.0, 0.0, 0.0])
        scale = data.get("scale", [1.0, 1.0, 1.0])
        reflectivity = data.get("reflectivity", 1.0)
        material = data.get("material", None)

        if not asset_path:
            return JSONResponse(status_code=400, content={"error": "asset_path is required"})

        queue_spawn(asset_path, prim_name, position, rotation, scale, reflectivity, material=material)
        return JSONResponse(content={"success": True, "queued": prim_name})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.delete("/api/environment/objects/{prim_name}", summary="Remove a spawned object.")
def delete_object(prim_name: str):
    try:
        prim_path = f"/World/spawned/{prim_name}"
        queue_delete(prim_path)
        return JSONResponse(content={"success": True, "queued_delete": prim_path})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


# ===== WebSocket endpoints =====

async def sonar_websocket(websocket: WebSocket, name: str):
    await websocket.accept()
    try:
        sonar = get_sonar(name)
        while sonar is None:
            await asyncio.sleep(1.0)
            sonar = get_sonar(name)
        while True:
            await asyncio.sleep(0.25)
            s = get_sonar(name)
            if s is None:
                return
            try:
                await websocket.send_bytes(_sonar_to_jpeg(s))
            except Exception:
                pass
    except (WebSocketDisconnect, Exception):
        pass


async def camera_websocket(websocket: WebSocket, name: str):
    await websocket.accept()
    try:
        cam = get_camera(name)
        while cam is None:
            await asyncio.sleep(1.0)
            cam = get_camera(name)
        while True:
            await asyncio.sleep(0.25)
            c = get_camera(name)
            if c is None:
                return
            try:
                jpeg_bytes = _camera_to_jpeg(c)
                if jpeg_bytes is not None:
                    await websocket.send_bytes(jpeg_bytes)
            except Exception:
                pass
    except (WebSocketDisconnect, Exception):
        pass
