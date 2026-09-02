# TraceLens Security Model

TraceLens is a local developer tool, not a hardened gateway or multi-user observability service.
Its safety model depends on limiting access to the machine and Docker host that run it. Do not
expose TraceLens to an untrusted network or use it as a production reverse proxy.

## Trust Boundaries

TraceLens handles four distinct trust zones:

1. The calling application and configured upstream API, whose traffic may contain secrets or
   personal data.
2. The TraceLens process and SQLite database, which store selected request and response data.
3. The dashboard and management API, which can read and permanently delete stored traces.
4. An optional external AI provider, which receives explicitly selected trace context.

The management API has no authentication or authorization. Anyone able to reach it can inspect or
delete traces and can request AI analysis when a provider is configured. Loopback binding and the
Docker port layout reduce reachability; they are not substitutes for authentication.

## Native and Docker Exposure

Native execution binds to `127.0.0.1`. The CLI does not offer a public bind-address option.
Other processes running as the same user, privileged local software, and users with access to the
machine remain inside the trust boundary.

The supplied Compose stack is an evaluation environment:

- only Nginx is published, at `127.0.0.1:5173`;
- the TraceLens backend and demo upstream are reachable by other containers on the Compose network;
- Nginx forwards `/api/*` to the backend;
- `TRACELENS_CONTAINER_MODE=1` makes the backend listen on all container interfaces;
- the SQLite database persists in the `tracelens-data` volume.

Container mode is a packaging mechanism, not an authorization control. Copying it into another
deployment, publishing backend port `9000`, changing the dashboard port to a non-loopback address,
or joining untrusted containers to the network expands the attack surface. The stack does not add
TLS, user authentication, tenant isolation, rate limiting, network egress controls, or encrypted
storage. It is not presented as a production deployment reference.

## Captured and Stored Data

TraceLens redacts the values of `Authorization`, `Cookie`, `Set-Cookie`, and `X-Api-Key` headers
before persistence. Header names outside that fixed list are not automatically recognized as
sensitive. Paths, query strings, and textual JSON, form, or text bodies can still contain secrets.
Review the traffic being proxied before using TraceLens with confidential or regulated data.

Text-body capture is limited to `64 KiB` by default. Binary, multipart, encoded, unknown-type, and
oversized bodies are omitted from capture. These controls reduce retained data; they are not
content-aware redaction. The forwarding limit is a separate `10 MiB` boundary and does not imply
that every forwarded body is stored.

SQLite data and the Docker volume are not encrypted by TraceLens. File-system or Docker access can
therefore expose retained traces and AI audit metadata. Deletion removes application records but is
not a guaranteed secure erase from SQLite pages, snapshots, backups, or storage media.

## External AI Analysis

AI analysis is disabled unless an endpoint, model, and `TRACELENS_AI_API_KEY` are configured. It is
an optional provider integration, not an offline or local analysis feature.

The dashboard requires a metadata-sharing checkbox and a second checkbox before including captured
bodies. The API independently requires `share_data: true`, but this Boolean is only an assertion in
the request: without authentication, it does not establish the identity or authority of the caller.

When analysis runs, TraceLens sends:

- the failed trace's method, path, status, duration, error type, and stored redacted headers;
- the same fields for up to five recent successful calls to that method and path; and
- captured request and response bodies for those traces only when `include_bodies` is true.

The serialized context is capped at `24 KiB` by default. The API key is sent as a bearer token to
the configured endpoint. TraceLens does not currently require HTTPS or restrict the endpoint host,
so operators must configure a trusted HTTPS endpoint and understand that provider's retention,
training, residency, access-control, and billing policies. Provider logs and retention are outside
TraceLens deletion controls.

Compatibility is limited to chat-completions APIs that accept the configured request shape,
including strict JSON-schema response formatting. “OpenAI-compatible” does not guarantee that an
arbitrary provider implements those features. Model output is diagnostic guidance, may be wrong,
and must not be executed or treated as a security decision without human review. Captured traffic
is untrusted model input and may contain prompt-injection content.

TraceLens stores metadata about each analysis attempt, but not the prompt, provider response, or
rendered analysis. The audit record includes the trace ID, timestamp, model, body-sharing choice,
outcome, provider status, and attempt count. The provider may independently retain request data.

## Operator Checklist

- Keep native and dashboard listeners on loopback.
- Do not publish backend port `9000` or reuse container mode for remote access.
- Proxy only development traffic that is safe to retain locally.
- Treat custom credential headers, URLs, query strings, and bodies as potentially unredacted.
- Configure AI only with a trusted HTTPS endpoint and an appropriately scoped API key.
- Review the exact trace and body-sharing choice before each analysis request.
- Set retention or delete traces and the Docker volume when the data is no longer needed.
- Do not rely on TraceLens for production authentication, authorization, TLS termination, or audit
  compliance.

