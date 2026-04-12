"""Multilingual engine: language detection, translation, transliteration, and caching."""

import hashlib
import json
import logging
import unicodedata

import redis.asyncio as aioredis

from app.core.ai_client import AIServiceClient, get_ai_client
from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Language metadata ──────────────────────────────────

LANGUAGE_NAMES: dict[str, str] = {
    "af": "Afrikaans",
    "ar": "Arabic",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "ca": "Catalan",
    "cs": "Czech",
    "cy": "Welsh",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "fa": "Persian",
    "fi": "Finnish",
    "fr": "French",
    "gu": "Gujarati",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "kn": "Kannada",
    "ko": "Korean",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mr": "Marathi",
    "ne": "Nepali",
    "nl": "Dutch",
    "no": "Norwegian",
    "pa": "Punjabi",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "so": "Somali",
    "sq": "Albanian",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tl": "Tagalog",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "vi": "Vietnamese",
    "zh-cn": "Chinese (Simplified)",
    "zh-tw": "Chinese (Traditional)",
    "zh": "Chinese",
}

# Script detection heuristics (Unicode block ranges)
_SCRIPT_RANGES: dict[str, list[tuple[int, int]]] = {
    "arabic": [(0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "cyrillic": [(0x0400, 0x04FF), (0x0500, 0x052F)],
    "devanagari": [(0x0900, 0x097F), (0xA8E0, 0xA8FF)],
    "bengali": [(0x0980, 0x09FF)],
    "chinese": [(0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0x2E80, 0x2EFF)],
    "japanese": [(0x3040, 0x309F), (0x30A0, 0x30FF), (0x4E00, 0x9FFF)],
    "korean": [(0xAC00, 0xD7AF), (0x1100, 0x11FF), (0x3130, 0x318F)],
    "thai": [(0x0E00, 0x0E7F)],
    "tamil": [(0x0B80, 0x0BFF)],
    "telugu": [(0x0C00, 0x0C7F)],
    "hebrew": [(0x0590, 0x05FF)],
}


def _detect_script(text: str) -> str | None:
    """Detect the dominant non-Latin script in text."""
    counts: dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        for script, ranges in _SCRIPT_RANGES.items():
            if any(lo <= cp <= hi for lo, hi in ranges):
                counts[script] = counts.get(script, 0) + 1
                break
    if not counts:
        return None
    return max(counts, key=counts.get)  # type: ignore[arg-type]


def _cache_key(text: str, source: str, target: str) -> str:
    """Build a Redis cache key for a translation pair."""
    h = hashlib.sha256(f"{text}|{source}|{target}".encode()).hexdigest()[:16]
    return f"translate:{source}:{target}:{h}"


# ─── LanguageEngine ─────────────────────────────────────


class LanguageEngine:
    """Centralized multilingual service: detect, translate, transliterate."""

    # ── Language detection ──────────────────────────────

    @staticmethod
    async def detect_language(
        text: str,
        ai: AIServiceClient | None = None,
    ) -> dict:
        """Detect language with dialect info.

        Primary: langdetect.  Fallback: Ollama LLM.
        Returns: {language_code, language_name, confidence, dialect_info}
        """
        lang_code = "en"
        confidence = 0.0
        dialect_info: str | None = None

        # Primary: langdetect
        try:
            from langdetect import detect_langs

            results = detect_langs(text)
            if results:
                top = results[0]
                lang_code = str(top.lang)
                confidence = round(top.prob, 3)
        except Exception:
            logger.debug("langdetect failed, falling back to Ollama")

        # If low confidence or ambiguous, use Ollama for dialect detection
        if confidence < 0.85 or lang_code in ("zh-cn", "zh-tw", "pt"):
            try:
                client = ai or get_ai_client()
                ollama_result = await client.generate(
                    prompt=(
                        "What language and dialect is this text? "
                        "Respond in JSON: "
                        '{\"language_code\": \"...\", \"language_name\": \"...\", '
                        '\"confidence\": 0.0-1.0, \"dialect_info\": \"...\"}\n\n'
                        f"Text: {text[:500]}"
                    ),
                    temperature=0.1,
                    max_tokens=200,
                )
                raw = ollama_result.get("response", "")
                # Try to extract JSON from the response
                parsed = _extract_json(raw)
                if parsed:
                    if parsed.get("confidence", 0) > confidence:
                        lang_code = parsed.get("language_code", lang_code)
                        confidence = parsed.get("confidence", confidence)
                    dialect_info = parsed.get("dialect_info")
            except Exception:
                logger.debug("Ollama dialect detection failed")

        # Enrich dialect info based on script analysis
        if not dialect_info:
            script = _detect_script(text)
            if script and lang_code in ("zh", "zh-cn", "zh-tw"):
                dialect_info = (
                    "Simplified Chinese" if script == "chinese" and lang_code != "zh-tw"
                    else "Traditional Chinese"
                )
            elif lang_code == "pt":
                # Heuristic: Brazilian Portuguese uses more ê, ô
                br_markers = sum(1 for c in text if c in "êôã")
                pt_markers = sum(1 for c in text if c in "àéó")
                if br_markers > pt_markers:
                    dialect_info = "Brazilian Portuguese"
                elif pt_markers > br_markers:
                    dialect_info = "European Portuguese"

        language_name = LANGUAGE_NAMES.get(lang_code, lang_code.title())

        return {
            "language_code": lang_code,
            "language_name": language_name,
            "confidence": confidence,
            "dialect_info": dialect_info,
        }

    # ── Translation ─────────────────────────────────────

    @staticmethod
    async def translate(
        text: str,
        source_lang: str | None,
        target_lang: str = "en",
        r: aioredis.Redis | None = None,
        ai: AIServiceClient | None = None,
    ) -> dict:
        """Translate text. Checks Redis cache first, then Ollama, then optional external API.

        Returns: {translated_text, source_lang, target_lang, method}
        """
        # Auto-detect source if not provided
        if not source_lang:
            detection = await LanguageEngine.detect_language(text, ai)
            source_lang = detection["language_code"]

        # No-op if source == target
        if source_lang == target_lang:
            return {
                "translated_text": text,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "method": "passthrough",
            }

        # Check Redis cache
        if r:
            cache_k = _cache_key(text, source_lang, target_lang)
            try:
                cached = await r.get(cache_k)
                if cached:
                    return {
                        "translated_text": cached,
                        "source_lang": source_lang,
                        "target_lang": target_lang,
                        "method": "cache",
                    }
            except Exception:
                logger.debug("Redis cache lookup failed")

        translated: str | None = None
        method = "ollama"

        # Try external API first if configured (higher quality)
        ext_api = settings.translation_external_api.lower()
        if ext_api == "deepl" and settings.deepl_api_key:
            translated = await _translate_deepl(text, source_lang, target_lang)
            if translated:
                method = "deepl"
        elif ext_api == "google" and settings.google_translate_api_key:
            translated = await _translate_google(text, source_lang, target_lang)
            if translated:
                method = "google"

        # Fallback: Ollama
        if not translated:
            client = ai or get_ai_client()
            src_name = LANGUAGE_NAMES.get(source_lang, source_lang)
            tgt_name = LANGUAGE_NAMES.get(target_lang, target_lang)
            prompt = (
                f"Translate the following {src_name} text to {tgt_name}. "
                f"Output ONLY the translation, nothing else:\n\n{text}"
            )
            result = await client.generate(prompt=prompt, temperature=0.1, max_tokens=4096)
            translated = result.get("response", "").strip()
            method = "ollama"

        if not translated:
            translated = text  # absolute fallback

        # Store in Redis cache
        if r:
            try:
                await r.setex(
                    _cache_key(text, source_lang, target_lang),
                    settings.translation_cache_ttl_seconds,
                    translated,
                )
            except Exception:
                logger.debug("Redis cache write failed")

        return {
            "translated_text": translated,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "method": method,
        }

    # ── Transliteration ─────────────────────────────────

    @staticmethod
    async def transliterate(
        text: str,
        source_script: str,
        target_script: str = "latin",
        ai: AIServiceClient | None = None,
    ) -> dict:
        """Transliterate text between scripts.

        For simple cases uses Unicode NFKD decomposition.
        For complex cases (CJK, Arabic) falls back to Ollama.
        Returns: {transliterated_text, source_script, target_script}
        """
        result_text = text

        if target_script == "latin":
            # Try Unicode decomposition first (works for accented Latin, Cyrillic partially)
            nfkd = unicodedata.normalize("NFKD", text)
            ascii_chars = []
            for ch in nfkd:
                cat = unicodedata.category(ch)
                if cat.startswith("L") or cat.startswith("N") or ch in " .,!?;:'\"-()":
                    if ord(ch) < 128:
                        ascii_chars.append(ch)

            # If we got a reasonable amount of Latin chars, use it
            latin_ratio = len(ascii_chars) / max(len(text), 1)
            if latin_ratio > 0.3:
                result_text = "".join(ascii_chars)
            else:
                # Ollama-based transliteration for complex scripts
                client = ai or get_ai_client()
                prompt = (
                    f"Transliterate the following {source_script} text to Latin script (romanization). "
                    f"Output ONLY the transliteration, nothing else:\n\n{text}"
                )
                ollama_result = await client.generate(
                    prompt=prompt, temperature=0.1, max_tokens=2048
                )
                result_text = ollama_result.get("response", text).strip()
        else:
            # Non-Latin target: use Ollama
            client = ai or get_ai_client()
            prompt = (
                f"Transliterate the following text from {source_script} script "
                f"to {target_script} script. "
                f"Output ONLY the transliteration:\n\n{text}"
            )
            ollama_result = await client.generate(
                prompt=prompt, temperature=0.1, max_tokens=2048
            )
            result_text = ollama_result.get("response", text).strip()

        return {
            "transliterated_text": result_text,
            "source_script": source_script,
            "target_script": target_script,
        }

    # ── Chat language awareness ─────────────────────────

    @staticmethod
    def build_language_system_prompt(detected_lang: str) -> str:
        """Return a system prompt fragment for language-aware chat."""
        lang_name = LANGUAGE_NAMES.get(detected_lang, detected_lang)
        return (
            f"The user is currently writing in {lang_name}. "
            "Respond in the same language the user is writing in. "
            "If they mix languages, you may do the same naturally. "
            "Always match their language and formality level."
        )


# ─── External API helpers ───────────────────────────────


async def _translate_deepl(text: str, source: str, target: str) -> str | None:
    """Call DeepL API for translation."""
    import httpx

    # Map common language codes to DeepL format
    deepl_map = {"en": "EN", "es": "ES", "fr": "FR", "de": "DE", "pt": "PT-BR",
                 "it": "IT", "nl": "NL", "pl": "PL", "ru": "RU", "ja": "JA",
                 "zh": "ZH", "ko": "KO", "ar": "AR"}
    src = deepl_map.get(source, source.upper())
    tgt = deepl_map.get(target, target.upper())

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api-free.deepl.com/v2/translate",
                data={
                    "auth_key": settings.deepl_api_key,
                    "text": text,
                    "source_lang": src,
                    "target_lang": tgt,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                translations = data.get("translations", [])
                if translations:
                    return translations[0].get("text")
    except Exception:
        logger.debug("DeepL translation failed")
    return None


async def _translate_google(text: str, source: str, target: str) -> str | None:
    """Call Google Cloud Translation API."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://translation.googleapis.com/language/translate/v2",
                params={"key": settings.google_translate_api_key},
                json={
                    "q": text,
                    "source": source,
                    "target": target,
                    "format": "text",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                translations = data.get("data", {}).get("translations", [])
                if translations:
                    return translations[0].get("translatedText")
    except Exception:
        logger.debug("Google Translate API failed")
    return None


def _extract_json(text: str) -> dict | None:
    """Try to extract a JSON object from a possibly-messy LLM response."""
    # Try direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # Try to find JSON within the text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except (json.JSONDecodeError, TypeError):
            pass
    return None
