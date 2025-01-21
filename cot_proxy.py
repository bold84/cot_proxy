from flask import Flask, request, Response, stream_with_context
import requests
import re
import os
import logging
from urllib.parse import urljoin

app = Flask(__name__)

# Configure logging based on DEBUG environment variable
log_level = logging.DEBUG if os.getenv('DEBUG', 'false').lower() == 'true' else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configure target URL
TARGET_BASE_URL = os.getenv('ENV_TARGET_BASE_URL', 'https://api.openai.com/v1/')
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
    
    try:
        # Get JSON body if present
        json_body = request.get_json(silent=True) if request.is_json else None
        logger.debug(f"Request JSON body: {json_body}")
        
        # Try to connect with a timeout
        try:
            api_response = requests.request(
                method=request.method,
                url=target_url,
                headers=headers,
                json=json_body,
                stream=True,
                timeout=30,  # 30 second timeout
                verify=True  # Verify SSL certificates
            )
            logger.debug(f"Connected to target URL: {target_url}")
            logger.debug(f"Target response time: {api_response.elapsed.total_seconds()}s")
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
        if api_response.status_code >= 400:
            error_content = api_response.content.decode('utf-8')
            logger.error(f"Target server error: {api_response.status_code}")
            logger.error(f"Error response: {error_content}")
            return Response(
                error_content,
                status=api_response.status_code,
                content_type=api_response.headers.get("Content-Type", "application/json")
            )
                
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to forward request: {str(e)}"
        logger.error(error_msg)
        return Response(
            response='{"error": "' + error_msg + '"}',
            status=502,
            content_type="application/json"
        )

    # Buffer for handling think tags across chunks
    class StreamBuffer:
        def __init__(self):
            self.buffer = ""
            
        def process_chunk(self, chunk):
            # Decode and add to buffer
            decoded_chunk = chunk.decode("utf-8", errors="replace")
            self.buffer += decoded_chunk
            
            output = ""
            
            while True:
                # Find the next potential tag start
                start = self.buffer.find("<think>")
                
                if start == -1:
                    # No more think tags, output all except last few chars
                    if len(self.buffer) > 1024:
                        output += self.buffer[:-1024]
                        self.buffer = self.buffer[-1024:]
                    break
                
                # Output content before the tag
                if start > 0:
                    output += self.buffer[:start]
                    self.buffer = self.buffer[start:]
                    start = 0  # Tag is now at start of buffer
                
                # Look for end tag
                end = self.buffer.find("</think>", start)
                if end == -1:
                    # No end tag yet, keep in buffer
                    break
                
                # Remove the complete think tag and its content
                end += len("</think>")
                self.buffer = self.buffer[end:]
            
            return output.encode("utf-8") if output else b""
            
        def flush(self):
            # Output remaining content
            output = self.buffer
            self.buffer = ""
            return output.encode("utf-8")

    # Check if response should be streamed
    is_stream = json_body.get('stream', False) if json_body else False
    logger.debug(f"Stream mode: {is_stream}")
    
    if not is_stream:
        # For non-streaming responses, return the full content
        content = api_response.content
        decoded = content.decode("utf-8", errors="replace")
        filtered = re.sub(r'<think>.*?</think>', '', decoded, flags=re.DOTALL)
        logger.debug(f"Non-streaming response content: {filtered}")
        return Response(
            filtered.encode("utf-8"),
            status=api_response.status_code,
            headers=[(name, value) for name, value in api_response.headers.items() if name.lower() != "content-length"],
            content_type=api_response.headers.get("Content-Type", "application/json")
        )
    else:
        # Stream the filtered response back to the client
        def generate_filtered_response():
            buffer = StreamBuffer()
            for chunk in api_response.iter_content(chunk_size=8192):
                # Process chunk through buffer
                output = buffer.process_chunk(chunk)
                if output:
                    logger.debug(f"Streaming chunk: {output.decode('utf-8', errors='replace')}")
                    yield output
            
            # Flush any remaining content
            final_output = buffer.flush()
            if final_output:
                logger.debug(f"Final streaming chunk: {final_output.decode('utf-8', errors='replace')}")
                yield final_output

        # Log response details
        logger.debug(f"Response status: {api_response.status_code}")
        logger.debug(f"Response headers: {dict(api_response.headers)}")
        
        return Response(
            stream_with_context(generate_filtered_response()),
            status=api_response.status_code,
            headers=[(name, value) for name, value in api_response.headers.items() if name.lower() != "content-length"],
            content_type=api_response.headers.get("Content-Type", "application/json")
        )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
