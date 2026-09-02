#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_dir="$root_dir/backend"
frontend_dir="$root_dir/frontend"

cleanup() {
  trap - EXIT INT TERM
  kill "${frontend_pid:-}" "${proxy_pid:-}" "${upstream_pid:-}" 2>/dev/null || true
}

wait_for() {
  local url="$1"
  for _ in {1..40}; do
    if curl --fail --silent "$url" >/dev/null; then
      return 0
    fi
    sleep 0.25
  done
  echo "Timed out waiting for $url" >&2
  exit 1
}

trap cleanup EXIT INT TERM

"$backend_dir/.venv/bin/python" -m tracelens.demo --port 8000 >"$root_dir/.demo-upstream.log" 2>&1 &
upstream_pid=$!
"$backend_dir/.venv/bin/tracelens" --target http://127.0.0.1:8000 --port 9000 >"$root_dir/.demo-proxy.log" 2>&1 &
proxy_pid=$!

wait_for http://127.0.0.1:8000/docs
wait_for http://127.0.0.1:9000/api/health

curl --fail --silent http://127.0.0.1:9000/users/42 >/dev/null
for _ in {1..5}; do
  curl --fail --silent http://127.0.0.1:9000/reports/daily >/dev/null
done
curl --fail --silent 'http://127.0.0.1:9000/reports/daily?slow=true' >/dev/null
curl --fail --silent --request POST http://127.0.0.1:9000/orders \
  --header 'Content-Type: application/json' \
  --data '{"customer_id":"cus_demo_001","product_id":"prod_keyboard"}' >/dev/null
curl --silent --request POST http://127.0.0.1:9000/orders \
  --header 'Content-Type: application/json' \
  --data '{"product_id":"prod_keyboard"}' >/dev/null

echo "Demo traffic captured. Open http://127.0.0.1:5173"
echo "Press Ctrl+C to stop the demo services."
(cd "$frontend_dir" && npm run dev -- --host 127.0.0.1) &
frontend_pid=$!
wait "$frontend_pid"