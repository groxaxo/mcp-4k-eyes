FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install system libs for Pillow
RUN apt-get update && apt-get install -y libjpeg-dev zlib1g-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY grounding_server.py .

# Expose the weird port
EXPOSE 43210

# Default command
CMD ["python", "grounding_server.py"]
