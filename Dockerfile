FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install all system dependencies Firefox needs (handles correct package names automatically)
RUN playwright install-deps firefox

# Download the Camoufox patched Firefox binary into the image
RUN python -m camoufox fetch

COPY . .

EXPOSE 8080

CMD ["python", "main.py"]
