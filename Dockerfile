# Use official Python base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install required system packages
RUN apt-get update && apt-get install -y --no-install-recommends gcc python3-dev

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the application port
EXPOSE 3000

# Set default environment variables
ENV DEBUG=false
ENV LLM_PARAMS=

# Run with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "3000", "--access-logfile", "-", "--error-logfile", "-", "cot_proxy:app"]
