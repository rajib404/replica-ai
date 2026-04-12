"""Voice verification service using Resemblyzer for speaker embeddings."""

import io
import logging
import secrets
import time
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from resemblyzer import VoiceEncoder, preprocess_wav
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import FileStorage, get_storage
from app.models.owner import Owner
from app.models.voice import VerificationLog, VerificationResult

logger = logging.getLogger(__name__)

# Lazy-loaded singleton encoder (CPU-only, loads ~40 MB model once)
_encoder: VoiceEncoder | None = None


def _get_encoder() -> VoiceEncoder:
    global _encoder
    if _encoder is None:
        _encoder = VoiceEncoder("cpu")
    return _encoder


def _generate_id() -> str:
    ts = hex(int(time.time() * 1000))[2:]
    rand = secrets.token_hex(8)
    return f"c{ts}{rand}"


def _audio_bytes_to_wav(audio_bytes: bytes) -> np.ndarray:
    """Convert raw audio bytes (any format librosa supports) to a 16 kHz mono numpy array."""
    buf = io.BytesIO(audio_bytes)
    wav, sr = librosa.load(buf, sr=16000, mono=True)
    return wav


def _wav_duration_sec(wav: np.ndarray, sr: int = 16000) -> float:
    return len(wav) / sr


class VoiceProfileManager:
    """Manages voice enrollment and verification using Resemblyzer speaker embeddings."""

    def __init__(self, storage: FileStorage | None = None) -> None:
        self._storage = storage or get_storage()
        self._encoder = _get_encoder()

    # ─── Enrollment ───────────────────────────────────────

    async def enroll_voice(
        self,
        owner_id: str,
        audio_samples: list[bytes],
        db: AsyncSession,
    ) -> dict:
        """Enroll a voice profile from 3-5 audio samples.

        Each sample must be >= voice_min_duration_sec.
        Generates a speaker embedding per sample, averages them,
        and stores the result as a .npy file referenced by Owner.voice_profile_ref.
        """
        min_samples = settings.voice_min_samples
        max_samples = settings.voice_max_samples

        if len(audio_samples) < min_samples:
            return {
                "status": "needs_more_samples",
                "samples_received": len(audio_samples),
                "samples_required": min_samples,
                "message": f"Need at least {min_samples} samples, got {len(audio_samples)}.",
            }

        # Limit to max_samples
        samples = audio_samples[:max_samples]

        embeddings: list[np.ndarray] = []
        for i, raw in enumerate(samples):
            wav = _audio_bytes_to_wav(raw)
            duration = _wav_duration_sec(wav)
            if duration < settings.voice_min_duration_sec:
                return {
                    "status": "needs_more_samples",
                    "samples_received": len(audio_samples),
                    "samples_required": min_samples,
                    "message": (
                        f"Sample {i + 1} is too short ({duration:.1f}s). "
                        f"Minimum {settings.voice_min_duration_sec}s required."
                    ),
                }
            processed = preprocess_wav(wav)
            embedding = self._encoder.embed_utterance(processed)
            embeddings.append(embedding)

        # Average all sample embeddings into one profile
        profile_embedding = np.mean(embeddings, axis=0)

        # Save embedding as .npy file
        profile_id = _generate_id()
        npy_bytes = io.BytesIO()
        np.save(npy_bytes, profile_embedding)
        npy_bytes.seek(0)

        rel_path = self._storage.save_file(
            owner_id=owner_id,
            content_type="voice_profile",
            entry_id=profile_id,
            filename="embedding.npy",
            data=npy_bytes.read(),
        )

        # Update Owner.voice_profile_ref
        result = await db.execute(select(Owner).where(Owner.id == owner_id))
        owner = result.scalar_one_or_none()
        if owner is None:
            raise ValueError("Owner not found")

        owner.voice_profile_ref = rel_path
        await db.commit()

        logger.info("Voice profile enrolled for owner %s with %d samples", owner_id, len(samples))

        return {
            "status": "enrolled",
            "samples_received": len(samples),
            "samples_required": min_samples,
            "message": f"Voice profile enrolled successfully with {len(samples)} samples.",
        }

    # ─── Verification ────────────────────────────────────

    async def verify_voice(
        self,
        owner_id: str,
        audio_sample: bytes,
        db: AsyncSession,
        source: str = "api",
    ) -> VerificationResult:
        """Verify a voice sample against the stored profile using cosine similarity."""
        result = await db.execute(select(Owner).where(Owner.id == owner_id))
        owner = result.scalar_one_or_none()
        if owner is None:
            raise ValueError("Owner not found")

        if not owner.voice_profile_ref:
            raise ValueError("No voice profile enrolled for this owner")

        # Load stored embedding
        stored_bytes = self._storage.read_file(owner.voice_profile_ref)
        stored_embedding = np.load(io.BytesIO(stored_bytes))

        # Generate embedding from the new sample
        wav = _audio_bytes_to_wav(audio_sample)
        processed = preprocess_wav(wav)
        sample_embedding = self._encoder.embed_utterance(processed)

        # Cosine similarity
        similarity = float(
            np.dot(stored_embedding, sample_embedding)
            / (np.linalg.norm(stored_embedding) * np.linalg.norm(sample_embedding))
        )

        threshold = settings.voice_similarity_threshold
        verified = similarity >= threshold

        # Log verification attempt
        log_entry = VerificationLog(
            id=_generate_id(),
            owner_id=owner_id,
            method="voice_match",
            success=verified,
            similarity_score=similarity,
            source=source,
        )
        db.add(log_entry)
        await db.commit()

        logger.info(
            "Voice verification for owner %s: score=%.3f threshold=%.2f verified=%s",
            owner_id, similarity, threshold, verified,
        )

        return VerificationResult(
            verified=verified,
            similarity_score=round(similarity, 4),
            threshold=threshold,
        )

    # ─── Status ──────────────────────────────────────────

    async def get_enrollment_status(
        self, owner_id: str, db: AsyncSession
    ) -> dict:
        """Check whether the owner has an enrolled voice profile."""
        result = await db.execute(select(Owner).where(Owner.id == owner_id))
        owner = result.scalar_one_or_none()
        if owner is None:
            raise ValueError("Owner not found")

        enrolled = owner.voice_profile_ref is not None
        return {
            "enrolled": enrolled,
            "samples_stored": settings.voice_min_samples if enrolled else 0,
            "samples_required": settings.voice_min_samples,
        }


# ─── Singleton ──────────────────────────────────────────


_voice_manager: VoiceProfileManager | None = None


def get_voice_manager() -> VoiceProfileManager:
    global _voice_manager
    if _voice_manager is None:
        _voice_manager = VoiceProfileManager()
    return _voice_manager
