import pytest
import os
import json
import responses
from unittest.mock import patch

# Assuming cot_proxy.py defines these defaults if env vars are not set
DEFAULT_GLOBAL_START_TAG_IN_CODE = '<think>'
DEFAULT_GLOBAL_END_TAG_IN_CODE = '</think>'

@responses.activate
def test_no_llm_params_no_model_in_request(client, mocker, caplog):
    """
    Test behavior when LLM_PARAMS is not set and no model is in the request.
    Uses default think tags, no parameter overrides.
    """
    mocked_target_base = "http://fake-target/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {}, clear=True) 
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', DEFAULT_GLOBAL_START_TAG_IN_CODE) # Ensure code defaults are used
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', DEFAULT_GLOBAL_END_TAG_IN_CODE)

    request_payload_to_target = None
    def request_callback(request):
        nonlocal request_payload_to_target
        request_payload_to_target = json.loads(request.body)
        return (200, {}, json.dumps({"id": "fake_response"}))

    responses.add_callback(
        responses.POST, f"{mocked_target_base}v1/chat/completions",
        callback=request_callback,
        content_type="application/json",
    )

    initial_request_body = {"messages": [{"role": "user", "content": "Hello"}]}
    response = client.post("/v1/chat/completions", json=initial_request_body)
    assert response.status_code == 200
    
    assert request_payload_to_target is not None
    assert request_payload_to_target == initial_request_body 
    assert f"Using think tags for model 'default': START='{DEFAULT_GLOBAL_START_TAG_IN_CODE}', END='{DEFAULT_GLOBAL_END_TAG_IN_CODE}'" in caplog.text


@responses.activate
def test_llm_params_default_model_config_no_model_in_request(client, mocker, caplog):
    """
    Test LLM_PARAMS with a 'default' model config, no model in request.
    Overrides should apply, 'default' think tags used.
    """
    mocked_target_base = "http://fake-target/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {
        "LLM_PARAMS": "model=default,temperature=0.5,think_tag_start=<dt>,think_tag_end=</dt>",
    }, clear=True) 
    # No need to patch cot_proxy.DEFAULT_THINK_START/END_TAG here as LLM_PARAMS should override

    request_payload_to_target = None
    def request_callback(request):
        nonlocal request_payload_to_target
        request_payload_to_target = json.loads(request.body)
        return (200, {}, json.dumps({"id": "fake_response"}))
    responses.add_callback(responses.POST, f"{mocked_target_base}v1/chat/completions", callback=request_callback)

    initial_request_body = {"messages": [{"role": "user", "content": "Hello"}]} # No model in request
    response = client.post("/v1/chat/completions", json=initial_request_body)
    assert response.status_code == 200
    
    assert request_payload_to_target is not None
    assert request_payload_to_target["temperature"] == 0.5
    assert "think_tag_start" not in request_payload_to_target
    assert "think_tag_end" not in request_payload_to_target
    
    assert "Using think tags for model 'default': START='<dt>', END='</dt>'" in caplog.text


@responses.activate
def test_llm_params_specific_model_match(client, mocker, caplog):
    """
    Test LLM_PARAMS with a specific model config that matches the request.
    Overrides and specific think tags should apply.
    """
    mocked_target_base = "http://fake-target/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {
        "LLM_PARAMS": "model=gpt-4,temperature=0.9,top_k=50,think_tag_start=<gpt4_s>,think_tag_end=</gpt4_e>",
        "THINK_TAG": "<global_s>", 
        "THINK_END_TAG": "</global_e>",
    }, clear=True)
    # No need to patch cot_proxy.DEFAULT_THINK_START/END_TAG as LLM_PARAMS model-specific should override

    request_payload_to_target = None
    def request_callback(request):
        nonlocal request_payload_to_target
        request_payload_to_target = json.loads(request.body)
        return (200, {}, json.dumps({"id": "fake_response"}))
    responses.add_callback(responses.POST, f"{mocked_target_base}v1/chat/completions", callback=request_callback)

    initial_request_body = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello gpt-4"}]}
    response = client.post("/v1/chat/completions", json=initial_request_body)
    assert response.status_code == 200
    
    assert request_payload_to_target is not None
    assert request_payload_to_target["model"] == "gpt-4"
    assert request_payload_to_target["temperature"] == 0.9
    assert request_payload_to_target["top_k"] == 50
    
    assert "Using think tags for model 'gpt-4': START='<gpt4_s>', END='</gpt4_e>'" in caplog.text

@responses.activate
def test_llm_params_specific_model_no_match_uses_global_tags(client, mocker, caplog):
    """
    Test LLM_PARAMS with a specific model config, but request model doesn't match.
    No overrides should apply. Global think tags (from THINK_TAG env var) should be used.
    """
    mocked_target_base = "http://fake-target/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    
    global_env_start = "<global_s_env>"
    global_env_end = "</global_e_env>"
    
    mocker.patch.dict(os.environ, {
        "LLM_PARAMS": "model=gpt-4,temperature=0.9", 
        "THINK_TAG": global_env_start,
        "THINK_END_TAG": global_env_end,
    }, clear=True)
    # Patch module-level defaults so the THINK_TAG env vars are picked up by cot_proxy.py
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', global_env_start)
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', global_env_end)

    request_payload_to_target = None
    def request_callback(request):
        nonlocal request_payload_to_target
        request_payload_to_target = json.loads(request.body)
        return (200, {}, json.dumps({"id": "fake_response"}))
    responses.add_callback(responses.POST, f"{mocked_target_base}v1/chat/completions", callback=request_callback)

    initial_request_body = {"model": "claude-3", "messages": [{"role": "user", "content": "Hello claude"}]}
    response = client.post("/v1/chat/completions", json=initial_request_body)
    assert response.status_code == 200
    
    assert request_payload_to_target is not None
    assert request_payload_to_target["model"] == "claude-3"
    assert "temperature" not in request_payload_to_target 
    
    assert f"Using think tags for model 'claude-3': START='{global_env_start}', END='{global_env_end}'" in caplog.text


@responses.activate
def test_llm_params_model_specific_tags_override_global_env_tags(client, mocker, caplog):
    """
    Test that model-specific think_tags in LLM_PARAMS override global THINK_TAG/THINK_END_TAG env vars.
    """
    mocked_target_base = "http://fake-target/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {
        "LLM_PARAMS": "model=my-model,think_tag_start=<model_s>,think_tag_end=</model_e>",
        "THINK_TAG": "<global_env_s>", # These should be ignored due to model-specific ones
        "THINK_END_TAG": "</global_env_e>",
    }, clear=True)
    # Patch module-level defaults to ensure they are not used
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', "<should_be_overridden_by_env>")
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', "<should_be_overridden_by_env>")


    request_payload_to_target = None 
    def request_callback(request):
        nonlocal request_payload_to_target
        request_payload_to_target = json.loads(request.body)
        return (200, {}, json.dumps({"id": "fake_response"}))
    responses.add_callback(responses.POST, f"{mocked_target_base}v1/chat/completions", callback=request_callback)

    initial_request_body = {"model": "my-model", "messages": [{"role": "user", "content": "Hello"}]}
    client.post("/v1/chat/completions", json=initial_request_body)
    
    assert "Using think tags for model 'my-model': START='<model_s>', END='</model_e>'" in caplog.text

@responses.activate
def test_llm_params_no_model_specific_tags_uses_global_env_tags(client, mocker, caplog):
    """
    Test that if LLM_PARAMS for a model has no think_tags, global THINK_TAG/THINK_END_TAG env vars are used.
    """
    mocked_target_base = "http://fake-target/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    
    global_env_start_active = "<global_env_s_active>"
    global_env_end_active = "</global_env_e_active>"

    mocker.patch.dict(os.environ, {
        "LLM_PARAMS": "model=my-model,temperature=0.1", 
        "THINK_TAG": global_env_start_active,
        "THINK_END_TAG": global_env_end_active,
    }, clear=True)
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', global_env_start_active)
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', global_env_end_active)
    
    request_payload_to_target = None
    def request_callback(request):
        nonlocal request_payload_to_target
        request_payload_to_target = json.loads(request.body)
        return (200, {}, json.dumps({"id": "fake_response"}))
    responses.add_callback(responses.POST, f"{mocked_target_base}v1/chat/completions", callback=request_callback)

    initial_request_body = {"model": "my-model", "messages": [{"role": "user", "content": "Hello"}]}
    client.post("/v1/chat/completions", json=initial_request_body)
    
    assert request_payload_to_target["temperature"] == 0.1
    assert f"Using think tags for model 'my-model': START='{global_env_start_active}', END='{global_env_end_active}'" in caplog.text

@responses.activate
def test_llm_params_no_model_specific_or_global_env_tags_uses_code_defaults(client, mocker, caplog):
    """
    Test that if no model-specific tags in LLM_PARAMS and no global THINK_TAG env vars,
    then the hardcoded defaults in cot_proxy.py are used.
    """
    mocked_target_base = "http://fake-target/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {
        "LLM_PARAMS": "model=my-model,temperature=0.2", 
    }, clear=True) # THINK_TAG and THINK_END_TAG are NOT set in os.environ
    # Ensure module defaults are the code defaults for this test
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', DEFAULT_GLOBAL_START_TAG_IN_CODE)
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', DEFAULT_GLOBAL_END_TAG_IN_CODE)


    request_payload_to_target = None
    def request_callback(request):
        nonlocal request_payload_to_target
        request_payload_to_target = json.loads(request.body)
        return (200, {}, json.dumps({"id": "fake_response"}))
    responses.add_callback(responses.POST, f"{mocked_target_base}v1/chat/completions", callback=request_callback)
    
    initial_request_body = {"model": "my-model", "messages": [{"role": "user", "content": "Hello"}]}
    client.post("/v1/chat/completions", json=initial_request_body)
    
    assert request_payload_to_target["temperature"] == 0.2
    expected_log = f"Using think tags for model 'my-model': START='{DEFAULT_GLOBAL_START_TAG_IN_CODE}', END='{DEFAULT_GLOBAL_END_TAG_IN_CODE}'"
    assert expected_log in caplog.text

@responses.activate
def test_malformed_llm_params_entry_is_skipped(client, mocker, caplog):
    """
    Test that malformed entries in LLM_PARAMS are skipped and valid ones are processed.
    """
    mocked_target_base = "http://fake-target/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {
        "LLM_PARAMS": "model=gpt-good,temperature=0.77;malformed_entry;model=claude-good,top_p=0.88,think_tag_start=<claude_s>,think_tag_end=</claude_e>",
    }, clear=True)
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', DEFAULT_GLOBAL_START_TAG_IN_CODE)
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', DEFAULT_GLOBAL_END_TAG_IN_CODE)

    gpt_payload = None
    claude_payload = None

    def gpt_callback(request):
        nonlocal gpt_payload
        gpt_payload = json.loads(request.body)
        return (200, {}, json.dumps({"id": "gpt_response"}))

    def claude_callback(request):
        nonlocal claude_payload
        claude_payload = json.loads(request.body)
        return (200, {}, json.dumps({"id": "claude_response"}))

    responses.add_callback(responses.POST, f"{mocked_target_base}v1/chat/completions", callback=gpt_callback)
    client.post("/v1/chat/completions", json={"model": "gpt-good", "messages": [{"role": "user", "content": "Hi GPT"}]})
    assert gpt_payload is not None
    assert gpt_payload["temperature"] == 0.77
    # gpt-good has no specific think tags in LLM_PARAMS, so it uses global defaults (which we ensured are code defaults)
    assert f"Using think tags for model 'gpt-good': START='{DEFAULT_GLOBAL_START_TAG_IN_CODE}', END='{DEFAULT_GLOBAL_END_TAG_IN_CODE}'" in caplog.text
    
    responses.reset() # Important: clear responses before adding new callback for the same URL pattern
    caplog.clear()
    responses.add_callback(responses.POST, f"{mocked_target_base}v1/chat/completions", callback=claude_callback)
    client.post("/v1/chat/completions", json={"model": "claude-good", "messages": [{"role": "user", "content": "Hi Claude"}]})
    assert claude_payload is not None
    assert claude_payload["top_p"] == 0.88
    assert "Using think tags for model 'claude-good': START='<claude_s>', END='</claude_e>'" in caplog.text

@responses.activate 
def test_llm_params_not_set_no_json_body(client, mocker, caplog):
    """Test proxy behavior when LLM_PARAMS is not set and request has no JSON body."""
    mocked_target_base = "http://fake-target/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {}, clear=True) 
    mocker.patch('cot_proxy.DEFAULT_THINK_START_TAG', DEFAULT_GLOBAL_START_TAG_IN_CODE)
    mocker.patch('cot_proxy.DEFAULT_THINK_END_TAG', DEFAULT_GLOBAL_END_TAG_IN_CODE)
    
    mocked_get_path = f"{mocked_target_base}v1/some/get_endpoint"
    responses.add(responses.GET, mocked_get_path, body="GET OK", status=200)

    response = client.get("/v1/some/get_endpoint") 
    assert response.status_code == 200
    assert response.data == b"GET OK"
        
    assert "Applying LLM parameters for model" not in caplog.text
    # Log for default think tags is expected as effective_think_tags are initialized
    assert f"Using think tags for model 'default': START='{DEFAULT_GLOBAL_START_TAG_IN_CODE}', END='{DEFAULT_GLOBAL_END_TAG_IN_CODE}'" in caplog.text
    assert "No specific LLM_PARAMS configuration found for model" not in caplog.text 
    
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == mocked_get_path