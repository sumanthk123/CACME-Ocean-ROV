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
