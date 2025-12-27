# Duufy Backend - Production Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies first (caching layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for analytics
RUN mkdir -p /app/data

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run with production settings
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
