import pytest
import os
import json
import requests # For requests.exceptions
import responses
from unittest.mock import patch, MagicMock

@responses.activate
def test_proxy_target_connection_timeout(client, mocker, caplog):
    """Test 504 response when connection to target URL times out."""
    mocked_target_url = "http://timeout-target/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_url)
    # Also clear os.environ for TARGET_BASE_URL to ensure cot_proxy.TARGET_BASE_URL is the one used if not patched.
    mocker.patch.dict(os.environ, {"TARGET_BASE_URL": mocked_target_url }, clear=True)


    # Configure responses to simulate a timeout for any request to this URL
    responses.add(
        responses.POST,
        f"{mocked_target_url}v1/chat/completions", # Use the mocked URL
        body=requests.exceptions.Timeout("Connection timed out")
    )

    request_body = {"model": "test-timeout", "messages": [{"role": "user", "content": "Hello"}]}
    proxy_response = client.post("/v1/chat/completions", json=request_body)

    assert proxy_response.status_code == 504
    assert proxy_response.content_type == "application/json"
    data = json.loads(proxy_response.data)
    assert "error" in data
    assert f"Connection to {mocked_target_url}v1/chat/completions timed out" in data["error"]
    assert f"Connection to {mocked_target_url}v1/chat/completions timed out" in caplog.text

@responses.activate
def test_proxy_target_ssl_error(client, mocker, caplog):
    """Test 502 response for SSL verification failure."""
    mocked_target_url = "https://ssl-error-target/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_url)
    mocker.patch.dict(os.environ, {"TARGET_BASE_URL": mocked_target_url}, clear=True)

    responses.add(
        responses.POST,
        f"{mocked_target_url}v1/chat/completions",
        body=requests.exceptions.SSLError("SSL verification failed")
    )

    request_body = {"model": "test-ssl", "messages": [{"role": "user", "content": "Hello"}]}
    proxy_response = client.post("/v1/chat/completions", json=request_body)

    assert proxy_response.status_code == 502
    assert proxy_response.content_type == "application/json"
    data = json.loads(proxy_response.data)
    assert "error" in data
    assert "SSL verification failed: SSL verification failed" in data["error"] # cot_proxy adds prefix
    assert "SSL verification failed: SSL verification failed" in caplog.text

@responses.activate
def test_proxy_target_connection_error(client, mocker, caplog):
    """Test 502 response for general connection error to target."""
    mocked_target_url = "http://conn-error-target/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_url)
    mocker.patch.dict(os.environ, {"TARGET_BASE_URL": mocked_target_url}, clear=True)

    responses.add(
        responses.POST,
        f"{mocked_target_url}v1/chat/completions",
        body=requests.exceptions.ConnectionError("Failed to connect")
    )

    request_body = {"model": "test-conn-error", "messages": [{"role": "user", "content": "Hello"}]}
    proxy_response = client.post("/v1/chat/completions", json=request_body)

    assert proxy_response.status_code == 502
    assert proxy_response.content_type == "application/json"
    data = json.loads(proxy_response.data)
    assert "error" in data
    assert f"Failed to connect to {mocked_target_url}v1/chat/completions: Failed to connect" in data["error"]
    assert f"Failed to connect to {mocked_target_url}v1/chat/completions: Failed to connect" in caplog.text

@responses.activate
def test_proxy_target_returns_4xx_error(client, mocker, caplog):
    """Test proxy forwards 4xx errors from the target API directly (non-streaming)."""
    mocked_target_url = "http://target-4xx-error/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_url)
    mocker.patch.dict(os.environ, {"TARGET_BASE_URL": mocked_target_url}, clear=True)

    target_error_body = {"detail": "Unauthorized", "code": "auth_failed"}
    target_status_code = 401
    target_content_type = "application/vnd.api+json"

    responses.add(
        responses.POST,
        f"{mocked_target_url}v1/chat/completions",
        json=target_error_body,
        status=target_status_code,
        content_type=target_content_type
    )

    request_body = {"model": "test-4xx", "stream": False, "messages": [{"role": "user", "content": "Hello"}]}
    proxy_response = client.post("/v1/chat/completions", json=request_body)

    assert proxy_response.status_code == target_status_code
    assert proxy_response.content_type == target_content_type
    assert proxy_response.json == target_error_body # Original error body should be passed through
    
    assert f"Target server error: {target_status_code}" in caplog.text
    assert f"Error response: {json.dumps(target_error_body)}" in caplog.text # Check logged error content

@responses.activate
def test_proxy_target_returns_5xx_error(client, mocker, caplog):
    """Test proxy forwards 5xx errors from the target API directly (non-streaming)."""
    mocked_target_url = "http://target-5xx-error/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_url)
    mocker.patch.dict(os.environ, {"TARGET_BASE_URL": mocked_target_url}, clear=True)

    target_error_body_text = "Internal Server Error on Target"
    target_status_code = 503
    target_content_type = "text/plain"

    responses.add(
        responses.POST,
        f"{mocked_target_url}v1/chat/completions",
        body=target_error_body_text,
        status=target_status_code,
        content_type=target_content_type
    )

    request_body = {"model": "test-5xx", "stream": False, "messages": [{"role": "user", "content": "Hello"}]}
    proxy_response = client.post("/v1/chat/completions", json=request_body)

    assert proxy_response.status_code == target_status_code
    assert proxy_response.content_type == target_content_type
    assert proxy_response.data.decode('utf-8') == target_error_body_text
    
    assert f"Target server error: {target_status_code}" in caplog.text
    assert f"Error response: {target_error_body_text}" in caplog.text

def test_proxy_request_exception_before_target_call(client, mocker, caplog):
    """
    Test 502 response if a RequestException occurs before/during the main request to target.
    Example: Malformed URL constructed, or other issues within the `requests.request` call setup
    not covered by specific exceptions like Timeout, SSLError, ConnectionError.
    """
    mocked_target_url = "http://valid-looking-url/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_url)
    mocker.patch.dict(os.environ, {"TARGET_BASE_URL": mocked_target_url}, clear=True)


    # Patch requests.request directly to raise a generic RequestException
    # The URL for requests.request will be constructed using the (patched) cot_proxy.TARGET_BASE_URL
    with patch('requests.request', side_effect=requests.exceptions.RequestException("Generic request problem")) as mock_req_call:
        request_body = {"model": "test-generic-req-ex", "messages": [{"role": "user", "content": "Hello"}]}
        proxy_response = client.post("/v1/chat/completions", json=request_body) # Path is appended to TARGET_BASE_URL

        assert proxy_response.status_code == 502
        data = json.loads(proxy_response.data)
        assert "error" in data
        # The error message in cot_proxy.py for this case is: f"Failed to forward request: {str(e)}"
        assert "Failed to forward request: Generic request problem" in data["error"]
        assert "Failed to forward request: Generic request problem" in caplog.text
        mock_req_call.assert_called_once() # Ensure requests.request was attempted

def test_teardown_request_closes_api_response(mocker): # Removed client and app fixtures as they are not directly used for this simplified test
    """
    Test that cleanup_request closes g.api_response if it exists.
    """
    from cot_proxy import cleanup_request # Import here to ensure it's the one from the app

    # Case 1: g.api_response exists and has a close method
    mock_g_with_response = MagicMock()
    mock_api_response_closable = MagicMock()
    mock_api_response_closable.close = MagicMock()
    mock_g_with_response.api_response = mock_api_response_closable
    
    with patch('cot_proxy.g', mock_g_with_response):
        cleanup_request()
        mock_api_response_closable.close.assert_called_once()

    # Case 2: g.api_response exists but does not have a close method (should not happen with requests.Response)
    # This case is less critical as requests.Response always has close.
    # For robustness, if it didn't have close, hasattr would be false for g.api_response.close.
    # The current cleanup_request checks hasattr(g, 'api_response') first.

    # Case 3: g does not have api_response attribute
    mock_g_without_response = MagicMock()
    # Ensure 'api_response' is not an attribute. If MagicMock creates it on access, delete it.
    if hasattr(mock_g_without_response, 'api_response'):
        del mock_g_without_response.api_response
    
    # Create a fresh mock for the close method to check it's not called
    another_mock_close = MagicMock()
    mock_g_with_response.api_response.close = another_mock_close # Reassign to a fresh mock

    with patch('cot_proxy.g', mock_g_without_response):
        cleanup_request()
        another_mock_close.assert_not_called() # Ensure the close method from previous mock isn't called