FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create app user for security
RUN useradd --create-home --shell /bin/bash app

# Copy application code
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p /data/database/backups /data/uploads \
    && chown -R app:app /app /data

# Switch to app user
USER app

# Expose port
EXPOSE 8065

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8065/health || exit 1

# Start application with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8065", "--workers", "4", "--timeout", "120", "--max-requests", "1000", "run:app"] 