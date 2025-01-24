# OpenAI API Reverse Proxy

A lightweight Dockerized reverse proxy for OpenAI's API endpoints with streaming response support.

## Features

- Transparent request forwarding to OpenAI API
- Streamed response handling
- Automatic `<think>` tag removal from responses
- Runtime LLM parameter overrides (temperature, top_k, etc.)
- Docker-ready deployment with Gunicorn
- JSON request/response handling
- Detailed error reporting
- Configurable target endpoint

## Quick Start

```bash
# Build the Docker image
docker build -t openai-proxy .

# Run the container
docker run -p 5000:5000 openai-proxy
```

## Testing with curl

### Health Check
```bash
# Check proxy health and target URL connectivity
curl http://localhost:5000/health
```

### Chat Completion (Streaming)
```bash
# Test streaming chat completion
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'
```

### Chat Completion (Non-streaming)
```bash
# Test regular chat completion
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Error Handling

The proxy provides detailed error responses for various scenarios:

```bash
# Test with invalid API key
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer invalid_key" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# Test with invalid JSON
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{invalid json}'
```

Error responses include:
- 400: Invalid JSON request
- 502: Connection/forwarding errors
- 503: Health check failures
- 504: Connection timeouts
- Original error codes from target API (401, 403, etc.)

### Test with Different Target
```bash
# Test with custom API endpoint
docker run -e TARGET_BASE_URL="http://your-api:8080/" -p 5000:5000 openai-proxy

curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Development Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python cot_proxy.py
```

## Configuration

### Environment Variables

- `TARGET_BASE_URL`: Target API endpoint (default: https://api.openai.com/v1/)
- `DEBUG`: Enable debug logging (default: false) 
- `LLM_PARAMS`: Comma-separated parameter overrides in format `key=value`. Model-specific groups separated by semicolons. Example: `model=gemma,temperature=0.5,top_k=40;model=llama2,max_tokens=200`

Example with all options:

```bash
# Configure target endpoint and LLM parameters
export TARGET_BASE_URL="http://alternate-api.example.com/"
export LLM_PARAMS="model=gemma,temperature=0.5,top_k=40;model=llama2,max_tokens=200"
export DEBUG=true

# Docker usage example with debug logging:
docker run \
  -e TARGET_BASE_URL="http://alternate-api.example.com/" \
  -e LLM_PARAMS="model=gemma,temperature=0.5,top_k=40" \
  -e DEBUG=true \
  -p 5000:5000 openai-proxy
```

### Production Configuration

The service uses Gunicorn with the following settings:
- 4 worker processes
- 3000 second timeout for long-running requests
- SSL verification enabled
- Automatic error recovery
- Health check endpoint for monitoring

## Dependencies

- Python 3.9+
- Flask
- Requests
- Gunicorn (production)
