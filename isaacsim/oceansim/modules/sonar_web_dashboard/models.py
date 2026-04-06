"""Pydantic models for the sonar web dashboard API."""

from typing import List, Optional
from pydantic import BaseModel, Field


class SonarParams(BaseModel):
    binning_method: str = Field("sum", description="'sum' or 'mean'")
    normalizing_method: str = Field("range", description="'all' or 'range'")
    attenuation: float = Field(0.1, ge=0.0, le=1.0)
    gau_noise_param: float = Field(0.2, ge=0.0, le=1.0)
    ray_noise_param: float = Field(0.05, ge=0.0, le=0.5)
    intensity_offset: float = Field(0.0, ge=-1.0, le=1.0)
    intensity_gain: float = Field(1.0, ge=0.1, le=5.0)
    central_peak: float = Field(2.0, ge=0.0, le=10.0)
    central_std: float = Field(0.001, ge=0.0001, le=0.1)


class SonarInfo(BaseModel):
    name: str
    min_range: float
    max_range: float
    range_res: float
    hori_fov: float
    vert_fov: float
    angular_res: float
    hori_res: int
    sonar_map_shape: List[int]


class SonarListResponse(BaseModel):
    sonars: List[SonarInfo]


class UpdateParamsResponse(BaseModel):
    success: bool
    params: Optional[SonarParams] = None
    error: Optional[str] = None


# ===== Environment models =====

class WaterParams(BaseModel):
    backscatter_r: float = Field(0.0, ge=0.0, le=1.0)
    backscatter_g: float = Field(0.31, ge=0.0, le=1.0)
    backscatter_b: float = Field(0.24, ge=0.0, le=1.0)
    backscatter_coeff_r: float = Field(0.05, ge=0.0, le=1.0)
    backscatter_coeff_g: float = Field(0.05, ge=0.0, le=1.0)
    backscatter_coeff_b: float = Field(0.2, ge=0.0, le=1.0)
    attenuation_coeff_r: float = Field(0.05, ge=0.0, le=1.0)
    attenuation_coeff_g: float = Field(0.05, ge=0.0, le=1.0)
    attenuation_coeff_b: float = Field(0.05, ge=0.0, le=1.0)


class LightingParams(BaseModel):
    intensity: float = Field(50000.0, ge=0.0, le=200000.0)
    color_temperature: float = Field(6500.0, ge=1000.0, le=12000.0)
    elevation: float = Field(45.0, ge=-90.0, le=90.0)
    azimuth: float = Field(0.0, ge=-180.0, le=180.0)
    enabled: bool = Field(True)


class SonarWaterParams(BaseModel):
    acoustic_attenuation: float = Field(0.2, ge=0.0, le=1.0)
    gau_noise: float = Field(0.05, ge=0.0, le=1.0)
    ray_noise: float = Field(0.02, ge=0.0, le=0.5)


class EnvironmentUpdateResponse(BaseModel):
    success: bool
    error: Optional[str] = None


WATER_CONDITION_PRESETS = {
    "clear_ocean": {
        "sonar": {"acoustic_attenuation": 0.2, "gau_noise": 0.05, "ray_noise": 0.02},
        "water": {"backscatter_r": 0.0, "backscatter_g": 0.1, "backscatter_b": 0.15, "backscatter_coeff_r": 0.02, "backscatter_coeff_g": 0.02, "backscatter_coeff_b": 0.08, "attenuation_coeff_r": 0.02, "attenuation_coeff_g": 0.02, "attenuation_coeff_b": 0.02},
    },
    "coastal": {
        "sonar": {"acoustic_attenuation": 0.4, "gau_noise": 0.15, "ray_noise": 0.08},
        "water": {"backscatter_r": 0.0, "backscatter_g": 0.25, "backscatter_b": 0.2, "backscatter_coeff_r": 0.04, "backscatter_coeff_g": 0.04, "backscatter_coeff_b": 0.15, "attenuation_coeff_r": 0.04, "attenuation_coeff_g": 0.04, "attenuation_coeff_b": 0.04},
    },
    "murky_harbor": {
        "sonar": {"acoustic_attenuation": 0.7, "gau_noise": 0.40, "ray_noise": 0.20},
        "water": {"backscatter_r": 0.05, "backscatter_g": 0.35, "backscatter_b": 0.25, "backscatter_coeff_r": 0.08, "backscatter_coeff_g": 0.08, "backscatter_coeff_b": 0.25, "attenuation_coeff_r": 0.08, "attenuation_coeff_g": 0.08, "attenuation_coeff_b": 0.08},
    },
    "turbid_river": {
        "sonar": {"acoustic_attenuation": 0.85, "gau_noise": 0.60, "ray_noise": 0.30},
        "water": {"backscatter_r": 0.1, "backscatter_g": 0.4, "backscatter_b": 0.2, "backscatter_coeff_r": 0.12, "backscatter_coeff_g": 0.12, "backscatter_coeff_b": 0.3, "attenuation_coeff_r": 0.12, "attenuation_coeff_g": 0.12, "attenuation_coeff_b": 0.12},
    },
}
