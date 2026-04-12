"""Unit tests for the static access rule templates."""

from __future__ import annotations

from app.services.family_access import TEMPLATES, FamilyAccessManager


class TestAccessTemplates:
    def test_get_templates_returns_all(self) -> None:
        templates = FamilyAccessManager.get_templates()
        assert len(templates) == len(TEMPLATES)
        assert len(templates) >= 4

    def test_every_template_has_required_fields(self) -> None:
        for t in TEMPLATES:
            assert t.name
            assert t.label
            assert t.description
            assert t.config is not None
            assert t.config.template_name == t.name

    def test_spouse_full_has_voice_match(self) -> None:
        spouse = next(t for t in TEMPLATES if t.name == "spouse_full")
        assert spouse.config.access_level == "full"
        assert spouse.config.verification_method == "voice_match"

    def test_child_stories_blocks_sensitive_topics(self) -> None:
        child = next(t for t in TEMPLATES if t.name == "child_stories")
        assert child.config.access_level == "limited"
        assert child.config.topic_restrictions is not None
        blocked = child.config.topic_restrictions.blocked
        assert "financial" in blocked
        assert "medical" in blocked
        assert "legal" in blocked
        assert "passwords" in blocked

    def test_grandchild_legacy_is_read_only(self) -> None:
        grand = next(t for t in TEMPLATES if t.name == "grandchild_legacy")
        assert grand.config.access_level == "read_only"

    def test_trusted_friend_uses_secret_word(self) -> None:
        friend = next(t for t in TEMPLATES if t.name == "trusted_friend")
        assert friend.config.verification_method == "secret_word"

    def test_template_names_are_unique(self) -> None:
        names = [t.name for t in TEMPLATES]
        assert len(names) == len(set(names))

    def test_all_topic_restrictions_block_passwords(self) -> None:
        """Any limited or read-only template must block password-adjacent
        topics — this is a privacy invariant of the system."""
        for t in TEMPLATES:
            if t.config.access_level in ("limited", "read_only"):
                if t.config.topic_restrictions is not None:
                    assert "passwords" in t.config.topic_restrictions.blocked
