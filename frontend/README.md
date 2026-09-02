# TraceLens Dashboard

The React and TypeScript interface for local TraceLens traffic.

Requires Node.js 20.19+ or 22.12+.

```bash
npm ci
npm run dev
```

The Vite dev server proxies `/api` requests to `http://127.0.0.1:9000`, where the TraceLens backend must be running.

The supplied Nginx container is part of the loopback-only Docker evaluation demo. It does not add
authentication or TLS and is not a production deployment reference. See the repository
[security model](../docs/security.md).

```bash
npm run lint
npm run build
```
