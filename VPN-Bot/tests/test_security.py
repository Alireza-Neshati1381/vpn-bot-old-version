"""Tests for security utilities."""
import pytest
from vpn_bot import security


class TestSecurity:
    """Test security validation and sanitization."""

    def test_sanitize_string_normal(self):
        """Test string sanitization with normal input."""
        result = security.sanitize_string("Hello World")
        assert result == "Hello World"

    def test_sanitize_string_with_nulls(self):
        """Test string sanitization removes null bytes."""
        result = security.sanitize_string("Hello\x00World")
        assert result == "HelloWorld"

    def test_sanitize_string_max_length(self):
        """Test string sanitization respects max length."""
        long_string = "A" * 1000
        result = security.sanitize_string(long_string, max_length=100)
        assert len(result) == 100

    def test_sanitize_string_whitespace(self):
        """Test string sanitization strips whitespace."""
        result = security.sanitize_string("  Hello World  ")
        assert result == "Hello World"

    def test_validate_numeric_valid(self):
        """Test numeric validation with valid input."""
        is_valid, value = security.validate_numeric("42", min_value=0, max_value=100)
        assert is_valid is True
        assert value == 42

    def test_validate_numeric_below_min(self):
        """Test numeric validation below minimum."""
        is_valid, value = security.validate_numeric("-5", min_value=0, max_value=100)
        assert is_valid is False
        assert value is None

    def test_validate_numeric_above_max(self):
        """Test numeric validation above maximum."""
        is_valid, value = security.validate_numeric("150", min_value=0, max_value=100)
        assert is_valid is False
        assert value is None

    def test_validate_numeric_invalid_format(self):
        """Test numeric validation with invalid format."""
        is_valid, value = security.validate_numeric("not_a_number")
        assert is_valid is False
        assert value is None

    def test_validate_float_valid(self):
        """Test float validation with valid input."""
        is_valid, value = security.validate_float("3.14", min_value=0.0, max_value=10.0)
        assert is_valid is True
        assert value == 3.14

    def test_validate_username_valid(self):
        """Test username validation with valid input."""
        assert security.validate_username("@john_doe") is True
        assert security.validate_username("john_doe") is True
        assert security.validate_username("user123") is True

    def test_validate_username_invalid(self):
        """Test username validation with invalid input."""
        assert security.validate_username("ab") is False  # Too short
        assert security.validate_username("user@name") is False  # Invalid char
        assert security.validate_username("") is False  # Empty

    def test_validate_url_valid(self):
        """Test URL validation with valid URLs."""
        assert security.validate_url("https://example.com") is True
        assert security.validate_url("http://panel.example.com:8080") is True
        assert security.validate_url("https://example.com/path/to/panel") is True

    def test_validate_url_invalid(self):
        """Test URL validation with invalid URLs."""
        assert security.validate_url("not_a_url") is False
        assert security.validate_url("ftp://example.com") is False
        assert security.validate_url("") is False

    def test_validate_file_extension_valid(self):
        """Test file extension validation with valid extensions."""
        assert security.validate_file_extension("photo.jpg") is True
        assert security.validate_file_extension("receipt.png") is True
        assert security.validate_file_extension("image.jpeg") is True

    def test_validate_file_extension_invalid(self):
        """Test file extension validation with invalid extensions."""
        assert security.validate_file_extension("script.exe") is False
        assert security.validate_file_extension("document.pdf") is False
        assert security.validate_file_extension("file") is False

    def test_secure_filename(self):
        """Test secure filename generation."""
        result = security.secure_filename("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result
        # os.path.basename removes leading path components
        assert result == "passwd"

    def test_secure_filename_with_spaces(self):
        """Test secure filename removes spaces."""
        result = security.secure_filename("my file name.jpg")
        assert " " not in result
        assert result == "myfilename.jpg"

    def test_validate_admin_pin_correct(self):
        """Test admin PIN validation with correct PIN."""
        assert security.validate_admin_pin("12345", "12345") is True

    def test_validate_admin_pin_incorrect(self):
        """Test admin PIN validation with incorrect PIN."""
        assert security.validate_admin_pin("12345", "54321") is False

    def test_validate_admin_pin_different_length(self):
        """Test admin PIN validation with different lengths."""
        assert security.validate_admin_pin("123", "12345") is False

    def test_validate_admin_pin_empty(self):
        """Test admin PIN validation with empty input."""
        assert security.validate_admin_pin("", "12345") is False
        assert security.validate_admin_pin("12345", "") is False
