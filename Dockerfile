FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
RUN mkdir -p /app/data

# tests
FROM base AS test
RUN pip install --no-cache-dir pytest
COPY tests ./tests
CMD ["pytest", "-v"]

# production
FROM base AS prod
EXPOSE 8000 8501
CMD ["uvicorn", "lol_analytics.api:app", "--host", "0.0.0.0", "--port", "8000"]