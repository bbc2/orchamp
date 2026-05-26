python_srcs := "src tests"

# List the available commands
help:
    @just --list

# Run Python tests
test-python:
    pytest --numprocesses auto --maxprocesses 4

# Run tests
test: test-python

# Run Python linters (type check + ruff)
lint-python:
    ty check {{ python_srcs }}
    ruff check {{ python_srcs }}
    ruff format --check --diff {{ python_srcs }}

# Lint JSON files
lint-json:
    biome check --linter-enabled=true --formatter-enabled=false .

# Run all linters
lint: lint-python lint-json

# Run all checks (lint + test)
check: lint test

# Fix Python linter errors
fix-python:
    ruff check --fix {{ python_srcs }}

# Fix JSON linter errors
fix-json:
    biome check --write .

# Fix all fixable issues and format
fix: fix-python fix-json

# Format Python code
format-python:
    ruff check --select I --fix {{ python_srcs }}
    ruff format {{ python_srcs }}

# Format JSON files
format-json:
    biome format --write .

# Format all code
format: format-python format-json

# Update test snapshots
update-snapshots:
    pytest --dist no --inline-snapshot create,fix

# Compile translation catalogs (.po → .mo)
compile-translations:
    pybabel compile -d src/orchamp_web/locales

# Update translation template and merge into existing catalogs
update-translations:
    pybabel extract -F babel.cfg -o src/orchamp_web/locales/messages.pot .
    pybabel update -i src/orchamp_web/locales/messages.pot -d src/orchamp_web/locales

# Run the dev server
run:
    #!/usr/bin/env bash
    set -e
    just compile-translations
    bun run build:static
    python -m http.server 8081 --directory tests &>/dev/null &
    HTTP_PID=$!
    trap "kill $HTTP_PID 2>/dev/null" EXIT
    env \
        ORCHAMP_CONFIG=_local/config.toml \
        ORCHAMP_LOG_LEVEL=DEBUG \
        uvicorn --factory --reload orchamp_web.app:create

# Build the Docker image
docker-build:
    docker build --tag orchamp:latest --file docker/orchamp.dockerfile .

# Build and run the Docker image
docker-run: docker-build
    docker run --rm --publish 8080:8080 \
        --volume "$(pwd)/_local/config.toml:/home/one/app/config.toml:ro" \
        --env ORCHAMP_BETA_PASSWORD=pass \
        orchamp:latest

# Deploy the application
deploy: docker-build
    #!/usr/bin/env bash
    set -e
    if [ -z "$ORCHAMP_BETA_PASSWORD" ]; then
        echo "Error: ORCHAMP_BETA_PASSWORD is not set" >&2
        exit 1
    fi
    flyctl secrets set --stage ORCHAMP_BETA_PASSWORD="$ORCHAMP_BETA_PASSWORD"
    flyctl deploy --local-only
