"""Pydantic models for multilingual / language endpoints."""

from pydantic import BaseModel, Field


# ─── Requests ────────────────────────────────────────────


class DetectLanguageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    source_lang: str | None = None  # auto-detect if None
    target_lang: str = "en"


class TransliterateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    source_script: str  # e.g. "arabic", "cyrillic", "devanagari", "chinese"
    target_script: str = "latin"


# ─── Responses ───────────────────────────────────────────


class LanguageDetectionResponse(BaseModel):
    language_code: str
    language_name: str
    confidence: float
    dialect_info: str | None = None


class TranslateResponse(BaseModel):
    translated_text: str
    source_lang: str
    target_lang: str
    method: str  # "cache", "ollama", "deepl", "google"


class TransliterateResponse(BaseModel):
    transliterated_text: str
    source_script: str
    target_script: str
