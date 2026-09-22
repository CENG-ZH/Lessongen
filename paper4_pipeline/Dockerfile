FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN python -m pip install --no-cache-dir uv==0.11.16
COPY . .
RUN uv sync --locked --extra web --no-dev && \
    python -c "import paper4_pipeline.providers.openai_compatible as p; assert p.__file__.startswith('/app/')"

CMD ["python", "-m", "paper4_pipeline.web_api"]
