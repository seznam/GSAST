FROM python:3.10 AS base

COPY . /app

WORKDIR /app

RUN python3 --version

RUN python3 -m pip install semgrep==1.99.0 && \
    python3 -m pip install -e gsast-core/ && \
    python3 -m pip install -e gsast-api/ && \
    python3 -m pip install -e gsast-worker/ && \
    python3 -m pip install -e gsast-cli/

ENV SEMGREP_ENABLE_VERSION_CHECK=0

RUN curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin

RUN trufflehog --version --no-update

EXPOSE 5000
CMD ["gsast-api"]

# Extends base with debugpy pre-installed so it does not need to be fetched at
# container startup (which fails when REQUESTS_CA_BUNDLE points to a corporate
# CA bundle that cannot verify PyPI).
# NOTE: This is the last stage, so a plain `docker build .` produces this image.
# Always use `--target base` for production builds (docker-compose.yml enforces this).
FROM base AS debug
RUN python3 -m pip install debugpy
