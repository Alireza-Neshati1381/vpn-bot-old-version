# Dockerfile for VPN Bot
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY VPN-Bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY VPN-Bot/ .

# Create directories for data persistence
RUN mkdir -p uploads/receipts && \
    chmod 755 uploads/receipts

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run the bot
CMD ["python", "main.py"]
