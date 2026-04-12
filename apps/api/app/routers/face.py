"""Face verification endpoints: enroll, check, and status."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_guard import AuthContext, require_auth
from app.core.config import settings
from app.core.database import get_db
from app.models.face import FaceCheckResponse, FaceEnrollResponse, FaceStatusResponse
from app.services.face_verify import FaceProfileManager, get_face_manager

router = APIRouter(prefix="/api/verify/face", tags=["face"])

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_SAMPLE_SIZE = settings.face_max_image_size_mb * 1024 * 1024


def _get_face_manager() -> FaceProfileManager:
    return get_face_manager()


def _validate_image_file(file: UploadFile) -> None:
    """Validate that the uploaded file has an allowed image extension."""
    if file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported image format. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}",
            )


@router.post("/enroll", response_model=FaceEnrollResponse)
async def face_enroll(
    samples: list[UploadFile],
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    manager: FaceProfileManager = Depends(_get_face_manager),
) -> FaceEnrollResponse:
    """Enroll a face profile from 5+ image samples.

    Each sample should be a clear photo of your face from different angles.
    Upload multiple files in the `samples` field.
    """
    if len(samples) < settings.face_min_samples:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Need at least {settings.face_min_samples} image samples, got {len(samples)}.",
        )

    for f in samples:
        _validate_image_file(f)

    # Read all sample bytes
    image_bytes_list: list[bytes] = []
    for f in samples:
        data = await f.read()
        if len(data) > MAX_SAMPLE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Sample {f.filename} exceeds {settings.face_max_image_size_mb}MB limit.",
            )
        image_bytes_list.append(data)

    try:
        result = await manager.enroll_face(
            owner_id=auth.subject_id,
            images=image_bytes_list,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return FaceEnrollResponse(**result)


@router.post("/check", response_model=FaceCheckResponse)
async def face_check(
    sample: UploadFile,
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    manager: FaceProfileManager = Depends(_get_face_manager),
) -> FaceCheckResponse:
    """Verify a face image against the enrolled profile."""
    _validate_image_file(sample)

    data = await sample.read()
    if len(data) > MAX_SAMPLE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Sample exceeds {settings.face_max_image_size_mb}MB limit.",
        )

    try:
        result = await manager.verify_face(
            owner_id=auth.subject_id,
            image=data,
            db=db,
            source="api",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return FaceCheckResponse(**result)


@router.get("/status", response_model=FaceStatusResponse)
async def face_status(
    auth: AuthContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    manager: FaceProfileManager = Depends(_get_face_manager),
) -> FaceStatusResponse:
    """Check face enrollment status for the authenticated owner."""
    try:
        result = await manager.get_enrollment_status(
            owner_id=auth.subject_id,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return FaceStatusResponse(**result)
