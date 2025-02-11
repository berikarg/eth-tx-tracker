FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port that uvicorn listens on (should be the same as in config)
EXPOSE 8000

# (Adjust --config path if needed)
CMD ["python", "main.py", "--config", "./configs/config.yml"]