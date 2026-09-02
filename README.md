# TraceLens

**A local API observability and debugging proxy for developers.**

TraceLens sits between an application and its HTTP API. It forwards traffic to a configured target, captures each exchange in local SQLite storage, and provides a React dashboard for investigating failures and latency.

```mermaid
flowchart LR
    Client[Application] -->|HTTP| Proxy[TraceLens\nFastAPI + HTTPX]
    Proxy -->|Forward| Upstream[Target API]
    Proxy -->|Persist traces| Database[(SQLite)]
    Dashboard[React dashboard] -->|Inspect traces| Proxy
```

## Quick Start

Prerequisites: Python $>=3.12,<3.15$, Node.js 20+, and `make`.

```bash
make backend-install
make frontend-install
```

Start TraceLens against an upstream service:

```bash
make backend TARGET=http://localhost:8000
```

In another terminal, start the dashboard:

```bash
make frontend
```

Open `http://127.0.0.1:5173`. Point an application at `http://127.0.0.1:9000`; TraceLens forwards requests to the target and records them locally.

## Try the Demo

After installation, launch the deterministic demo environment:

```bash
make demo
```

It starts a local upstream API on port `8000`, TraceLens on port `9000`, seeds successful traffic, a slow request, and a failed order request, then starts the dashboard at `http://127.0.0.1:5173`. Select the failed `POST /orders` trace to inspect its captured request and response. The five normal `GET /reports/daily` calls followed by a slow one demonstrate the V2 latency anomaly signal. Press `Ctrl+C` in the demo terminal to stop all three services.

![TraceLens dashboard showing seeded demo traffic](docs/screenshots/dashboard-demo.png)

Run the upstream API alone with `make demo-api` when integrating TraceLens manually. The API exposes `GET /users/{id}`, `GET /reports/daily?slow=true`, and `POST /orders`; omit `customer_id` from an order to create a deterministic `500` response.

## Docker Demo

Docker Desktop with Docker Compose is the only additional prerequisite. Run the complete evaluation environment with:

```bash
make docker-demo
```

Compose builds and starts the demo upstream, TraceLens, a production dashboard served by Nginx, and a one-shot traffic seeder. Open `http://127.0.0.1:5173` after the services are ready. Nginx proxies dashboard `/api` requests to TraceLens over the private Compose network; the backend's port `9000` is not published to the host.

The SQLite database persists in the `tracelens-data` Docker volume, so traffic remains available across `docker compose down` and the next `make docker-demo`. Stop services with `make docker-down`. To remove all containerized traces and images created by the stack, run:

```bash
docker compose down --volumes --rmi local
```

## Development

The `Makefile` provides the common commands:

| Command | Purpose |
| --- | --- |
| `make test` | Run the backend test suite |
| `make frontend-test` | Run the dashboard test suite |
| `make lint` | Lint the backend and dashboard |
| `make build` | Produce a dashboard production build |
| `make backend TARGET=http://localhost:8000` | Start the local proxy |
| `make frontend` | Start the dashboard development server |
| `make demo` | Start the demo upstream, proxy, seed traffic, and dashboard |
| `make demo-api` | Start only the demo upstream API |
| `make docker-demo` | Build and start the containerized demo environment |
| `make docker-down` | Stop the containerized demo environment |

To run without `make`:

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest
```

```bash
cd frontend
npm ci
npm run dev
```

Vite proxies local `/api` requests to TraceLens on port `9000`.

## API

| Endpoint | Description |
| --- | --- |
| `GET /api/health` | Confirm the local management API is running |
| `GET /api/traces` | List traces, including endpoint latency analysis; filter by `path`, `status_code`, `min_duration_ms`, or `max_duration_ms` |
| `GET /api/traces/{id}` | Inspect the complete captured exchange and its latency analysis |
| `DELETE /api/traces/{id}` | Permanently delete one trace and its local analysis audit metadata |
| `POST /api/traces/{id}/analysis` | Request explicitly consented external analysis for a failed trace |
| `GET /api/metrics` | Get request count, error rate, average latency, and P95 latency |
| `DELETE /api/traces` | Permanently clear locally stored trace history |

```bash
curl 'http://127.0.0.1:9000/api/traces?status_code=500&min_duration_ms=300'
curl http://127.0.0.1:9000/api/metrics
```

Trace lists are paginated with `limit` and `offset` (up to 200 traces per page). The dashboard loads 50 traces at a time and keeps active filters when navigating pages.

## Retention and Deletion

TraceLens retains captured traces until you clear or delete them by default. Enable automatic pruning with a positive `--retention-hours` value; pruning runs when a new trace is captured and removes the expired trace plus its metadata-only AI analysis audits.

```bash
make backend TARGET=http://localhost:8000 BACKEND_ARGS='--retention-hours 168'
```

Use the dashboard detail panel to delete one trace, or `DELETE /api/traces` to purge all local history.

## V1

- Async HTTP reverse proxy built with FastAPI and HTTPX
- SQLite-backed capture of request method, path, status, timestamp, and duration
- React and TypeScript dashboard for traffic metrics and trace details
- Server-side filters for endpoint, HTTP status, and latency
- Safe capture defaults: local binding, sensitive-header redaction, and bounded text-body capture

TraceLens is deliberately a local developer tool. HTTPS interception, streaming, and remote deployment are deferred.

Request and response bodies are buffered for forwarding up to `10 MiB` by default. Configure the
boundary with `--max-forward-body-bytes`; oversized client requests receive `413`, and oversized
upstream responses receive `502`. Text capture remains independently capped at `64 KiB`, and
encoded response bodies are forwarded unchanged but omitted from body capture.

Native runs always bind to `127.0.0.1`. The Docker demo enables an internal container mode so TraceLens can listen on its private Compose network, but Compose does not publish the backend port to the host. Container mode is reserved for the packaged stack and is not a public CLI option.

## V2: Latency Anomalies

TraceLens derives a baseline from the five preceding traces with the same HTTP method and path. A request is marked as a latency anomaly when it takes at least twice that baseline. Analysis is calculated from locally retained traces when they are read, so it introduces no extra persisted data or migration.

The trace list and detail APIs include `baseline_duration_ms`, `latency_increase_ratio`, and `is_anomaly`. The dashboard marks anomalous requests and shows the baseline comparison in trace detail.

## V3: AI-Assisted Failure Analysis

Failure analysis is disabled by default. Configure an OpenAI-compatible chat-completions endpoint, a model, and an API key to enable it:

```bash
export TRACELENS_AI_API_KEY='your-provider-key'
make backend TARGET=http://localhost:8000 \
  BACKEND_ARGS='--ai-endpoint https://api.openai.com/v1/chat/completions --ai-model gpt-4.1-mini'
```

For a failed trace, the dashboard requires an explicit consent checkbox before TraceLens contacts the provider. Captured request and response bodies are excluded by default and require a separate opt-in. TraceLens sends the failed trace plus up to five recent successful requests to the same method and path; captured headers have already passed through TraceLens header redaction. API keys remain in the process environment and are never stored in SQLite or returned by the API.

AI context is capped at `24 KiB` by default, with oversized captured fields truncated before sharing. TraceLens retries transient transport failures and `429` rate limits twice by default, using capped backoff. Configure the limits with `--ai-max-context-bytes` and `--ai-max-retries`. Provider responses must satisfy a strict JSON schema. Each analysis action records only local audit metadata: timestamp, trace ID, selected model, body-sharing choice, outcome, provider status, and attempt count. Prompts and analysis results are never written to the audit table.

## Architecture

The full V1 implementation contract covers module boundaries, request lifecycle, data model, REST API, proxy behavior, failure handling, concurrency, privacy, testing, and architectural tradeoffs.

Read [the V1 architecture](docs/architecture.md#L1).

## Quality Gates

GitHub Actions runs backend tests and Ruff checks on Python 3.12, plus dashboard tests, linting, and a production build on Node.js 20, for every pull request and push to `main`.

## Repository Layout

```text
tracelens/
  backend/                  # Python CLI, proxy, storage, and REST API
  frontend/                 # React and TypeScript dashboard
  docs/
    architecture.md         # Canonical V1 technical design
    screenshots/            # Dashboard images and demos
  .github/
    workflows/              # CI
  Makefile                  # Common development commands
  LICENSE                   # MIT
```

## Roadmap

- **V1:** local proxy, trace persistence, REST API, dashboard, CI, and documentation
- **V2:** endpoint latency baselines and slow-request anomaly detection
- **V3:** optional AI-assisted failure analysis with explicit data-sharing controls

## Status

V3 complete. AI analysis is opt-in and disabled until a provider is configured.
