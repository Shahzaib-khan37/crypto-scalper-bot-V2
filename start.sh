#!/bin/bash
# Fallback to port 5000 if PORT environment variable is not defined (e.g. on GCP)
PORT=${PORT:-5000}

echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt

echo "Starting application with Gunicorn on port $PORT..."
gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 app:app
