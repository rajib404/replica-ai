"""Voice verification endpoints: enroll, check, and status."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_guard import AuthContext, require_auth
from app.core.config import settings
from app.core.database import get_db
from app.models.voice import VoiceCheckResponse, VoiceEnrollResponse, VoiceStatusResponse
from app.services.voice_verify import VoiceProfileManager, get_voice_manager

router = APIRouter(prefix="/api/verify/voice", tags=["voice"])

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}
MAX_SAMPLE_SIZE = 50 * 1024 * 1024  # 50 MB


def _get_voice_manager() -> VoiceProfileManager:
    return get_voice_manager()


def _validate_audio_file(file: UploadFile) -> None:
    """Validate that the uploaded file has an allowed audio extension."""
    if file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_AUDIO_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported audio format. Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}",
            )


@router.post("/enroll", response_model=VoiceEnrollResponse)
async def voice_enroll(
    samples: list[UploadFile],
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    manager: VoiceProfileManager = Depends(_get_voice_manager),
) -> VoiceEnrollResponse:
    """Enroll a voice profile from 3-5 audio samples.

    Each sample should be at least 10 seconds of clear speech.
    Upload multiple files in the `samples` field.
    """
    if len(samples) < settings.voice_min_samples:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Need at least {settings.voice_min_samples} audio samples, got {len(samples)}.",
        )

    for f in samples:
        _validate_audio_file(f)

    # Read all sample bytes
    audio_bytes_list: list[bytes] = []
    for f in samples:
        data = await f.read()
        if len(data) > MAX_SAMPLE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Sample {f.filename} exceeds {MAX_SAMPLE_SIZE // (1024 * 1024)}MB limit.",
            )
        audio_bytes_list.append(data)

    try:
        result = await manager.enroll_voice(
            owner_id=auth.subject_id,
            audio_samples=audio_bytes_list,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return VoiceEnrollResponse(**result)


@router.post("/check", response_model=VoiceCheckResponse)
async def voice_check(
    sample: UploadFile,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    manager: VoiceProfileManager = Depends(_get_voice_manager),
) -> VoiceCheckResponse:
    """Verify a voice sample against the enrolled profile."""
    _validate_audio_file(sample)

    data = await sample.read()
    if len(data) > MAX_SAMPLE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Sample exceeds {MAX_SAMPLE_SIZE // (1024 * 1024)}MB limit.",
        )

    try:
        result = await manager.verify_voice(
            owner_id=auth.subject_id,
            audio_sample=data,
            db=db,
            source="api",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    message = "Voice verified successfully." if result.verified else "Voice verification failed."
    return VoiceCheckResponse(
        verified=result.verified,
        similarity_score=result.similarity_score,
        threshold=result.threshold,
        message=message,
    )


@router.get("/status", response_model=VoiceStatusResponse)
async def voice_status(
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    manager: VoiceProfileManager = Depends(_get_voice_manager),
) -> VoiceStatusResponse:
    """Check voice enrollment status for the authenticated owner."""
    try:
        result = await manager.get_enrollment_status(
            owner_id=auth.subject_id,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return VoiceStatusResponse(**result)
