FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir --timeout=120 . 2>&1 | tail -5

COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "shifttracker.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
