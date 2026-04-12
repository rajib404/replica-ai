"""Pydantic models for video call WebSocket messages."""

from pydantic import BaseModel, Field


# ─── WebSocket message types ─────────────────────────────


class WSVideoFaceFrame(BaseModel):
    """Client sends face frame control message, followed by binary JPEG."""
    type: str = "face_frame"


class WSVideoFaceResult(BaseModel):
    """Server sends face verification result."""
    type: str = "face_result"
    verified: bool
    confidence: float
    message: str


class WSVideoCallStatus(BaseModel):
    """Server sends periodic video call status."""
    type: str = "video_status"
    face_verified: bool = False
    call_duration_sec: int = 0
