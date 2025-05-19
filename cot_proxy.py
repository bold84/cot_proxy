from flask import Flask, request, Response, stream_with_context, g
import requests
import re
import os
import logging
import json
import time
from typing import Any
from urllib.parse import urljoin
import re # Ensure re is available for escaping

# Global default think tags
# Prioritize environment variables, then hardcoded defaults
DEFAULT_THINK_START_TAG = os.getenv('THINK_TAG', '<think>')
DEFAULT_THINK_END_TAG = os.getenv('THINK_END_TAG', '</think>')

# Parameter type definitions
PARAM_TYPES = {
    # Float parameters (0.0 to 1.0 typically)
    'temperature': float,      # Randomness in sampling
    'top_p': float,           # Nucleus sampling threshold
    'presence_penalty': float, # Penalty for token presence
    'frequency_penalty': float,# Penalty for token frequency
    'repetition_penalty': float, # Penalty for repetition
    
    # Integer parameters
    'top_k': int,             # Top-k sampling parameter
    'max_tokens': int,        # Maximum tokens to generate
    'n': int,                 # Number of completions
    'seed': int,              # Random seed for reproducibility
    'num_ctx': int,           # Context window size
    'num_predict': int,       # Number of tokens to predict
    'repeat_last_n': int,     # Context for repetition penalty
    'batch_size': int,        # Batch size for generation
    
    # Boolean parameters
    'echo': bool,             # Whether to echo prompt
    'stream': bool,           # Whether to stream responses
    'mirostat': bool,         # Use Mirostat sampling
}

# Buffer for handling think tags across chunks
class StreamBuffer:
    def __init__(self, start_tag, end_tag):
        self.buffer = ""
        self.start_tag = start_tag
        self.end_tag = end_tag
        
    def process_chunk(self, chunk):
        # Decode and add to buffer
        decoded_chunk = chunk.decode("utf-8", errors="replace")
        self.buffer += decoded_chunk
        
        output = ""
        
        while True:
            # Find the next potential tag start
            start = self.buffer.find(self.start_tag)
            
            if start == -1:
                # No more think tags, output all except last few chars
                if len(self.buffer) > 1024: # Keep some buffer for potential partial tags at the very end
                    output += self.buffer[:-1024]
                    self.buffer = self.buffer[-1024:]
                break
            
            # Output content before the tag
            if start > 0:
                output += self.buffer[:start]
                self.buffer = self.buffer[start:]
                start = 0  # Tag is now at start of buffer
            
            # Look for end tag
            end = self.buffer.find(self.end_tag, start) # Search after the start tag
            if end == -1:
                # No end tag yet, keep in buffer (if buffer isn't excessively large)
                if len(self.buffer) > (len(self.start_tag) + 4096): # Heuristic to prevent runaway buffer with unclosed tags
                    # This case implies a very long segment without an end tag.
                    # We might decide to flush part of it if it's not the start_tag itself.
                    # For now, break and wait for more data or flush.
                    pass # Keep in buffer
                break
            
            # Remove the complete think tag and its content
            end += len(self.end_tag)
            self.buffer = self.buffer[end:]
        
        return output.encode("utf-8") if output else b""
        
    def flush(self):
        # Output remaining content
        output = self.buffer
        self.buffer = ""
        return output.encode("utf-8")

def convert_param_value(key: str, value: str) -> Any:
    """Convert parameter value to appropriate type based on parameter name."""
    if not value or value.lower() == 'null':
        return None
        
    param_type = PARAM_TYPES.get(key)
    if not param_type:
        return value  # Keep as string if not a known numeric param
        
    try:
        if param_type == bool:
            return value.lower() == 'true'
        return param_type(value)
    except (ValueError, TypeError):
        # If conversion fails, log warning and return original string
        logger.warning(f"Failed to convert parameter '{key}' value '{value}' to {param_type.__name__}")
        return value

app = Flask(__name__)

@app.teardown_request
def cleanup_request(exception=None):
    """Ensure proper cleanup of resources when request ends."""
    if hasattr(g, 'api_response'):
        logger.debug("Cleaning up API response in teardown")
        g.api_response.close()

# Configure logging based on DEBUG environment variable
log_level = logging.DEBUG if os.getenv('DEBUG', 'false').lower() == 'true' else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configure target URL
TARGET_BASE_URL = os.getenv('TARGET_BASE_URL', 'https://api.openai.com/v1/')
if not TARGET_BASE_URL.endswith('/'):
    TARGET_BASE_URL += '/'  # Ensure trailing slash for urljoin

logger.debug(f"Starting proxy with target URL: {TARGET_BASE_URL}")
logger.debug(f"Debug mode: {log_level == logging.DEBUG}")

@app.route('/health')
def health_check():
    try:
        # Try to connect to the target URL
        response = requests.get(
            TARGET_BASE_URL,
            timeout=5,
            verify=True
        )
        logger.debug(f"Health check - Target URL: {TARGET_BASE_URL}")
        logger.debug(f"Health check - Status code: {response.status_code}")
        
        return Response(
            response='{"status": "healthy", "target_url": "' + TARGET_BASE_URL + '"}',
            status=200,
            content_type="application/json"
        )
    except Exception as e:
        error_msg = f"Health check failed: {str(e)}"
        logger.error(error_msg)
        return Response(
            response='{"status": "unhealthy", "error": "' + error_msg + '"}',
            status=503,
            content_type="application/json"
        )

@app.route('/', defaults={'path': ''}, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@app.route('/<path:path>', methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
def proxy(path):
    # Construct the target URL dynamically using the base URL and client's path
    target_url = urljoin(TARGET_BASE_URL, path)
    
    # Forward all headers (except "Host" to avoid conflicts)
    headers = {
        key: value 
        for key, value in request.headers 
        if key.lower() != "host"
    }
    
    # Forward query parameters from the original request
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"

    # Log request details
    logger.debug(f"Forwarding {request.method} request to: {target_url}")
    logger.debug(f"Headers: {headers}")
    
    # Initialize effective_think_start_tag and effective_think_end_tag to global defaults
    # These will be used by the streaming/non-streaming response handlers.
    # They might be updated if json_body and LLM_PARAMS are processed.
    effective_think_start_tag = DEFAULT_THINK_START_TAG
    effective_think_end_tag = DEFAULT_THINK_END_TAG
    target_model_for_log = 'default' # For logging if no model in request
    model_specific_config = {}  # Initialize to ensure it's always a dict
    enable_think_tag_filtering = False  # Default to filtering disabled

    try:
        # Get JSON body if present
        json_body = request.get_json(silent=True) if request.is_json else None
        logger.debug(f"Request JSON body: {json_body}")
        
        if json_body:
            target_model_for_log = json_body.get('model', 'default') # Update for logging
            # Apply model-specific LLM parameter overrides from environment
            if llm_params := os.getenv('LLM_PARAMS'):
                # Parse model configurations: "model=MODEL1,param1=val1,param2=val2;model=MODEL2,param3=val3"
                model_configs = {}
                for model_entry in llm_params.split(';'):
                    model_entry = model_entry.strip()
                    if not model_entry or not model_entry.startswith('model='):
                        continue
                    
                    # Split into model declaration and parameters
                    parts = model_entry.split(',')
                    model_name = parts[0].split('=', 1)[1].strip()
                    model_configs[model_name] = {}
                    
                    # Process parameters after model declaration
                    for param in parts[1:]:
                        param = param.strip()
                        if '=' in param:
                            key, value = param.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            if key in ['think_tag_start', 'think_tag_end', 'upstream_model_name', 'append_to_last_user_message']:
                                model_configs[model_name][key] = value  # Store as raw string
                            elif key == 'enable_think_tag_filtering':
                                model_configs[model_name][key] = value.lower() == 'true'
                            else:
                                model_configs[model_name][key] = convert_param_value(key, value)
                
                # Get target model from request (already got for target_model_for_log)
                current_target_model = json_body.get('model')

                if current_target_model and current_target_model in model_configs:
                    model_specific_config = model_configs[current_target_model]
                    effective_think_start_tag = model_specific_config.get('think_tag_start', DEFAULT_THINK_START_TAG)
                    effective_think_end_tag = model_specific_config.get('think_tag_end', DEFAULT_THINK_END_TAG)
                    enable_think_tag_filtering = model_specific_config.get('enable_think_tag_filtering', False) # Default to False if key missing
                    original_model = current_target_model
                    logger.debug(f"Applying LLM parameters for model: {original_model}")

                    # Replace the model in the request body if upstream_model_name is specified
                    if 'upstream_model_name' in model_specific_config:
                        upstream_model = model_specific_config['upstream_model_name']
                        json_body['model'] = upstream_model
                        target_model_for_log = upstream_model
                        logger.info(f"Replacing pseudo model '{original_model}' with upstream model '{upstream_model}'")

                    # Apply other parameters (excluding think tags and upstream_model_name)
                    logger.debug(f"Applying LLM parameters for model: {current_target_model}")
                    for key, value in model_specific_config.items():
                        if key not in ['enable_think_tag_filtering', 'think_tag_start', 'think_tag_end', 'upstream_model_name', 'append_to_last_user_message']:
                            json_body[key] = value
                            logger.debug(f"Overriding LLM parameter: {key} = {value}")

                elif current_target_model: # Model in request, but no specific config in LLM_PARAMS
                    logger.debug(f"No specific LLM_PARAMS configuration found for model: {current_target_model}. Using default think tags.")
                # If no current_target_model in json_body, effective tags remain global defaults.
                # If LLM_PARAMS has a "default" config, it might apply if current_target_model is None
                # and the logic for 'target_model or default' is used for param overrides (currently not for overrides, only for log).
                # The current logic: if json_body.get('model') is None, no specific model_specific_config is found.
                # If a "default" model config exists in LLM_PARAMS and no model is in request,
                # it should ideally pick up "default" config for overrides too.
                # Let's adjust to check for "default" config if no model in request.
                elif "default" in model_configs and not current_target_model:
                    model_specific_config = model_configs["default"]
                    effective_think_start_tag = model_specific_config.get('think_tag_start', DEFAULT_THINK_START_TAG)
                    effective_think_end_tag = model_specific_config.get('think_tag_end', DEFAULT_THINK_END_TAG)
                    enable_think_tag_filtering = model_specific_config.get('enable_think_tag_filtering', False) # Default to False if key missing
                    original_model = 'default (no model in request)'
                    logger.debug(f"Applying LLM parameters for 'default' model configuration (no model in request).")

                    if 'upstream_model_name' in model_specific_config:
                        upstream_model = model_specific_config['upstream_model_name']
                        json_body['model'] = upstream_model
                        target_model_for_log = upstream_model
                        logger.info(f"Using upstream model '{upstream_model}' for default configuration")

                    for key, value in model_specific_config.items():
                        if key not in ['enable_think_tag_filtering', 'think_tag_start', 'think_tag_end', 'upstream_model_name', 'append_to_last_user_message']:
                            json_body[key] = value
                            logger.debug(f"Overriding LLM parameter for 'default': {key} = {value}")

        logger.info(f"Using think tags for model '{target_model_for_log}': START='{effective_think_start_tag}', END='{effective_think_end_tag}'")
        logger.info(f"Think tag filtering enabled: {enable_think_tag_filtering} for model '{target_model_for_log}'")
        
        append_string = model_specific_config.get('append_to_last_user_message')
        if append_string and json_body: # Ensure json_body exists
            if 'messages' not in json_body or not json_body['messages']:
                # No messages: create a new user message with the string
                json_body.setdefault('messages', [])
                json_body['messages'].append({"role": "user", "content": append_string})
                logger.debug(f"Created new user message with content: {append_string}")
            else:
                # Find the last message to append to
                if json_body['messages']: # Ensure messages list is not empty
                    last_message = json_body['messages'][-1]
                    if last_message.get('role') == 'user':
                        if isinstance(last_message.get('content'), str):
                            last_message['content'] += append_string
                            logger.debug(f"Appended to existing user message (string content): {append_string}")
                        elif isinstance(last_message.get('content'), list):
                            content_list = last_message['content']
                            appended_to_existing_text_part = False
                            # Iterate backwards to find the last text part to append to
                            # This handles cases like a list of text and image parts.
                            for i in range(len(content_list) - 1, -1, -1):
                                part = content_list[i]
                                if isinstance(part, dict) and part.get('type') == 'text' and 'text' in part:
                                    part['text'] += append_string
                                    appended_to_existing_text_part = True
                                    logger.debug(f"Appended to last text part of user message content list: {append_string}")
                                    break
                            
                            if not appended_to_existing_text_part:
                                # If no suitable text part was found (e.g. list of images, or empty list),
                                # add a new text part.
                                content_list.append({'type': 'text', 'text': append_string})
                                logger.debug(f"Added new text part to user message content list: {append_string}")
                        else:
                            # Content is not a string or list (e.g., None or unexpected type)
                            # Set the content to the append_string.
                            original_content_type = type(last_message.get('content')).__name__
                            last_message['content'] = append_string
                            logger.warning(f"Last user message content was '{original_content_type}'. Overwritten with new string content: {append_string}")
                    else:
                        # Last message is not user: insert a new user message
                        json_body['messages'].append({"role": "user", "content": append_string})
                        logger.debug(f"Last message not 'user'. Inserted new user message with content: {append_string}")
                else: # messages list is empty
                    json_body['messages'].append({"role": "user", "content": append_string})
                    logger.debug(f"Messages list was empty. Created new user message with content: {append_string}")
        
        # Try to connect with a timeout
        try:
            # Store response in Flask's request context
            g.api_response = requests.request(
                method=request.method,
                url=target_url,
                headers=headers,
                json=json_body,
                stream=True,
                timeout=int(os.getenv('API_REQUEST_TIMEOUT', 120)),  # Timeout in seconds, default 120
                verify=True  # Verify SSL certificates
            )
            logger.debug(f"Connected to target URL: {target_url}")
            logger.debug(f"Target response time: {g.api_response.elapsed.total_seconds()}s")
        except requests.exceptions.Timeout:
            error_msg = f"Connection to {target_url} timed out"
            logger.error(error_msg)
            return Response(
                response='{"error": "' + error_msg + '"}',
                status=504,
                content_type="application/json"
            )
        except requests.exceptions.SSLError as e:
            error_msg = f"SSL verification failed: {str(e)}"
            logger.error(error_msg)
            return Response(
                response='{"error": "' + error_msg + '"}',
                status=502,
                content_type="application/json"
            )
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Failed to connect to {target_url}: {str(e)}"
            logger.error(error_msg)
            return Response(
                response='{"error": "' + error_msg + '"}',
                status=502,
                content_type="application/json"
            )
        
        # For error responses, return them directly without streaming
        if g.api_response.status_code >= 400:
            error_content = g.api_response.content.decode('utf-8')
            logger.error(f"Target server error: {g.api_response.status_code}")
            logger.error(f"Error response: {error_content}")
            return Response(
                error_content,
                status=g.api_response.status_code,
                content_type=g.api_response.headers.get("Content-Type", "application/json")
            )
                
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to forward request: {str(e)}"
        logger.error(error_msg)
        return Response(
            response='{"error": "' + error_msg + '"}',
            status=502,
            content_type="application/json"
        )

    # Check if response should be streamed
    is_stream = json_body.get('stream', False) if json_body else False
    logger.debug(f"Stream mode: {is_stream}")
    
    if not is_stream:
        content = g.api_response.content
        decoded = content.decode("utf-8", errors="replace")
        
        # Check if this is a model list request
        if path in ['models', 'v1/models']:
            try:
                # Attempt to parse the JSON response
                models_data = json.loads(decoded)

                # Extract pseudo models from LLM_PARAMS
                pseudo_models = []
                llm_params = os.getenv('LLM_PARAMS', '')
                if llm_params:
                    for model_entry in llm_params.split(';'):
                        model_entry = model_entry.strip()
                        if not model_entry or not model_entry.startswith('model='):
                            continue
                        parts = model_entry.split(',')
                        model_name = parts[0].split('=', 1)[1].strip()

                        # Create a pseudo model entry in OpenAI-like format
                        pseudo_model = {
                            'id': model_name,
                            'object': 'model',
                            'created': int(time.time()),
                            'owned_by': 'organization-owner'
                        }
                        pseudo_models.append(pseudo_model)

                    # Merge pseudo models into the 'data' array if it exists
                    if 'data' in models_data:
                        models_data['data'].extend(pseudo_models)
                    else:
                        models_data['data'] = pseudo_models

                # Re-encode the JSON response
                decoded = json.dumps(models_data)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse model list response: {e}")
            except Exception as e:
                logger.error(f"Error processing model list: {e}")

        # Conditional filtering based on enable_think_tag_filtering
        if enable_think_tag_filtering:
            # Use effective_think_start_tag and effective_think_end_tag defined earlier in the proxy function
            think_pattern = f"{re.escape(effective_think_start_tag)}.*?{re.escape(effective_think_end_tag)}"
            filtered = re.sub(think_pattern, '', decoded, flags=re.DOTALL)
        else:
            filtered = decoded  # Skip filtering

        logger.debug(f"Non-streaming response content: {filtered}")
        return Response(
            filtered.encode("utf-8"),
            status=g.api_response.status_code,
            headers=[(name, value) for name, value in g.api_response.headers.items() if name.lower() != "content-length"],
            content_type=g.api_response.headers.get("Content-Type", "application/json")
        )
    else:
        # Stream the filtered response back to the client
        def generate_filtered_response():
            buffer = StreamBuffer(effective_think_start_tag, effective_think_end_tag)
            client_disconnected = False
            try:
                # Conditional filtering based on enable_think_tag_filtering
                if enable_think_tag_filtering:
                    for chunk in g.api_response.iter_content(chunk_size=8192):
                        # The act of trying to yield to a disconnected client will typically
                        # raise GeneratorExit or a socket error, caught below.
                        
                        output = buffer.process_chunk(chunk)
                        if output:
                            logger.debug(f"Streaming chunk: {output.decode('utf-8', errors='replace')}")
                            yield output
                    
                    # After the loop, if the client is still considered connected, flush the buffer
                    # (client_disconnected flag will be true if the except block was hit)
                    if not client_disconnected:
                        final_output = buffer.flush()
                        if final_output:
                            logger.debug(f"Final streaming chunk after loop: {final_output.decode('utf-8', errors='replace')}")
                            yield final_output
                else:
                    # No filtering: stream chunks directly
                    for chunk in g.api_response.iter_content(chunk_size=8192):
                        yield chunk
                        
                        
            except (GeneratorExit, ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                # Only log if it's not a GeneratorExit (which is a normal stream closure)
                if not isinstance(e, GeneratorExit):
                    logger.warning(f"Client disconnected or stream error during generation: {type(e).__name__} - {str(e)}")
                client_disconnected = True
                # Optionally, re-raise if specific handling is needed by Flask/Gunicorn,
                # but often just returning is enough to stop the generator.
                # For now, we'll just log and stop.
            except requests.exceptions.RequestException as e:
                # Catch other requests-related errors during streaming
                logger.error(f"Requests exception during streaming: {type(e).__name__} - {str(e)}")
                client_disconnected = True
            except Exception as e:
                # Catch any other unexpected errors during streaming
                logger.error(f"Unexpected error during streaming: {type(e).__name__} - {str(e)}", exc_info=True)
                client_disconnected = True
            # finally:
            #     # Ensure the downstream response is closed, especially if an error occurred.
            #     # The teardown_request will also attempt this, but good for safety here too.
            #     if hasattr(g, 'api_response') and g.api_response:
            #         g.api_response.close()
            #         logger.debug("Downstream API response closed in generate_filtered_response finally block.")

        # Log response details
        logger.debug(f"Response status: {g.api_response.status_code}")
        logger.debug(f"Response headers: {dict(g.api_response.headers)}")
        
        return Response(
            stream_with_context(generate_filtered_response()),
            status=g.api_response.status_code,
            headers=[(name, value) for name, value in g.api_response.headers.items() if name.lower() != "content-length"],
            content_type=g.api_response.headers.get("Content-Type", "application/json")
        )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
