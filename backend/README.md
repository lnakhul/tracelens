# TraceLens Backend

This package contains the TraceLens CLI, FastAPI application, HTTP proxy, and local trace APIs.

Native executions always listen on `127.0.0.1`. The packaged Docker stack sets an internal
`TRACELENS_CONTAINER_MODE=1` environment flag so the backend can listen on the private Compose
network; do not use that flag to expose TraceLens on an untrusted network.

Proxy request and response bodies are buffered up to `10 MiB` by default. Use
`--max-forward-body-bytes` to change the limit. This is separate from the smaller `64 KiB`
text-body capture limit.

See the repository [README](../README.md) for the project overview and
[architecture](../docs/architecture.md) for the V1 design.
