# 🚀 cot_proxy: Supercharge Your LLM Workflows!

Ever wished you had more control over how your applications interact with Large Language Models (LLMs)? **cot_proxy** is a smart, lightweight proxy that sits between your app and your LLM, giving you powerful control without changing your client code.

## 🔍 Why cot_proxy?

### 🧠 Master Complex Models Like Qwen3

Qwen3 models have a "reasoning" mode (activated by `/think`) and a "normal" mode (activated by `/no_think`), each requiring different sampling parameters for optimal performance. This makes them difficult to use with applications like Cline or RooCode that don't allow setting these parameters.

**With cot_proxy, you can:**
- Create simplified model names like `Qwen3-Thinking` and `Qwen3-Normal` that automatically:
  - Apply the perfect sampling parameters for each mode
  - Append `/think` or `/no_think` to your prompts
  - Strip out `<think>...</think>` tags when needed
- All without changing a single line of code in your client application!

### 🛠️ Real-World Use Cases

**Case 1: Standardize LLM Interactions Across Tools**
- Problem: Your team uses multiple tools (web UIs, CLI tools, custom apps) to interact with LLMs, leading to inconsistent results.
- Solution: Configure cot_proxy with standardized parameters and prompts for each use case, then point all tools to it.

**Case 2: Clean Up Verbose Model Outputs**
- Problem: Your model includes detailed reasoning in `<think>` tags, but your application only needs the final answer.
- Solution: Enable think tag filtering in cot_proxy to automatically remove the reasoning, delivering clean responses.

**Case 3: Simplify Complex Model Management**
- Problem: You need to switch between different models and configurations based on the task.
- Solution: Create intuitive "pseudo-models" like `creative-writing` or `factual-qa` that map to the right models with the right parameters.

## ✨ Key Features

- **Smart Request Modification**: Automatically adjust parameters and append text to prompts
- **Response Filtering**: Remove thinking/reasoning tags from responses
- **Model Name Mapping**: Create intuitive pseudo-models that map to actual models
- **Streaming Support**: Works with both streaming and non-streaming responses
- **Easy Deployment**: Dockerized for quick setup

## 🚀 Quick Start (5 Minutes)

### 1. Get Up and Running

#### Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/bold84/cot_proxy.git
cd cot_proxy

# Copy the example environment file (includes ready-to-use Qwen3 configurations!)
cp .env.example .env

# Edit the .env file to configure your settings (optional)
# nano .env

# Start the service
docker-compose up -d
```

#### Using Docker Directly

```bash
# Build the Docker image
docker build -t cot-proxy .

# Run the container
docker run -p 3000:5000 cot-proxy
```

### 2. Try It Out with Qwen3

The `.env.example` file includes pre-configured settings for Qwen3 models with both thinking and non-thinking modes. To use them:

1. Make sure you've copied `.env.example` to `.env`
2. Update the `TARGET_BASE_URL` in your `.env` file to point to your Qwen3 API
3. Make requests to your proxy using the pre-configured model names:

```bash
# For thinking mode with optimal parameters
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "Qwen3-32B-Thinking",
    "messages": [{"role": "user", "content": "Explain quantum computing"}],
    "stream": true
  }'

# For non-thinking mode with optimal parameters
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "Qwen3-32B-Non-Thinking",
    "messages": [{"role": "user", "content": "Explain quantum computing"}],
    "stream": true
  }'
```

## 🧪 Additional Testing Options

### Health Check
```bash
# Verify your proxy is running and can connect to your target API
curl http://localhost:3000/health
```

### Testing Different Configurations

#### Test with a Custom Target API
```bash
# Run with a different target API endpoint
docker run -e TARGET_BASE_URL="http://your-api:8080/" -p 3000:5000 cot-proxy
```

#### Test with Debug Logging
```bash
# Enable debug logging to see detailed request/response information
docker run -e DEBUG=true -p 3000:5000 cot-proxy
```

### Error Handling

The proxy provides detailed error responses for various scenarios:

```bash
# Test with invalid API key to see authentication error handling
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer invalid_key" \
  -d '{
    "model": "your-model",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

Error responses include:
- 400: Invalid JSON request
- 502: Connection/forwarding errors
- 503: Health check failures
- 504: Connection timeouts
- Original error codes from target API (401, 403, etc.)

## 👨‍💻 Development Setup

Want to contribute or customize `cot_proxy` for your specific needs? Here's how to set up a development environment:

```bash
# Clone the repository
git clone https://github.com/bold84/cot_proxy.git
cd cot_proxy

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the development server
python cot_proxy.py
```

### Running Tests

`cot_proxy` includes a comprehensive test suite to ensure everything works as expected:

```bash
# Install test dependencies
pip install pytest pytest-flask pytest-mock responses

# Run all tests
pytest

# Run specific test files
pytest tests/test_stream_buffer.py
pytest tests/test_llm_params.py
```

The test suite covers:
- Stream buffer functionality for think tag filtering
- LLM parameter handling and overrides
- Request/response proxying (both streaming and non-streaming)
- Error handling scenarios

## Configuration

### Environment Variables via `.env` file

Configuration is primarily managed via an `.env` file in the root of the project. Create a `.env` file by copying the provided [`.env.example`](.env.example:0).
The `docker-compose.yml` file defines default values for these environment variables using the `${VARIABLE:-default_value}` syntax. This means:
- If a variable is set in your shell environment when you run `docker-compose`, that value takes the highest precedence.
- If not set in the shell, Docker Compose will look for the variable in the `.env` file. If found, that value is used.
- If the variable is not found in the shell or the `.env` file, the `default_value` specified in `docker-compose.yml` (e.g., `false` in `${DEBUG:-false}`) will be used.

The following variables can be set (values in [`.env.example`](.env.example:0) are illustrative, and defaults are shown from `docker-compose.yml`):

- `HOST_PORT`: The port on the host machine to expose the proxy service (default: `3000`). The container internal port is fixed at `5000`.
- `TARGET_BASE_URL`: Target API endpoint (default in example: `http://your-model-server:8080/`)
- `DEBUG`: Enable debug logging (`true` or `false`, default in example: `false`)
- `API_REQUEST_TIMEOUT`: Timeout for API requests in seconds (default in example: `3000`)
- `LLM_PARAMS`: Comma-separated parameter overrides in format `key=value`. Model-specific groups separated by semicolons.
  - Standard LLM parameters like `temperature`, `top_k`, etc., can be overridden per model.
  - Special parameters:
    - `think_tag_start` and `think_tag_end`: Customize the tags used for stripping thought processes
    - `enable_think_tag_filtering`: Set to `true` to enable filtering of think tags (default: `false`)
    - `upstream_model_name`: Replace the requested model with a different model name when forwarding to the API
    - `append_to_last_user_message`: Add text to the last user message or create a new one if needed
  - Example in `.env.example`: `LLM_PARAMS=model=default,temperature=0.7,enable_think_tag_filtering=true,think_tag_start=<think>,think_tag_end=</think>`
  - Example for Qwen3 (commented out in `.env.example`): `LLM_PARAMS=model=Qwen3-32B-Non-Thinking,upstream_model_name=Qwen3-32B,temperature=0.7,top_k=20,top_p=0.8,enable_think_tag_filtering=true,think_tag_start=<think>,think_tag_end=</think>,append_to_last_user_message=\n\n/no_think`
- `THINK_TAG`: Global default start tag for stripping thought processes (e.g., `<think>`). Overridden by model-specific `think_tag_start` in `LLM_PARAMS`. Defaults to `<think>` if not set via this variable or `LLM_PARAMS`. (Example in `.env.example`: `<think>`)
- `THINK_END_TAG`: Global default end tag for stripping thought processes (e.g., `</think>`). Overridden by model-specific `think_tag_end` in `LLM_PARAMS`. Defaults to `</think>` if not set via this variable or `LLM_PARAMS`. (Example in `.env.example`: `</think>`)

**Environment Variable Precedence (for Docker Compose):**
Docker Compose resolves environment variables in the following order of precedence (highest first):
1. Variables set in your shell environment when running `docker-compose up` (e.g., `DEBUG=true docker-compose up`).
2. Variables defined in the `.env` file located in the project directory.
3. Default values specified using the `${VARIABLE:-default_value}` syntax within the `environment` section of `docker-compose.yml`.
4. If a variable is not defined through any of the above methods, it will be unset for the container, and the application (`cot_proxy.py`) might rely on its own internal hardcoded defaults (e.g., for think tags).

**Think Tag Configuration Priority (as seen by `cot_proxy.py` after Docker Compose resolution):**
1. Model-specific `think_tag_start`/`think_tag_end` parsed from the `LLM_PARAMS` environment variable. (The `LLM_PARAMS` variable itself is sourced according to the Docker Compose precedence above).
2. Global `THINK_TAG`/`THINK_END_TAG` environment variables. (These are also sourced according to the Docker Compose precedence).
3. Hardcoded defaults (`<think>` and `</think>`) within `cot_proxy.py` if the corresponding environment variables are not ultimately set.

**Docker Usage:**
The `docker-compose.yml` is configured to use this precedence. It loads variables from the `.env` file and applies defaults from its `environment` section if variables are not otherwise set.
Simply run:
```bash
docker-compose up
# or for detached mode
docker-compose up -d
```
If you need to override a variable from the `.env` file for a specific `docker run` command (less common when using Docker Compose), you can still use the `-e` flag:
```bash
# Example: Overriding DEBUG for a single run, assuming you're not using docker-compose here
docker run -e DEBUG=true -p 3000:5000 cot-proxy
```
However, with the current `docker-compose.yml` setup, managing variables through the `.env` file (to override defaults) is the recommended method.

### Production Configuration

The service uses Gunicorn with the following settings:
- 4 worker processes
- 3000 second timeout for long-running requests
- SSL verification enabled
- Automatic error recovery
- Health check endpoint for monitoring

## Advanced Features

### Model-Specific Configuration

The proxy allows you to define different configurations for different models using the `LLM_PARAMS` environment variable. This enables you to:

1. Create "pseudo-models" that map to real upstream models with specific parameters
2. Apply different parameter sets to different models
3. Configure think tag filtering differently per model

Example configuration for multiple models:

```
LLM_PARAMS=model=Qwen3-32B-Non-Thinking,upstream_model_name=Qwen3-32B,temperature=0.7,top_k=20,top_p=0.8,enable_think_tag_filtering=true,think_tag_start=<think>,think_tag_end=</think>,append_to_last_user_message=\n\n/no_think;model=Qwen3-32B-Thinking,upstream_model_name=Qwen3-32B,temperature=0.6,top_k=20,top_p=0.95,append_to_last_user_message=\n\n/think,enable_think_tag_filtering=true,think_tag_start=<think>,think_tag_end=</think>
```

This creates two pseudo-models:
- `Qwen3-32B-Non-Thinking`: Maps to `Qwen3-32B` with parameters optimized for non-thinking mode
- `Qwen3-32B-Thinking`: Maps to `Qwen3-32B` with parameters optimized for thinking mode

### Think Tag Filtering

The proxy can filter out content enclosed in think tags from model responses. This is useful for:

1. Removing internal reasoning/thinking from final outputs
2. Cleaning up responses for end users
3. Maintaining a clean conversation history

Think tag filtering can be:
- Enabled globally via environment variables
- Configured per model via `LLM_PARAMS`
- Enabled/disabled per model using `enable_think_tag_filtering`

The proxy uses an efficient streaming buffer to handle think tags that span multiple chunks in streaming responses.

### Model Name Substitution

You can create "pseudo-models" that map to actual upstream models using the `upstream_model_name` parameter:

```
model=my-custom-model,upstream_model_name=actual-model-name
```

This allows you to:
1. Create simplified model names for end users
2. Hide implementation details of which models you're actually using
3. Easily switch underlying models without changing client code

### Message Modification

The proxy can automatically append content to the last user message or create a new user message if needed. This is useful for:

1. Adding system instructions without changing client code
2. Injecting special commands or flags (like `/think` or `/no_think`)
3. Standardizing prompts across different clients

Example:
```
append_to_last_user_message=\n\nAlways respond in JSON format.
```

### Usage Examples

#### Creating a "Thinking" and "Non-Thinking" Version of the Same Model

```bash
# In your .env file:
LLM_PARAMS=model=Qwen3-Thinking,upstream_model_name=Qwen3-32B,temperature=0.7,enable_think_tag_filtering=false,append_to_last_user_message=\n\n/think;model=Qwen3-Clean,upstream_model_name=Qwen3-32B,temperature=0.7,enable_think_tag_filtering=true,append_to_last_user_message=\n\n/no_think

# Client can then request either model:
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -d '{
    "model": "Qwen3-Thinking",
    "messages": [{"role": "user", "content": "Solve: 25 × 13"}],
    "stream": true
  }'
```

## Dependencies

- **Python 3.9+**: The core runtime environment
- **Flask 3.0.2**: Lightweight web framework for handling HTTP requests
- **Requests 2.31.0**: HTTP library for forwarding requests to the target API
- **Gunicorn 21.2.0**: Production-grade WSGI server (used in Docker deployment)
- **Testing tools**:
  - pytest: Python testing framework
  - pytest-flask: Flask integration for pytest
  - pytest-mock: Mocking support for pytest
  - responses: Mock HTTP responses

## 🤝 Community & Contributions

We welcome contributions to make `cot_proxy` even better! Here's how you can help:

- **Star the repository**: Show your support and help others discover the project
- **Report issues**: Found a bug or have a feature request? Open an issue on GitHub
- **Submit pull requests**: Code improvements and bug fixes are always welcome
- **Share your use cases**: Let us know how you're using `cot_proxy` in your projects

### License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### Contact

For questions or feedback, please open an issue on the GitHub repository: [https://github.com/bold84/cot_proxy](https://github.com/bold84/cot_proxy)
