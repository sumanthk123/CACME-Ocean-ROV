"""REST API and WebSocket endpoints for the sonar web dashboard."""

import asyncio
import io

import numpy as np
from PIL import Image

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import Response, JSONResponse

from omni.services.core import routers

from .sonar_bridge import get_sonar, list_sonars, get_params, set_params
from .models import SonarParams, SonarInfo, SonarListResponse, UpdateParamsResponse

router = routers.ServiceAPIRouter()


def _sonar_to_jpeg(sonar, quality=80):
    """Convert sonar_image warp array to JPEG bytes."""
    img_np = sonar.sonar_image.numpy()  # GPU -> CPU copy, shape (H, W, 4) uint8 RGBA
    pil_img = Image.fromarray(img_np[:, :, :3])  # drop alpha
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


@router.get(
    "/api/sonar/list",
    summary="List all registered sonar sensors.",
    response_model=SonarListResponse,
)
def get_sonar_list() -> SonarListResponse:
    sonars = []
    for name in list_sonars():
        s = get_sonar(name)
        if s is not None:
            sonars.append(SonarInfo(
                name=name,
                min_range=s.min_range,
                max_range=s.max_range,
                range_res=s.range_res,
                hori_fov=s.hori_fov,
                vert_fov=s.vert_fov,
                angular_res=s.angular_res,
                hori_res=s.hori_res,
                sonar_map_shape=list(s.sonar_map.shape),
            ))
    return SonarListResponse(sonars=sonars)


@router.get(
    "/api/sonar/{name}/params",
    summary="Get current sonar processing parameters.",
    response_model=SonarParams,
)
def get_sonar_params(name: str):
    sonar = get_sonar(name)
    if sonar is None:
        return JSONResponse(status_code=404, content={"error": f"Sonar '{name}' not found"})
    params = get_params(name)
    return SonarParams(**params)


@router.put(
    "/api/sonar/{name}/params",
    summary="Update sonar processing parameters.",
    response_model=UpdateParamsResponse,
)
def update_sonar_params(name: str, data: SonarParams) -> UpdateParamsResponse:
    sonar = get_sonar(name)
    if sonar is None:
        return JSONResponse(status_code=404, content={"error": f"Sonar '{name}' not found"})
    new_params = data.dict(exclude_unset=False)
    set_params(name, new_params)
    return UpdateParamsResponse(success=True, params=data)


@router.get(
    "/api/sonar/{name}/image",
    summary="Get current sonar image as JPEG.",
)
def get_sonar_image(name: str):
    sonar = get_sonar(name)
    if sonar is None:
        return JSONResponse(status_code=404, content={"error": f"Sonar '{name}' not found"})
    try:
        jpeg_bytes = _sonar_to_jpeg(sonar)
        return Response(content=jpeg_bytes, media_type="image/jpeg")
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get(
    "/api/sonar/{name}/data",
    summary="Get raw sonar map data as JSON.",
)
def get_sonar_data(name: str):
    sonar = get_sonar(name)
    if sonar is None:
        return JSONResponse(status_code=404, content={"error": f"Sonar '{name}' not found"})
    try:
        sonar_np = sonar.sonar_map.numpy()  # shape (range_bins, azimuth_bins, 3) vec3
        return JSONResponse(content={
            "shape": list(sonar_np.shape),
            "data": sonar_np.tolist(),
        })
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


async def sonar_websocket(websocket: WebSocket, name: str):
    """WebSocket endpoint that streams sonar JPEG frames at ~10 FPS."""
    await websocket.accept()
    sonar = get_sonar(name)
    if sonar is None:
        await websocket.close(code=4004, reason=f"Sonar '{name}' not found")
        return
    try:
        while True:
            await asyncio.sleep(0.1)  # ~10 FPS
            s = get_sonar(name)
            if s is None:
                await websocket.close(code=4004, reason="Sonar disconnected")
                return
            try:
                jpeg_bytes = _sonar_to_jpeg(s)
                await websocket.send_bytes(jpeg_bytes)
            except Exception:
                pass  # skip frame on error (e.g. sonar not yet initialized)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
