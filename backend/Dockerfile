FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY tracelens ./tracelens

RUN pip install --no-cache-dir .

ENTRYPOINT ["tracelens"]