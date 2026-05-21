"""
modules.prospecting.schemas
============================
Schemas Pydantic para os endpoints de prospeccao geolocalizada.
"""
from pydantic import BaseModel, field_validator


class SearchRequest(BaseModel):
    lat: float
    lng: float
    radius_km: int = 50

    @field_validator("radius_km")
    @classmethod
    def validate_radius(cls, v: int) -> int:
        if v < 5 or v > 300:
            raise ValueError("radius_km deve ser entre 5 e 300")
        return v
