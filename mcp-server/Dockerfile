FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

COPY pyproject.toml README.md ./
COPY apps ./apps
COPY orchestrator ./orchestrator
COPY mcp-server ./mcp-server

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -e .

EXPOSE 8080

CMD ["sh", "-c", "uvicorn server:app --app-dir mcp-server --host 0.0.0.0 --port ${PORT}"]
