FROM python:3.11-slim

LABEL maintainer="SentinelIQ AI Safety Platform"
LABEL version="1.0.0"

WORKDIR /app

# System dependencies for OpenCV + GPU
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create required directories
RUN mkdir -p evidence backend/data

# Non-root user for security
RUN useradd -m -u 1001 vigil && chown -R vigil:vigil /app
USER vigil

EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

CMD ["uvicorn", "backend.core.app:app", "--host", "0.0.0.0", "--port", "5000", \
     "--workers", "1", "--timeout-keep-alive", "75", "--loop", "asyncio"]
