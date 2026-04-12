"""Face verification service using face_recognition for face embeddings."""

import asyncio
import io
import logging
import secrets
import time

import face_recognition
import numpy as np
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import FileStorage, get_storage
from app.models.owner import Owner
from app.models.voice import VerificationLog

logger = logging.getLogger(__name__)


def _generate_id() -> str:
    ts = hex(int(time.time() * 1000))[2:]
    rand = secrets.token_hex(8)
    return f"c{ts}{rand}"


def _image_bytes_to_array(image_bytes: bytes) -> np.ndarray:
    """Convert raw image bytes (JPEG/PNG/WebP) to a numpy RGB array."""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")
    return np.array(img)


def _extract_face_encoding(image_array: np.ndarray) -> np.ndarray | None:
    """Extract face encoding from an image array. Returns None if no face detected."""
    encodings = face_recognition.face_encodings(image_array)
    if not encodings:
        return None
    return encodings[0]


class FaceProfileManager:
    """Manages face enrollment and verification using face_recognition embeddings."""

    def __init__(self, storage: FileStorage | None = None) -> None:
        self._storage = storage or get_storage()

    # ─── Enrollment ───────────────────────────────────────

    async def enroll_face(
        self,
        owner_id: str,
        images: list[bytes],
        db: AsyncSession,
    ) -> dict:
        """Enroll a face profile from 5+ image samples.

        Extracts face encodings from each image, averages them,
        and stores the result as a .npy file referenced by Owner.face_profile_ref.
        """
        min_samples = settings.face_min_samples
        max_samples = settings.face_max_samples

        if len(images) < min_samples:
            return {
                "status": "needs_more_samples",
                "samples_received": len(images),
                "samples_required": min_samples,
                "message": f"Need at least {min_samples} samples, got {len(images)}.",
            }

        samples = images[:max_samples]
        loop = asyncio.get_running_loop()

        encodings: list[np.ndarray] = []
        for i, raw in enumerate(samples):
            image_array = await loop.run_in_executor(None, _image_bytes_to_array, raw)
            encoding = await loop.run_in_executor(None, _extract_face_encoding, image_array)
            if encoding is None:
                return {
                    "status": "no_face_detected",
                    "samples_received": len(images),
                    "samples_required": min_samples,
                    "message": f"No face detected in sample {i + 1}. Please ensure your face is clearly visible.",
                }
            encodings.append(encoding)

        # Average all sample encodings into one profile
        profile_encoding = np.mean(encodings, axis=0)

        # Save encoding as .npy file
        profile_id = _generate_id()
        npy_bytes = io.BytesIO()
        np.save(npy_bytes, profile_encoding)
        npy_bytes.seek(0)

        rel_path = self._storage.save_file(
            owner_id=owner_id,
            content_type="face_profile",
            entry_id=profile_id,
            filename="encoding.npy",
            data=npy_bytes.read(),
        )

        # Update Owner.face_profile_ref
        result = await db.execute(select(Owner).where(Owner.id == owner_id))
        owner = result.scalar_one_or_none()
        if owner is None:
            raise ValueError("Owner not found")

        owner.face_profile_ref = rel_path
        await db.commit()

        logger.info("Face profile enrolled for owner %s with %d samples", owner_id, len(samples))

        return {
            "status": "enrolled",
            "samples_received": len(samples),
            "samples_required": min_samples,
            "message": f"Face profile enrolled successfully with {len(samples)} samples.",
        }

    # ─── Verification ────────────────────────────────────

    async def verify_face(
        self,
        owner_id: str,
        image: bytes,
        db: AsyncSession,
        source: str = "api",
    ) -> dict:
        """Verify a face image against the stored profile using face distance."""
        result = await db.execute(select(Owner).where(Owner.id == owner_id))
        owner = result.scalar_one_or_none()
        if owner is None:
            raise ValueError("Owner not found")

        if not owner.face_profile_ref:
            raise ValueError("No face profile enrolled for this owner")

        # Load stored encoding
        stored_bytes = self._storage.read_file(owner.face_profile_ref)
        stored_encoding = np.load(io.BytesIO(stored_bytes))

        loop = asyncio.get_running_loop()

        # Extract encoding from the new image
        image_array = await loop.run_in_executor(None, _image_bytes_to_array, image)
        sample_encoding = await loop.run_in_executor(None, _extract_face_encoding, image_array)

        if sample_encoding is None:
            # Log failed attempt
            log_entry = VerificationLog(
                id=_generate_id(),
                owner_id=owner_id,
                method="face_match",
                success=False,
                similarity_score=0.0,
                source=source,
            )
            db.add(log_entry)
            await db.commit()

            return {
                "verified": False,
                "confidence": 0.0,
                "threshold": settings.face_similarity_threshold,
                "message": "No face detected in the image.",
            }

        # Compute face distance
        distance = float(face_recognition.face_distance([stored_encoding], sample_encoding)[0])
        confidence = round(1.0 - distance, 4)
        threshold = settings.face_similarity_threshold
        verified = distance <= (1.0 - threshold)

        # Log verification attempt
        log_entry = VerificationLog(
            id=_generate_id(),
            owner_id=owner_id,
            method="face_match",
            success=verified,
            similarity_score=confidence,
            source=source,
        )
        db.add(log_entry)
        await db.commit()

        logger.info(
            "Face verification for owner %s: confidence=%.3f threshold=%.2f verified=%s",
            owner_id, confidence, threshold, verified,
        )

        return {
            "verified": verified,
            "confidence": confidence,
            "threshold": threshold,
            "message": "Face verified successfully." if verified else "Face verification failed.",
        }

    # ─── Status ──────────────────────────────────────────

    async def get_enrollment_status(
        self, owner_id: str, db: AsyncSession
    ) -> dict:
        """Check whether the owner has an enrolled face profile."""
        result = await db.execute(select(Owner).where(Owner.id == owner_id))
        owner = result.scalar_one_or_none()
        if owner is None:
            raise ValueError("Owner not found")

        enrolled = owner.face_profile_ref is not None
        return {
            "enrolled": enrolled,
            "samples_stored": settings.face_min_samples if enrolled else 0,
            "samples_required": settings.face_min_samples,
        }


# ─── Singleton ──────────────────────────────────────────


_face_manager: FaceProfileManager | None = None


def get_face_manager() -> FaceProfileManager:
    global _face_manager
    if _face_manager is None:
        _face_manager = FaceProfileManager()
    return _face_manager
