"""Pydantic schemas for face verification endpoints."""

from pydantic import BaseModel


class FaceEnrollResponse(BaseModel):
    status: str  # "enrolled" | "needs_more_samples" | "no_face_detected"
    samples_received: int
    samples_required: int
    message: str


class FaceCheckResponse(BaseModel):
    verified: bool
    confidence: float  # 1.0 - distance
    threshold: float
    message: str


class FaceStatusResponse(BaseModel):
    enrolled: bool
    samples_stored: int
    samples_required: int
