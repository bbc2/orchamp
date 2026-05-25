# Stage: Static assets building
FROM debian:12-slim@sha256:e899040a73d36e2b36fa33216943539d9957cba8172b858097c2cabcdb20a3e2 AS builder-static

RUN apt-get update && apt-get install -y ca-certificates unzip wget

# Prepare user
RUN useradd --create-home one
ENV PATH="/home/one/.local/bin:$PATH"
USER one

COPY util/static-dl /usr/local/bin/static-dl
USER root
RUN static-dl \
    --url https://github.com/oven-sh/bun/releases/download/bun-v1.3.5/bun-linux-x64.zip \
    --hash 7051d86a924aefea3e0b96213b5fd8f79c0793f9cae6534233e627e5c3db4669 \
    --out /tmp/bun.zip \
    && unzip /tmp/bun.zip -d /tmp \
    && install -m 755 /tmp/bun-linux-x64/bun /opt/bun \
    && chmod 755 /opt/bun
USER one

RUN mkdir /home/one/app
WORKDIR /home/one/app

COPY package.json bun.lockb ./
RUN /opt/bun install
COPY --chown=one:one src/orchamp_web/static/assumptions.js src/orchamp_web/static/assumptions.js
RUN /opt/bun run build:static

# Stage: Python app building
FROM debian:12-slim@sha256:e899040a73d36e2b36fa33216943539d9957cba8172b858097c2cabcdb20a3e2 AS builder

RUN apt-get update && apt-get install -y wget ca-certificates

# Prepare user
RUN useradd --create-home one
ENV PATH="/home/one/.local/bin:$PATH"
USER one

COPY util/static-dl /usr/local/bin/static-dl
USER root
RUN static-dl \
        --url https://github.com/astral-sh/uv/releases/download/0.9.18/uv-x86_64-unknown-linux-musl.tar.gz \
        --hash a55ae2d0d53c8f6541bb4d6afc95857ff33a97de8f1d23e9d09acdcb865c4a00 \
        --out /tmp/uv.tar.gz \
    && mkdir /opt/uv && tar -xf /tmp/uv.tar.gz --strip-components=1 -C /opt/uv
USER one

RUN mkdir /home/one/app
WORKDIR /home/one/app

ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/home/one/.cache/uv,uid=1000,gid=1000 \
    /opt/uv/uv sync --locked --compile-bytecode --no-dev --no-install-project

# Stage: Final
FROM debian:12-slim@sha256:e899040a73d36e2b36fa33216943539d9957cba8172b858097c2cabcdb20a3e2

RUN apt-get update && apt-get install -y dumb-init && apt-get clean

# Prepare user
RUN useradd --create-home one
ENV PATH="/home/one/.local/bin:$PATH"
USER one

# Copy runtime files from builder
COPY --from=builder /home/one/.local /home/one/.local
COPY --from=builder /home/one/app/.venv /home/one/app/.venv

# Copy source code (separate layer for faster updates)
COPY src /home/one/app/src
ENV PYTHONPATH="/home/one/app/src"

# Compile bytecode for faster startup
USER root
RUN /home/one/app/.venv/bin/python -m compileall -q /home/one/app/src
USER one

# Set up static assets
COPY --from=builder-static \
    /home/one/app/src/orchamp_web/static \
    /home/one/app/src/orchamp_web/static
USER root
RUN chmod --recursive a+rX /home/one/app/src/orchamp_web/static
USER one

# Set up configuration file
COPY _local/config.toml /home/one/app/config.toml
ENV ORCHAMP_CONFIG="/home/one/app/config.toml"

CMD ["dumb-init", "/home/one/app/.venv/bin/gunicorn", "--bind", "0.0.0.0:8080", "--worker-class", "uvicorn.workers.UvicornWorker", "orchamp_web.app:create()"]
