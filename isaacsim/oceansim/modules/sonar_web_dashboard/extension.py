"""Kit extension for the OceanSim sonar web dashboard."""

import os
import traceback

import carb
import omni.ext


class Extension(omni.ext.IExt):

    def on_startup(self, ext_id: str) -> None:
        carb.log_info("[SonarWebDashboard] Starting up")
        try:
            from fastapi.staticfiles import StaticFiles
            from omni.services.core import main
            from .api import router as api_router, sonar_websocket, camera_websocket

            self._api_router = api_router

            # Register REST API routes
            main.register_router(router=api_router, tags=["sonar-dashboard"])

            # Register WebSocket endpoints
            main.register_websocket_endpoint("/ws/sonar/{name}", sonar_websocket)
            main.register_websocket_endpoint("/ws/camera/{name}", camera_websocket)

            # Serve static web files
            web_dir = os.path.join(os.path.dirname(__file__), "web")
            if os.path.isdir(web_dir):
                main.register_mount("/sonar-dashboard", StaticFiles(directory=web_dir, html=True))
                carb.log_info(f"[SonarWebDashboard] Dashboard at /sonar-dashboard/")
            else:
                carb.log_warn(f"[SonarWebDashboard] web dir not found: {web_dir}")

        except Exception as e:
            carb.log_error(f"[SonarWebDashboard] Startup failed: {e}")
            carb.log_error(traceback.format_exc())

    def on_shutdown(self) -> None:
        carb.log_info("[SonarWebDashboard] Shutting down")
        try:
            from omni.services.core import main
            if hasattr(self, '_api_router'):
                main.deregister_router(router=self._api_router)
            main.deregister_mount("/sonar-dashboard")
        except Exception:
            pass
