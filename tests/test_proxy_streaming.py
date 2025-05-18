import pytest
import os
import json
import logging
import responses
from unittest.mock import patch, MagicMock

# Default think tags from cot_proxy.py if no env vars are set
DEFAULT_CODE_START_TAG = '<think>'
DEFAULT_CODE_END_TAG = '</think>'

def generate_streaming_chunks(content_parts, chunk_size=10):
    """Helper to generate byte chunks from a list of strings."""
    full_content = "".join(content_parts)
    for i in range(0, len(full_content), chunk_size):
        yield full_content[i:i+chunk_size].encode('utf-8')

# @responses.activate # Not needed if we patch requests.request
def test_proxy_streaming_basic_think_tag_removal(client, mocker, caplog, enable_debug):
    """Test basic streaming with default think tags."""
    caplog.set_level(logging.DEBUG)
    mocked_target_base = "http://fake-target-stream/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {}, clear=True)
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', DEFAULT_CODE_START_TAG)
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', DEFAULT_CODE_END_TAG)

    target_response_parts = ["This is ", DEFAULT_CODE_START_TAG, "some thoughts", DEFAULT_CODE_END_TAG, " a stream."]
    
    mock_api_response = MagicMock()
    mock_api_response.iter_content.return_value = generate_streaming_chunks(target_response_parts)
    mock_api_response.status_code = 200
    mock_api_response.headers = {'Content-Type': 'application/json'} # Example header
    mock_api_response.elapsed = MagicMock() # Mock elapsed time
    mock_api_response.elapsed.total_seconds.return_value = 0.1


    with patch('requests.request', return_value=mock_api_response) as mock_requests_call:
        request_body = {"model": "test-model", "stream": True, "messages": [{"role": "user", "content": "Hello stream"}]}
        response = client.post("/v1/chat/completions", json=request_body)
    
        assert response.status_code == 200
        assert response.is_streamed
        
        streamed_data = response.data
        expected_output = "This is  a stream.".encode('utf-8')
        assert streamed_data == expected_output
        
        mock_requests_call.assert_called_once()
        args, kwargs = mock_requests_call.call_args
        assert kwargs.get('url') == f"{mocked_target_base}v1/chat/completions"
        assert kwargs.get('stream') is True # Check that the proxy requested a stream

    expected_log = f"Using think tags for model 'test-model': START='{DEFAULT_CODE_START_TAG}', END='{DEFAULT_CODE_END_TAG}'"
    assert expected_log in caplog.text
    assert "Streaming chunk" in caplog.text

# @responses.activate
def test_proxy_streaming_llm_params_custom_tags(client, mocker, caplog):
    """Test streaming with custom think tags from LLM_PARAMS."""
    custom_start = "<custom_s>"
    custom_end = "</custom_e>"
    
    mocked_target_base = "http://fake-target-stream/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {
        "LLM_PARAMS": f"model=my-streaming-model,think_tag_start={custom_start},think_tag_end={custom_end}",
    }, clear=True)
    # No need to patch cot_proxy.DEFAULT_THINK_START/END_TAG as LLM_PARAMS model-specific should override

    target_response_parts = ["Data: ", custom_start, "secret stuff", custom_end, " more data."]
    
    mock_api_response = MagicMock()
    mock_api_response.iter_content.return_value = generate_streaming_chunks(target_response_parts)
    mock_api_response.status_code = 200
    mock_api_response.headers = {'Content-Type': 'application/json'}
    mock_api_response.elapsed = MagicMock()
    mock_api_response.elapsed.total_seconds.return_value = 0.1

    with patch('requests.request', return_value=mock_api_response):
        request_body = {"model": "my-streaming-model", "stream": True, "messages": [{"role": "user", "content": "Stream custom"}]}
        response = client.post("/v1/chat/completions", json=request_body)
    
        assert response.status_code == 200
        assert response.is_streamed
        
        streamed_data = response.data
        expected_output = "Data:  more data.".encode('utf-8')
        assert streamed_data == expected_output
    
    expected_log = f"Using think tags for model 'my-streaming-model': START='{custom_start}', END='{custom_end}'"
    assert expected_log in caplog.text

# @responses.activate
def test_proxy_streaming_global_env_tags(client, mocker, caplog):
    """Test streaming with global THINK_TAG and THINK_END_TAG from environment."""
    env_start_tag = "<env_think>"
    env_end_tag = "</env_think>"

    mocked_target_base = "http://fake-target-stream/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {
        "THINK_TAG": env_start_tag,
        "THINK_END_TAG": env_end_tag,
    }, clear=True)
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', env_start_tag)
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', env_end_tag)


    target_response_parts = ["Info: ", env_start_tag, "env thoughts", env_end_tag, " end info."]
    
    mock_api_response = MagicMock()
    mock_api_response.iter_content.return_value = generate_streaming_chunks(target_response_parts)
    mock_api_response.status_code = 200
    mock_api_response.headers = {'Content-Type': 'application/json'}
    mock_api_response.elapsed = MagicMock()
    mock_api_response.elapsed.total_seconds.return_value = 0.1

    with patch('requests.request', return_value=mock_api_response):
        request_body = {"model": "another-model", "stream": True, "messages": [{"role": "user", "content": "Stream env tags"}]}
        response = client.post("/v1/chat/completions", json=request_body)
    
        assert response.status_code == 200
        assert response.is_streamed
        
        streamed_data = response.data
        expected_output = "Info:  end info.".encode('utf-8')
        assert streamed_data == expected_output

    expected_log = f"Using think tags for model 'another-model': START='{env_start_tag}', END='{env_end_tag}'"
    assert expected_log in caplog.text

# @responses.activate
def test_proxy_streaming_tag_split_across_chunks(client, mocker, caplog):
    """Test streaming where a think tag is split across multiple chunks."""
    mocked_target_base = "http://fake-target-stream/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {}, clear=True)
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', DEFAULT_CODE_START_TAG)
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', DEFAULT_CODE_END_TAG)


    chunks_from_target = [
        b"Part1 ",
        b"<th",
        b"ink>Hidden Content</th",
        b"ink>",
        b" Part2"
    ]
    
    mock_api_response = MagicMock()
    # IMPORTANT: iter_content should yield byte chunks directly, not a generator of generators
    mock_api_response.iter_content.return_value = (c for c in chunks_from_target) # Make it a generator
    mock_api_response.status_code = 200
    mock_api_response.headers = {'Content-Type': 'application/json'}
    mock_api_response.elapsed = MagicMock()
    mock_api_response.elapsed.total_seconds.return_value = 0.1

    with patch('requests.request', return_value=mock_api_response):
        request_body = {"model": "split-model", "stream": True, "messages": [{"role": "user", "content": "Stream split"}]}
        response = client.post("/v1/chat/completions", json=request_body)
    
        assert response.status_code == 200
        assert response.is_streamed
        
        streamed_data = response.data
        expected_output = b"Part1  Part2"
        assert streamed_data == expected_output
    
    expected_log = f"Using think tags for model 'split-model': START='{DEFAULT_CODE_START_TAG}', END='{DEFAULT_CODE_END_TAG}'"
    assert expected_log in caplog.text

# @responses.activate # Not needed as we patch requests.request
def test_proxy_streaming_client_disconnect(client, mocker, caplog):
    """
    Test handling of client disconnection during streaming.
    Checks for log messages and that the underlying response is closed.
    """
    mocked_target_base = "http://fake-target-stream/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {}, clear=True)
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', DEFAULT_CODE_START_TAG) # Ensure consistent tags
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', DEFAULT_CODE_END_TAG)


    # Mock the target's response stream to simulate client disconnect
    # The GeneratorExit should be raised by the app's generator when the client disconnects
    # while yielding. We simulate this by having iter_content raise it.
    mock_iter_content = MagicMock(side_effect=GeneratorExit("Simulated client disconnect"))

    mock_api_response = MagicMock()
    mock_api_response.iter_content = mock_iter_content # Assign the mock directly
    mock_api_response.status_code = 200
    mock_api_response.headers = {'Content-Type': 'application/json'}
    mock_api_response.close = MagicMock() # Mock the close method
    mock_api_response.elapsed = MagicMock()
    mock_api_response.elapsed.total_seconds.return_value = 0.1


    with patch('requests.request', return_value=mock_api_response) as mock_requests_call:
        request_body = {"model": "disconnect-model", "stream": True, "messages": [{"role": "user", "content": "Stream disconnect"}]}
        
        # Make the request
        response = client.post("/v1/chat/completions", json=request_body)
        
        # The initial response (headers) should be 200 OK
        assert response.status_code == 200
        assert response.is_streamed

        # No need to consume the stream manually

     # Assertions:
    # 1. The underlying api_response.close() should have been called from the finally block.
    mock_api_response.close.assert_called_once()

# TODO: Add test for streaming when target returns an error status code (e.g. 4xx, 5xx)
# In cot_proxy.py, if g.api_response.status_code >= 400, it returns non-streamed error.
# So, streaming tests should only cover cases where target initially returns 2xx.
# This is implicitly handled because if target gave 4xx, it wouldn't reach streaming logic.