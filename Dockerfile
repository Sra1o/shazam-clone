FROM python:3.10-slim

WORKDIR /app

# Install system dependencies required for audio processing
# libsndfile1 and ffmpeg are needed by librosa
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend application code
COPY . .

# Render dynamically assigns a PORT environment variable
EXPOSE 8000

# Run Uvicorn server, binding to the PORT env variable (defaulting to 8000 if not set)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
