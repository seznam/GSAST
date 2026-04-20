FROM python:3.10

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
