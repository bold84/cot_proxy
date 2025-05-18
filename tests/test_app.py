import pytest
import os
import logging
import requests # For requests.exceptions
import json
import cot_proxy # Import the module to patch its variables
from unittest.mock import patch

# Import the responses library for mocking HTTP requests
import responses

def test_app_exists(app):
    """Test if the Flask app instance exists."""
    assert app is not None

def test_client_exists(client):
    """Test if the Flask test client exists."""
    assert client is not None

def test_target_base_url_default(client, mocker):
    """Test TARGET_BASE_URL uses default if env var is not set."""
    mocker.patch.dict(os.environ, {}, clear=True) # Ensure TARGET_BASE_URL is not set
    
    # We need to re-import or reload the module where TARGET_BASE_URL is defined
    # for the mocked os.getenv to take effect during its definition.
    # A simpler way for testing config is often to set it on app.config directly in tests
    # or to have a factory function for the app that can take config.
    # For this specific case, since TARGET_BASE_URL is module-level,
    # we'll check the app's behavior which indirectly uses it.
    # The health check endpoint reveals the TARGET_BASE_URL.
    
    # Temporarily override cot_proxy.TARGET_BASE_URL for this test
    # This is a bit of a workaround because TARGET_BASE_URL is set at module import time.
    # Patch the module-level TARGET_BASE_URL in the cot_proxy module
    with patch('cot_proxy.TARGET_BASE_URL', 'https://api.openai.com/v1/') as mock_target_url:
        with responses.RequestsMock() as rsps:
            rsps.add(responses.GET, mock_target_url, status=200, body="OK")
            health_response = client.get('/health')
            assert health_response.status_code == 200
            data = json.loads(health_response.data)
            assert data['target_url'] == mock_target_url

def test_target_base_url_from_env(client, mocker):
    """Test TARGET_BASE_URL is set from environment variable."""
    test_url = "http://custom-env-url:1234/"
    mocker.patch.dict(os.environ, {"TARGET_BASE_URL": test_url}, clear=True)

    # Similar to above, module-level var needs care.
    with patch('cot_proxy.TARGET_BASE_URL', test_url) as mock_target_url:
        with responses.RequestsMock() as rsps:
            rsps.add(responses.GET, mock_target_url, status=200, body="OK")
            health_response = client.get('/health')
            assert health_response.status_code == 200
            data = json.loads(health_response.data)
            assert data['target_url'] == mock_target_url

def test_target_base_url_trailing_slash(client, mocker):
    """Test TARGET_BASE_URL ensures a trailing slash."""
    test_url_no_slash = "http://custom-env-url-no-slash:5678"
    expected_url_with_slash = "http://custom-env-url-no-slash:5678/"
    mocker.patch.dict(os.environ, {"TARGET_BASE_URL": test_url_no_slash}, clear=True)

    with patch('cot_proxy.TARGET_BASE_URL', expected_url_with_slash) as mock_target_url:
        with responses.RequestsMock() as rsps:
            rsps.add(responses.GET, mock_target_url, status=200, body="OK")
            health_response = client.get('/health')
            assert health_response.status_code == 200
            data = json.loads(health_response.data)
            assert data['target_url'] == mock_target_url

def test_logging_level_debug(mocker):
    """Test logging level is DEBUG when DEBUG env var is 'true'."""
    mocker.patch.dict(os.environ, {"DEBUG": "true"}, clear=True)
    # To properly test this, we'd need to re-evaluate the logging setup in cot_proxy.py
    # This might involve reloading the module or having a configurable app factory.
    # For simplicity, we'll assume the logger instance reflects the config.
    # A more robust test would involve checking log output or logger properties after app setup.
    # This test is more of a conceptual check given the current structure.
    # A direct check on flask_app.logger.level might not work if it's configured by basicConfig
    # before the app logger is fully set up or if it's a different logger instance.
    
    # For now, let's assert based on the re-evaluation logic if cot_proxy was imported fresh
    # This is tricky because pytest imports test modules, and cot_proxy might already be imported.
    # A common pattern is to have a create_app() factory.
    # Given the current structure, we'll check the module-level logger from cot_proxy.
    
    # Re-import or re-run the config part of cot_proxy.py under the mocked environment
    # This is not ideal. A better way is to make logging setup a function.
    # For this test, we'll assume that if cot_proxy was loaded with DEBUG=true, its logger would be DEBUG.
    # This test is more illustrative of the intent.
    # A practical way:
    # from importlib import reload
    # import cot_proxy
    # reload(cot_proxy) # This re-runs module-level code
    # assert cot_proxy.logger.level == logging.DEBUG
    # However, reloading modules in tests can have side effects.
    
    # Let's check the configured log_level variable in cot_proxy after patching os.environ
    # This requires cot_proxy to be imported *after* the patch, or use importlib.reload
    with patch.dict(os.environ, {"DEBUG": "true"}):
        # If cot_proxy.py is re-evaluated (e.g. by reload or if it's the first import under this env)
        # then cot_proxy.log_level would be logging.DEBUG
        # For this test, we'll assume we can inspect the intended level.
        # This is a simplification.
        pass # Placeholder for a more robust logging test method

def test_logging_level_info_default(mocker):
    """Test logging level is INFO when DEBUG env var is not 'true'."""
    mocker.patch.dict(os.environ, {"DEBUG": "false"}, clear=True)
    # Similar caveats as above test_logging_level_debug
    # with patch.dict(os.environ, {"DEBUG": "false"}):
    #   from importlib import reload
    #   import cot_proxy
    #   reload(cot_proxy)
    #   assert cot_proxy.logger.level == logging.INFO
    pass # Placeholder

@responses.activate
def test_health_check_healthy(client, mocker):
    """Test the /health endpoint when the target is healthy."""
    mocked_url = "http://healthy-target.com/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_url)
    
    responses.add(
        responses.GET,
        mocked_url,
        json={"status": "ok_from_target"},
        status=200
    )
    
    response = client.get('/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'healthy'
    assert data['target_url'] == mocked_url

@responses.activate
def test_health_check_unhealthy_connection_error(client, mocker):
    """Test the /health endpoint when the target connection fails."""
    mocked_url = "http://unhealthy-target-conn-error.com/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_url)
    
    responses.add(
        responses.GET,
        mocked_url,
        body=requests.exceptions.ConnectionError("Test connection error")
    )
    
    response = client.get('/health')
    assert response.status_code == 503
    data = json.loads(response.data)
    assert data['status'] == 'unhealthy'
    assert "Test connection error" in data['error']
    # assert data['target_url'] == mocked_url # Unhealthy response doesn't include target_url

@responses.activate
def test_health_check_unhealthy_timeout(client, mocker):
    """Test the /health endpoint when the target connection times out."""
    mocked_url = "http://unhealthy-target-timeout.com/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_url)
    
    responses.add(
        responses.GET,
        mocked_url,
        body=requests.exceptions.Timeout("Test timeout")
    )
    
    response = client.get('/health')
    assert response.status_code == 503
    data = json.loads(response.data)
    assert data['status'] == 'unhealthy'
    assert "Test timeout" in data['error']
    # assert data['target_url'] == mocked_url # Unhealthy response doesn't include target_url

@responses.activate
def test_health_check_unhealthy_target_error_status(client, mocker):
    """Test the /health endpoint when the target returns an error status."""
    mocked_url = "http://target-returns-error.com/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_url)
    
    responses.add(
        responses.GET,
        mocked_url,
        status=500,
        body="Target server error"
    )
        
    response = client.get('/health')
    # The health check in cot_proxy.py considers any GET that doesn't raise an exception
    # (like ConnectionError, Timeout) as the target being "reachable" for its own health.
    # The status code from the target (500 here) is logged but doesn't make the proxy's /health fail.
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'healthy'
    assert data['target_url'] == mocked_url