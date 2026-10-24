# syntax=docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89
FROM python:3.12-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2
COPY --from=ghcr.io/astral-sh/uv:0.12.3@sha256:2d890623d310b57771ce840f0da5eed5fc6d657da05ffaa45d82797b53fa3abc /uv /bin/uv
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never
WORKDIR /opt/workstream/backend
COPY backend/pyproject.toml backend/uv.lock backend/LICENSE ./
COPY backend/app ./app
RUN uv sync --locked --no-dev --no-editable && rm -rf build workstream_backend.egg-info
COPY external_checkers/intake/worker.py /opt/workstream/intake.py
ENTRYPOINT ["/opt/venv/bin/python", "-I", "/opt/workstream/intake.py"]
