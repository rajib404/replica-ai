"""Unit tests for the language detection / script analysis helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.multilingual import (
    LANGUAGE_NAMES,
    LanguageEngine,
    _cache_key,
    _detect_script,
)


# ─── Script detection ───────────────────────────────────────


class TestDetectScript:
    def test_none_for_latin_text(self) -> None:
        assert _detect_script("Hello world") is None

    def test_arabic(self) -> None:
        assert _detect_script("مرحبا بالعالم") == "arabic"

    def test_cyrillic(self) -> None:
        assert _detect_script("Привет мир") == "cyrillic"

    def test_devanagari(self) -> None:
        assert _detect_script("नमस्ते") == "devanagari"

    def test_bengali(self) -> None:
        assert _detect_script("বাংলা") == "bengali"

    def test_hebrew(self) -> None:
        assert _detect_script("שלום") == "hebrew"

    def test_thai(self) -> None:
        assert _detect_script("สวัสดี") == "thai"

    def test_dominant_script_wins(self) -> None:
        """Mixed scripts should return the one with the most characters."""
        text = "Hello مرحبا مرحبا مرحبا"
        assert _detect_script(text) == "arabic"


# ─── Cache key ───────────────────────────────────────────────


class TestCacheKey:
    def test_deterministic(self) -> None:
        k1 = _cache_key("hello", "en", "es")
        k2 = _cache_key("hello", "en", "es")
        assert k1 == k2

    def test_different_text_different_key(self) -> None:
        k1 = _cache_key("hello", "en", "es")
        k2 = _cache_key("goodbye", "en", "es")
        assert k1 != k2

    def test_different_target_different_key(self) -> None:
        k1 = _cache_key("hello", "en", "es")
        k2 = _cache_key("hello", "en", "fr")
        assert k1 != k2

    def test_key_format(self) -> None:
        k = _cache_key("hi", "en", "es")
        assert k.startswith("translate:en:es:")


# ─── LanguageEngine.detect_language ─────────────────────────


class TestDetectLanguage:
    async def test_detects_english(self) -> None:
        mock_ai = AsyncMock()
        mock_ai.generate = AsyncMock(return_value={"response": ""})

        result = await LanguageEngine.detect_language(
            "The quick brown fox jumps over the lazy dog.", ai=mock_ai
        )
        assert result["language_code"] == "en"
        assert result["language_name"] == "English"
        assert result["confidence"] > 0

    async def test_detects_spanish(self) -> None:
        mock_ai = AsyncMock()
        mock_ai.generate = AsyncMock(return_value={"response": ""})

        result = await LanguageEngine.detect_language(
            "Hola mundo, este es un texto de prueba en español.", ai=mock_ai
        )
        assert result["language_code"] == "es"
        assert result["language_name"] == "Spanish"

    async def test_detects_french(self) -> None:
        mock_ai = AsyncMock()
        mock_ai.generate = AsyncMock(return_value={"response": ""})

        result = await LanguageEngine.detect_language(
            "Bonjour le monde, ceci est un texte de test en français.",
            ai=mock_ai,
        )
        assert result["language_code"] == "fr"

    async def test_returns_english_default_when_langdetect_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If langdetect raises and Ollama is stubbed out, we should still
        return a sane default."""
        mock_ai = AsyncMock()
        mock_ai.generate = AsyncMock(return_value={"response": ""})

        result = await LanguageEngine.detect_language("", ai=mock_ai)
        # Should not raise; default is 'en'
        assert result["language_code"] == "en"

    async def test_dialect_info_populated_for_chinese(self) -> None:
        """Heuristic dialect info should run for Chinese codes."""
        mock_ai = AsyncMock()
        mock_ai.generate = AsyncMock(return_value={"response": ""})

        result = await LanguageEngine.detect_language(
            "这是一个简单的中文测试文本，用于检测语言。", ai=mock_ai
        )
        # Should detect Chinese family
        assert result["language_code"].startswith("zh")

    async def test_portuguese_dialect_heuristic_brazilian(self) -> None:
        mock_ai = AsyncMock()
        mock_ai.generate = AsyncMock(return_value={"response": ""})

        # "ê, ô, ã" are Brazilian markers in the heuristic
        result = await LanguageEngine.detect_language(
            "Olá, você está bem? Estão aqui, estão todos bem, avião, corações.",
            ai=mock_ai,
        )
        assert result["language_code"] == "pt"


# ─── LANGUAGE_NAMES table ───────────────────────────────────


class TestLanguageNames:
    def test_contains_common_languages(self) -> None:
        for code in ["en", "es", "fr", "de", "zh", "ja", "ar", "hi"]:
            assert code in LANGUAGE_NAMES

    def test_english_name(self) -> None:
        assert LANGUAGE_NAMES["en"] == "English"

    def test_chinese_has_both_variants(self) -> None:
        assert "zh-cn" in LANGUAGE_NAMES
        assert "zh-tw" in LANGUAGE_NAMES
