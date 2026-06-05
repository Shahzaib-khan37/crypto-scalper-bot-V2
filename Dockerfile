FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# Copy and install dependencies
COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy all codebase files
COPY . /code

# Set port to 7860 (Hugging Face default)
ENV PORT=7860
EXPOSE 7860

# Run Flask application
CMD ["python", "app.py"]
