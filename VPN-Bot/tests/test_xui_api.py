"""Tests for XUI API client."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from requests.exceptions import ConnectionError, SSLError
from http.cookiejar import Cookie

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
        result = client._build_url("panel/api/test")
        assert result == "https://example.com/panel/panel/api/test"

    def test_url_without_login_uses_directly_for_login(self):
        """Test that URL without /login is used directly as login URL."""
        client = XUIClient("https://test.irlesson.ir:8080/testpatch/", "user", "pass")
        assert client._login_url == "https://test.irlesson.ir:8080/testpatch/"
        assert client._api_base_url == "https://test.irlesson.ir:8080/testpatch/"

    def test_url_with_login_suffix_uses_directly_for_login(self):
        """Test that URL with /login is used directly as login URL."""
        client = XUIClient("https://example.com/panel/login", "user", "pass")
        assert client._login_url == "https://example.com/panel/login/"
        assert client.base_url == "https://example.com/panel/login/"

    def test_url_with_login_suffix_strips_for_api(self):
        """Test that URL with /login has it stripped for API calls."""
        client = XUIClient("https://example.com/panel/login", "user", "pass")
        assert client._api_base_url == "https://example.com/panel/"

    def test_build_url_uses_api_base_after_login_stripped(self):
        """Test that _build_url uses API base URL correctly."""
        client = XUIClient("https://example.com/panel/login", "user", "pass")
        result = client._build_url("panel/api/inbounds/list")
        assert result == "https://example.com/panel/panel/api/inbounds/list"

    def test_case_insensitive_login_detection(self):
        """Test that /Login suffix (mixed case) is detected."""
        client = XUIClient("https://example.com/panel/Login", "user", "pass")
        assert client._url_ends_with_login is True
        assert client._api_base_url == "https://example.com/panel/"

    def test_login_in_middle_of_path_not_stripped(self):
        """Test that login in middle of path is not stripped."""
        client = XUIClient("https://example.com/login/panel", "user", "pass")
        assert client._url_ends_with_login is False
        assert client._api_base_url == "https://example.com/login/panel/"

    def test_session_has_accept_header(self):
        """Test that session is initialized with Accept header."""
        client = XUIClient("https://example.com/", "user", "pass")
        assert client.session.headers.get("Accept") == "application/json"

    def test_default_timeout_is_20_seconds(self):
        """Test that default timeout is 20 seconds."""
        client = XUIClient("https://example.com/", "user", "pass")
        assert client.timeout == 20


class TestSSLErrorDetection:
    """Tests for SSL error detection helper method."""

    def test_is_ssl_error_with_ssl_error_instance(self):
        """Test _is_ssl_error returns True for SSLError instance."""
        client = XUIClient("https://example.com/", "user", "pass")
        assert client._is_ssl_error(SSLError("test")) is True

    def test_is_ssl_error_with_ssl_in_message(self):
        """Test _is_ssl_error returns True for errors with SSL in message."""
        client = XUIClient("https://example.com/", "user", "pass")
        assert client._is_ssl_error(ConnectionError("SSL handshake failed")) is True
        assert client._is_ssl_error(ConnectionError("ssl error occurred")) is True

    def test_is_ssl_error_with_non_ssl_error(self):
        """Test _is_ssl_error returns False for non-SSL errors."""
        client = XUIClient("https://example.com/", "user", "pass")
        assert client._is_ssl_error(ConnectionError("Connection refused")) is False
        assert client._is_ssl_error(ConnectionError("Connection timed out")) is False


class TestLoginMethods:
    """Tests for improved login methods."""

    def test_validate_login_response_with_cookies(self):
        """Test that login validation passes when cookies are set."""
        client = XUIClient("https://example.com/", "user", "pass")
        
        # Add a mock cookie to the session
        mock_cookie = MagicMock()
        mock_cookie.name = "session"
        client.session.cookies.set_cookie(mock_cookie)
        
        data = {"success": True}
        assert client._validate_login_response(data) is True

    def test_validate_login_response_with_obj_token(self):
        """Test that login validation passes when obj token is in response."""
        client = XUIClient("https://example.com/", "user", "pass")
        
        data = {"success": True, "obj": "some_token"}
        assert client._validate_login_response(data) is True

    def test_validate_login_response_fails_on_api_error(self):
        """Test that login validation fails when API returns failure."""
        client = XUIClient("https://example.com/", "user", "pass")
        
        data = {"success": False, "msg": "Invalid credentials"}
        assert client._validate_login_response(data) is False

    def test_validate_login_response_handles_none(self):
        """Test that login validation handles None gracefully."""
        client = XUIClient("https://example.com/", "user", "pass")
        assert client._validate_login_response(None) is False

    def test_login_tries_json_then_form_data(self):
        """Test that login tries JSON first, then falls back to form data."""
        client = XUIClient("https://example.com/", "user", "pass")
        
        # JSON fails, form data succeeds
        json_response = Mock()
        json_response.json.return_value = {"success": False}
        json_response.raise_for_status = Mock()
        
        form_response = Mock()
        form_response.json.return_value = {"success": True, "obj": "token"}
        form_response.raise_for_status = Mock()
        
        # Track calls to distinguish JSON vs form data
        call_count = [0]
        def mock_post(*args, **kwargs):
            call_count[0] += 1
            if "json" in kwargs:
                return json_response
            else:  # data parameter = form data
                return form_response
        
        with patch.object(client.session, "post", side_effect=mock_post):
            client._login()
        
        assert client._authenticated is True
        assert call_count[0] == 2  # Called twice: once for JSON, once for form data


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
    def test_ssl_error_logs_hint_on_final_retry(self, mock_sleep):
        """Test that SSL errors log a hint on the final retry attempt."""
        client = XUIClient("https://example.com:8080/panel/", "user", "pass")

        ssl_error = SSLError("SSL: UNEXPECTED_EOF_WHILE_READING")

        with patch.object(client.session, "post", side_effect=ssl_error):
            with patch("vpn_bot.xui_api.LOGGER") as mock_logger:
                with pytest.raises(XUIConnectionError):
                    client._login()

                # Check that the final warning includes the hint
                warning_calls = mock_logger.warning.call_args_list
                assert len(warning_calls) == MAX_RETRIES
                # The last warning should include the hint
                final_warning_args = warning_calls[-1][0]
                # The format string is the first arg, hint is the last positional arg
                assert "Hint: Try changing the server URL from https:// to http://" in final_warning_args[-1]

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

    def test_request_handles_403_as_auth_error(self):
        """Test that 403 status triggers re-authentication like 401."""
        client = XUIClient("https://example.com:8080/panel/", "user", "pass")
        client._authenticated = True

        # First request returns 403, then succeed after re-auth
        forbidden_response = Mock()
        forbidden_response.status_code = 403
        forbidden_response.raise_for_status = Mock()
        
        success_response = Mock()
        success_response.status_code = 200
        success_response.text = '{"success": true}'
        success_response.json.return_value = {"success": True}
        success_response.raise_for_status = Mock()

        # Mock login to succeed
        login_response = Mock()
        login_response.json.return_value = {"success": True, "obj": "token"}
        login_response.raise_for_status = Mock()

        request_call_count = [0]
        def mock_request(method, url, **kwargs):
            request_call_count[0] += 1
            if request_call_count[0] == 1:
                return forbidden_response
            return success_response

        with patch.object(client.session, "request", side_effect=mock_request):
            with patch.object(client.session, "post", return_value=login_response):
                result = client._request("GET", "test/path")

        assert result == {"success": True}
        assert request_call_count[0] == 2  # Initial request + retry after re-auth


class TestNewAPIMethods:
    """Tests for new API methods."""

    def test_list_inbounds_returns_list(self):
        """Test that list_inbounds returns a list of inbounds."""
        client = XUIClient("https://example.com/", "user", "pass")
        client._authenticated = True

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true, "obj": [{"id": 1}, {"id": 2}]}'
        mock_response.json.return_value = {"success": True, "obj": [{"id": 1}, {"id": 2}]}
        mock_response.raise_for_status = Mock()

        with patch.object(client.session, "request", return_value=mock_response):
            result = client.list_inbounds()

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == 1

    def test_list_inbounds_returns_empty_list_on_error(self):
        """Test that list_inbounds returns empty list when obj is not a list."""
        client = XUIClient("https://example.com/", "user", "pass")
        client._authenticated = True

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true, "obj": null}'
        mock_response.json.return_value = {"success": True, "obj": None}
        mock_response.raise_for_status = Mock()

        with patch.object(client.session, "request", return_value=mock_response):
            result = client.list_inbounds()

        assert result == []

    def test_delete_client_by_path(self):
        """Test delete_client_by_path uses path-based endpoint."""
        client = XUIClient("https://example.com/", "user", "pass")
        client._authenticated = True

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true}'
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = Mock()

        with patch.object(client.session, "request", return_value=mock_response) as mock_request:
            client.delete_client_by_path(1, "test-uuid")

        # Verify the path format
        call_args = mock_request.call_args
        assert "panel/api/inbounds/1/delClient/test-uuid" in call_args[0][1]

    def test_check_connection_success(self):
        """Test check_connection returns True on success."""
        client = XUIClient("https://example.com/", "user", "pass")

        login_response = Mock()
        login_response.json.return_value = {"success": True, "obj": "token"}
        login_response.raise_for_status = Mock()

        with patch.object(client.session, "post", return_value=login_response):
            result = client.check_connection()

        assert result is True

    def test_check_connection_failure(self):
        """Test check_connection returns False on failure."""
        client = XUIClient("https://example.com/", "user", "pass")

        with patch.object(client.session, "post", side_effect=SSLError("SSL error")):
            with patch("vpn_bot.xui_api.time.sleep"):
                result = client.check_connection()

        assert result is False

    def test_get_client_traffic_by_id_returns_dict(self):
        """Test get_client_traffic_by_id returns traffic dict."""
        client = XUIClient("https://example.com/", "user", "pass")
        client._authenticated = True

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true, "obj": {"up": 100, "down": 200}}'
        mock_response.json.return_value = {"success": True, "obj": {"up": 100, "down": 200}}
        mock_response.raise_for_status = Mock()

        with patch.object(client.session, "request", return_value=mock_response):
            result = client.get_client_traffic_by_id("test-uuid")

        assert result == {"up": 100, "down": 200}

    def test_get_client_traffic_by_id_handles_list_response(self):
        """Test get_client_traffic_by_id handles list response format."""
        client = XUIClient("https://example.com/", "user", "pass")
        client._authenticated = True

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true, "obj": [{"up": 100, "down": 200}]}'
        mock_response.json.return_value = {"success": True, "obj": [{"up": 100, "down": 200}]}
        mock_response.raise_for_status = Mock()

        with patch.object(client.session, "request", return_value=mock_response):
            result = client.get_client_traffic_by_id("test-uuid")

        assert result == {"up": 100, "down": 200}


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
