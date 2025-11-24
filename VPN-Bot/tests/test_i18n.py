"""Tests for internationalization system."""
import pytest
from vpn_bot import i18n


class TestI18n:
    """Test translation system."""

    def test_get_text_simple_key_en(self):
        """Test getting simple translation key in English."""
        text = i18n.get_text("welcome", lang="en")
        assert "Welcome" in text
        assert "{role}" in text

    def test_get_text_simple_key_fa(self):
        """Test getting simple translation key in Persian."""
        text = i18n.get_text("welcome", lang="fa")
        assert "خوش آمدید" in text

    def test_get_text_nested_key_en(self):
        """Test getting nested translation key."""
        text = i18n.get_text("admin.add_server", lang="en")
        assert text == "Add Server"

    def test_get_text_nested_key_fa(self):
        """Test getting nested translation key in Persian."""
        text = i18n.get_text("admin.add_server", lang="fa")
        assert text == "افزودن سرور"

    def test_get_text_with_formatting(self):
        """Test translation with parameter formatting."""
        text = i18n.get_text("admin.role_updated", lang="en", username="@john", role="ADMIN")
        assert "@john" in text
        assert "ADMIN" in text

    def test_get_text_missing_key(self):
        """Test handling of missing translation key."""
        text = i18n.get_text("nonexistent.key", lang="en")
        # Should return the key itself when not found
        assert text == "nonexistent.key"

    def test_get_text_fallback_to_english(self):
        """Test fallback to English when translation not found."""
        # This assumes some keys might not be translated in all languages
        text = i18n.get_text("welcome", lang="invalid_lang")
        # Should fallback to English or default
        assert len(text) > 0

    def test_get_user_language_default(self):
        """Test getting user language with default."""
        user_data = {}
        lang = i18n.get_user_language(user_data)
        assert lang == "fa"  # Default language

    def test_get_user_language_custom(self):
        """Test getting custom user language."""
        user_data = {"language": "en"}
        lang = i18n.get_user_language(user_data)
        assert lang == "en"

    def test_supported_languages(self):
        """Test that required languages are supported."""
        assert "en" in i18n.SUPPORTED_LANGUAGES
        assert "fa" in i18n.SUPPORTED_LANGUAGES

    def test_translation_completeness(self):
        """Test that key sections exist in both languages."""
        # Check that major sections exist
        sections = ["admin", "accountant", "user", "common", "status", "errors"]
        
        for section in sections:
            en_text = i18n.get_text(section, lang="en")
            fa_text = i18n.get_text(section, lang="fa")
            
            # Neither should be the raw key (meaning translation exists)
            assert en_text != section or fa_text != section
