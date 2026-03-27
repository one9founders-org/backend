FROM python:3.11-slim

EXPOSE 8000

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app/backend

# Install system dependencies first (rarely changes)
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies (changes less frequently)
COPY requirements.txt .
# Install PyTorch CPU-only first to avoid pulling ~7GB of NVIDIA CUDA packages.
# This server runs on CPU — the full CUDA build exceeds the EC2 disk budget.
RUN pip install --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code (changes most frequently)
COPY . .

# Create staticfiles directory
RUN mkdir -p /app/backend/staticfiles

CMD ["gunicorn", "--config", "gunicorn.conf.py", "config.wsgi:application"]
