import pytest
import os
import json
import logging
import responses
from unittest.mock import patch

# Default think tags from cot_proxy.py if no env vars are set
DEFAULT_CODE_START_TAG = '<think>'
DEFAULT_CODE_END_TAG = '</think>'

@responses.activate
def test_proxy_non_streaming_basic_get(client, mocker):
    """Test basic non-streaming GET request forwarding."""
    mocked_target_base = "http://fake-target-nonstream/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {}, clear=True) # Clear env var so patched module var is used

    target_response_content = {"message": "GET success"}
    responses.add(
        responses.GET,
        f"{mocked_target_base}some/path?param1=value1",
        json=target_response_content,
        status=200,
        headers={"X-Custom-Header": "TargetValue"}
    )

    proxy_response = client.get("/some/path?param1=value1", headers={"X-Client-Header": "ClientValue"})

    assert proxy_response.status_code == 200
    assert proxy_response.json == target_response_content
    assert proxy_response.headers.get("X-Custom-Header") == "TargetValue"
    # Content-Length might be different due to Flask test client or re-encoding, so usually not asserted directly unless critical.
    
    # Verify that the request to the target was made correctly
    assert len(responses.calls) == 1
    call = responses.calls[0]
    assert call.request.method == "GET"
    assert call.request.url == f"{mocked_target_base}some/path?param1=value1"
    assert call.request.headers.get("X-Client-Header") == "ClientValue"
    assert "Host" not in call.request.headers # Host header should be excluded

@responses.activate
def test_proxy_non_streaming_post_json_body(client, mocker):
    """Test non-streaming POST request with JSON body forwarding."""
    mocked_target_base = "http://fake-target-nonstream/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {}, clear=True)

    request_json_body = {"data": "sample_post_data", "model": "test-post-model"}
    target_response_content = {"reply": "POST received"}

    # This will hold the JSON body received by the mocked target
    payload_to_target = None
    def request_callback(request):
        nonlocal payload_to_target
        payload_to_target = json.loads(request.body)
        return (200, {}, json.dumps(target_response_content))

    responses.add_callback(
        responses.POST,
        f"{mocked_target_base}v1/post/endpoint",
        callback=request_callback,
        content_type="application/json"
    )

    proxy_response = client.post("/v1/post/endpoint", json=request_json_body)

    assert proxy_response.status_code == 200
    assert proxy_response.json == target_response_content
    assert payload_to_target is not None
    assert payload_to_target == request_json_body


@responses.activate
def test_proxy_non_streaming_think_tag_removal_default_tags(client, mocker, caplog, enable_debug):
    """Test non-streaming think tag removal with default code tags."""
    caplog.set_level(logging.DEBUG)
    mocked_target_base = "http://fake-target-nonstream/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {
        "LLM_PARAMS": "model=nonstream-model,enable_think_tag_filtering=true"
    }, clear=True)
    # Ensure module defaults are the code defaults for this test
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', DEFAULT_CODE_START_TAG)
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', DEFAULT_CODE_END_TAG)

    raw_content_from_target = f"Visible {DEFAULT_CODE_START_TAG}secret thoughts{DEFAULT_CODE_END_TAG} content."
    responses.add(
        responses.POST,
        f"{mocked_target_base}v1/chat/completions",
        body=raw_content_from_target,
        status=200,
        content_type="application/json"
    )

    request_body = {"model": "nonstream-model", "stream": False, "messages": [{"role": "user", "content": "Hello"}]}
    proxy_response = client.post("/v1/chat/completions", json=request_body)

    assert proxy_response.status_code == 200
    assert proxy_response.data.decode('utf-8') == "Visible  content."
    
    expected_log = f"Using think tags for model 'nonstream-model': START='{DEFAULT_CODE_START_TAG}', END='{DEFAULT_CODE_END_TAG}'"
    assert expected_log in caplog.text
    assert "Non-streaming response content: Visible  content." in caplog.text
    

@responses.activate
def test_proxy_non_streaming_think_tag_removal_llm_params_tags(client, mocker, caplog):
    """Test non-streaming think tag removal with tags from LLM_PARAMS."""
    custom_start = "<llm_s>"
    custom_end = "</llm_e>"
    mocked_target_base = "http://fake-target-nonstream/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {
        "LLM_PARAMS": f"model=llm-param-model,think_tag_start={custom_start},think_tag_end={custom_end},enable_think_tag_filtering=true",
    }, clear=True)

    raw_content_from_target = f"Data {custom_start}hidden{custom_end} visible."
    responses.add(
        responses.POST,
        f"{mocked_target_base}v1/chat/completions",
        body=raw_content_from_target,
        status=200,
        content_type="application/json"
    )

    request_body = {"model": "llm-param-model", "stream": False, "messages": [{"role": "user", "content": "Hello"}]}
    proxy_response = client.post("/v1/chat/completions", json=request_body)

    assert proxy_response.status_code == 200
    assert proxy_response.data.decode('utf-8') == "Data  visible."
    expected_log = f"Using think tags for model 'llm-param-model': START='{custom_start}', END='{custom_end}'"
    assert expected_log in caplog.text

@responses.activate
def test_proxy_non_streaming_think_tag_removal_global_env_tags(client, mocker, caplog):
    """Test non-streaming think tag removal with global THINK_TAG/THINK_END_TAG."""
    env_start = "<env_s>"
    env_end = "</env_e>"
    mocked_target_base = "http://fake-target-nonstream/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {
        "THINK_TAG": env_start,
        "THINK_END_TAG": env_end,
        "LLM_PARAMS": "model=global-env-model,enable_think_tag_filtering=true"
    }, clear=True)
    # Patch module-level defaults so the THINK_TAG env vars are picked up
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', env_start)
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', env_end)

    raw_content_from_target = f"Prefix {env_start}thoughts{env_end} Suffix."
    responses.add(
        responses.POST,
        f"{mocked_target_base}v1/chat/completions",
        body=raw_content_from_target,
        status=200,
        content_type="application/json"
    )

    request_body = {"model": "global-env-model", "stream": False, "messages": [{"role": "user", "content": "Hello"}]}
    proxy_response = client.post("/v1/chat/completions", json=request_body)

    assert proxy_response.status_code == 200
    assert proxy_response.data.decode('utf-8') == "Prefix  Suffix."
    expected_log = f"Using think tags for model 'global-env-model': START='{env_start}', END='{env_end}'"
    assert expected_log in caplog.text

@responses.activate
def test_proxy_non_streaming_no_stream_key_in_request(client, mocker, caplog, enable_debug):
    """Test non-streaming path is taken if 'stream' key is absent in JSON body."""
    caplog.set_level(logging.DEBUG)
    mocked_target_base = "http://fake-target-nonstream/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {
        "LLM_PARAMS": "model=no-stream-key-model,enable_think_tag_filtering=true"
    }, clear=True)
    # Ensure module defaults are the code defaults for this test
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', DEFAULT_CODE_START_TAG)
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', DEFAULT_CODE_END_TAG)

    raw_content_from_target = f"Content {DEFAULT_CODE_START_TAG}stuff{DEFAULT_CODE_END_TAG} end."
    responses.add(
        responses.POST,
        f"{mocked_target_base}v1/chat/completions",
        body=raw_content_from_target,
        status=200,
        content_type="application/json"
    )

    # 'stream' key is missing, should default to non-streaming
    request_body = {"model": "no-stream-key-model", "messages": [{"role": "user", "content": "Hello"}]}
    proxy_response = client.post("/v1/chat/completions", json=request_body)

    assert proxy_response.status_code == 200
    assert proxy_response.data.decode('utf-8') == "Content  end."
    assert "Non-streaming response content:" in caplog.text # Confirms non-streaming path
    # Stream mode log should indicate false
    assert "Stream mode: False" in caplog.text


@responses.activate
def test_proxy_non_streaming_no_json_body(client, mocker, caplog, enable_debug):
    """Test non-streaming path when request has no JSON body (e.g., simple GET)."""
    caplog.set_level(logging.DEBUG)
    mocked_target_base = "http://fake-target-nonstream/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {
        "LLM_PARAMS": "model=default,enable_think_tag_filtering=true" # For the second part of the test
    }, clear=True)
    # Ensure module defaults are the code defaults for this test
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', DEFAULT_CODE_START_TAG)
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', DEFAULT_CODE_END_TAG)

    target_response_body = "Simple GET response, no tags involved."
    responses.add(
        responses.GET,
        f"{mocked_target_base}simple/get/path",
        body=target_response_body,
        status=200,
        content_type="text/plain"
    )

    proxy_response = client.get("/simple/get/path")

    assert proxy_response.status_code == 200
    assert proxy_response.data.decode('utf-8') == target_response_body
    assert proxy_response.headers.get("Content-Type") == "text/plain"
    
    # is_stream is determined by json_body.get('stream', False) if json_body else False
    # So if no json_body, is_stream is False.
    assert "Stream mode: False" in caplog.text
    # The non-streaming logic for think tag removal is only hit if json_body was present
    # to determine effective_think_start_tag etc.
    # If no json_body, the proxy function's main try block for requests.request is hit,
    # then it checks g.api_response.status_code. If < 400, it proceeds to the
    # `is_stream` check. If `is_stream` is false (due to no json_body),
    # it decodes g.api_response.content.
    # The `effective_think_start_tag` would be the global defaults in this case.
    # So, if the response *did* contain default tags, they *would* be stripped.
    