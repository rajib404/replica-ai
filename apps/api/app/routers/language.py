"""Language detection and translation endpoints."""

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends

from app.core.ai_client import AIServiceClient, get_ai_client
from app.core.auth_guard import require_auth
from app.core.redis import get_redis
from app.models.language import (
    DetectLanguageRequest,
    LanguageDetectionResponse,
    TranslateRequest,
    TranslateResponse,
    TransliterateRequest,
    TransliterateResponse,
)
from app.services.multilingual import LanguageEngine

router = APIRouter(prefix="/api/language", tags=["language"])


@router.post("/detect", response_model=LanguageDetectionResponse)
async def detect_language(
    body: DetectLanguageRequest,
    _user=Depends(require_auth),
    ai: AIServiceClient = Depends(get_ai_client),
):
    """Detect language and dialect of the given text."""
    result = await LanguageEngine.detect_language(text=body.text, ai=ai)
    return LanguageDetectionResponse(**result)


@router.post("/translate", response_model=TranslateResponse)
async def translate_text(
    body: TranslateRequest,
    _user=Depends(require_auth),
    r: aioredis.Redis = Depends(get_redis),
    ai: AIServiceClient = Depends(get_ai_client),
):
    """Translate text between languages with Redis caching."""
    result = await LanguageEngine.translate(
        text=body.text,
        source_lang=body.source_lang,
        target_lang=body.target_lang,
        r=r,
        ai=ai,
    )
    return TranslateResponse(**result)


@router.post("/transliterate", response_model=TransliterateResponse)
async def transliterate_text(
    body: TransliterateRequest,
    _user=Depends(require_auth),
    ai: AIServiceClient = Depends(get_ai_client),
):
    """Transliterate text between scripts (e.g., Arabic to Latin)."""
    result = await LanguageEngine.transliterate(
        text=body.text,
        source_script=body.source_script,
        target_script=body.target_script,
        ai=ai,
    )
    return TransliterateResponse(**result)
