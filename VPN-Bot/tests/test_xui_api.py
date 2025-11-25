"""Tests for XUI API client."""
import pytest
from unittest.mock import Mock, patch
from requests.exceptions import ConnectionError, SSLError

from vpn_bot.xui_api import (
    XUIClient,
    XUIError,
    XUIConnectionError,
    MAX_RETRIES,
)


class TestXUIClient:
    """Tests for XUIClient class."""

    def test_init_sets_base_url_with_trailing_slash(self):
        """Test that base_url gets a trailing slash."""
        client = XUIClient("https://example.com", "user", "pass")
        assert client.base_url == "https://example.com/"

    def test_init_preserves_trailing_slash(self):
        """Test that existing trailing slash is preserved."""
        client = XUIClient("https://example.com/", "user", "pass")
        assert client.base_url == "https://example.com/"

    def test_build_url_joins_path(self):
        """Test that _build_url joins paths correctly."""
        client = XUIClient("https://example.com/panel/", "user", "pass")
        result = client._build_url("login/")
        assert result == "https://example.com/panel/login/"


class TestXUIConnectionErrors:
    """Tests for connection error handling."""

    def test_ssl_error_raises_connection_error_with_hint(self):
        """Test that SSL errors are converted to XUIConnectionError with helpful message."""
        client = XUIClient("https://example.com:8080/panel/", "user", "pass")

        # Create a mock SSL error
        ssl_error = SSLError("SSL: UNEXPECTED_EOF_WHILE_READING")

        with patch.object(client.session, "post", side_effect=ssl_error):
            with pytest.raises(XUIConnectionError) as exc_info:
                client._login()

            error_msg = str(exc_info.value)
            assert "SSL/TLS error" in error_msg
            assert "https://" in error_msg
            assert "http://" in error_msg

    def test_connection_refused_error_message(self):
        """Test that connection refused errors have helpful message."""
        client = XUIClient("https://example.com:8080/panel/", "user", "pass")

        conn_error = ConnectionError("Connection refused")

        with patch.object(client.session, "post", side_effect=conn_error):
            with pytest.raises(XUIConnectionError) as exc_info:
                client._login()

            error_msg = str(exc_info.value)
            assert "Connection refused" in error_msg
            assert "panel is running" in error_msg

    def test_timeout_error_message(self):
        """Test that timeout errors have helpful message."""
        client = XUIClient("https://example.com:8080/panel/", "user", "pass")

        timeout_error = ConnectionError("Connection timed out")

        with patch.object(client.session, "post", side_effect=timeout_error):
            with pytest.raises(XUIConnectionError) as exc_info:
                client._login()

            error_msg = str(exc_info.value)
            assert "timed out" in error_msg
            assert "network connectivity" in error_msg

    def test_retry_on_ssl_error(self):
        """Test that SSL errors trigger retries."""
        client = XUIClient("https://example.com:8080/panel/", "user", "pass")

        # Create a mock that fails 3 times
        ssl_error = SSLError("SSL error")
        mock_post = Mock(side_effect=ssl_error)

        with patch.object(client.session, "post", mock_post):
            with pytest.raises(XUIConnectionError):
                client._login()

            # Should have retried MAX_RETRIES times
            assert mock_post.call_count == MAX_RETRIES

    @patch("vpn_bot.xui_api.time.sleep")
    def test_retry_with_backoff(self, mock_sleep):
        """Test that retries use exponential backoff."""
        client = XUIClient("https://example.com:8080/panel/", "user", "pass")

        ssl_error = SSLError("SSL error")

        with patch.object(client.session, "post", side_effect=ssl_error):
            with pytest.raises(XUIConnectionError):
                client._login()

        # Should have called sleep for backoff (MAX_RETRIES - 1 times)
        assert mock_sleep.call_count == MAX_RETRIES - 1

    def test_successful_login_after_retry(self):
        """Test that login succeeds after a retry."""
        client = XUIClient("https://example.com:8080/panel/", "user", "pass")

        # First call fails, second succeeds
        success_response = Mock()
        success_response.json.return_value = {"success": True}
        success_response.raise_for_status = Mock()

        ssl_error = SSLError("SSL error")
        mock_post = Mock(side_effect=[ssl_error, success_response])

        with patch.object(client.session, "post", mock_post):
            with patch("vpn_bot.xui_api.time.sleep"):
                client._login()

        assert client._authenticated is True

    def test_request_retry_on_connection_error(self):
        """Test that _request retries on connection errors."""
        client = XUIClient("https://example.com:8080/panel/", "user", "pass")
        client._authenticated = True

        conn_error = ConnectionError("Connection error")
        mock_request = Mock(side_effect=conn_error)

        with patch.object(client.session, "request", mock_request):
            with patch("vpn_bot.xui_api.time.sleep"):
                with pytest.raises(XUIConnectionError):
                    client._request("GET", "test/path")

            assert mock_request.call_count == MAX_RETRIES


class TestXUIConnectionErrorException:
    """Tests for the XUIConnectionError exception class."""

    def test_inherits_from_xui_error(self):
        """Test that XUIConnectionError inherits from XUIError."""
        error = XUIConnectionError("test error")
        assert isinstance(error, XUIError)

    def test_can_be_caught_as_xui_error(self):
        """Test that XUIConnectionError can be caught as XUIError."""
        try:
            raise XUIConnectionError("test error")
        except XUIError:
            pass  # Expected
        except Exception:
            pytest.fail("XUIConnectionError should be caught as XUIError")
