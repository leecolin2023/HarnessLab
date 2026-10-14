#!/usr/bin/env bash
# EXP-MS-001 reproducibility helper, not production installation.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

failure() {
  local code=$?
  echo "[ERROR] Experimental workflow interrupted (exit $code)."
  echo "Inspect: docker compose ps / docker compose logs --tail=100"
  exit "$code"
}
trap failure ERR

for cmd in docker python3 curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[BLOCKED] Required command not found: $cmd"
    exit 2
  fi
done
docker compose version >/dev/null
docker info >/dev/null 2>&1 || { echo "[BLOCKED] Docker daemon unavailable"; exit 2; }

mkdir -p results models
if [ ! -f .env ]; then
  python3 - <<'PY'
from secrets import token_urlsafe
from pathlib import Path
p=Path(".env")
p.write_text("MODEL_API_KEY="+token_urlsafe(32)+"\nOCR_PROFILE=small\nOCR_CPU_THREADS=2\nMAX_UPLOAD_BYTES=5242880\nMAX_IMAGE_PIXELS=16000000\n")
p.chmod(0o600)
PY
  echo "Created a new private .env (key not printed)."
fi

echo "[1/5] Build model service image (may download large dependencies)"
docker compose build
echo "[2/5] Start model service (first run may download OCR weights)"
docker compose up -d

ready=0
for i in $(seq 1 90); do
  if curl -sf --max-time 5 http://127.0.0.1:8008/health/ready >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 10
done
if [ "$ready" -ne 1 ]; then
  echo "[BLOCKED] OCR model did not become ready within 15 minutes."
  docker compose ps
  docker compose logs --tail=60
  exit 3
fi

echo "[3/5] Generate synthetic OCR image"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || { echo "[BLOCKED] Install python3-venv for Ubuntu 24.04"; exit 3; }
fi
if ! .venv/bin/python -c "import PIL" >/dev/null 2>&1; then
  .venv/bin/python -m pip install -q Pillow
fi
.venv/bin/python tools/make_sample.py
set -a
# shellcheck disable=SC1091
. ./.env
set +a

echo "[4/5] Verify authenticated inference and rejected invalid secret"
success_code="$(curl --silent --show-error --max-time 120 -o results/first-response.json -w '%{http_code}' \
  -H "Authorization: Bearer $MODEL_API_KEY" \
  -F "file=@sample.png" \
  http://127.0.0.1:8008/v1/ocr)"
if [ "$success_code" != "200" ]; then
  echo "[FAILED] Expected 200, got $success_code. See results/first-response.json"
  exit 4
fi
python3 - <<'PY'
from pathlib import Path
import json
p=Path("results/first-response.json")
data=json.loads(p.read_text())
if not isinstance(data.get("lines"),list) or not data["lines"]:
    raise SystemExit("[FAILED] HTTP 200 but OCR lines were empty")
print("[OK] Local OCR returned",len(data["lines"]),"text regions using",data.get("model"))
PY

bad_code="$(curl --silent --max-time 30 -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer definitely-wrong" \
  -F "file=@sample.png" \
  http://127.0.0.1:8008/v1/ocr)"
if [ "$bad_code" != "401" ]; then
  echo "[FAILED] Expected 401 for wrong secret; got $bad_code"
  exit 4
fi

echo "[5/5] Collect limited baseline request metrics"
python3 tools/bench.py --image sample.png --requests 5 --concurrency 1 --out results/c1
python3 tools/bench.py --image sample.png --requests 10 --concurrency 2 --out results/c2
python3 tools/bench.py --image sample.png --requests 10 --concurrency 4 --out results/c4
docker stats --no-stream > results/docker-stats.txt
echo "[OK] Results: results/first-response.json, c1.json, c2.json, c4.json, docker-stats.txt"
echo "No QPS/latency claims should be made without reviewing these measurements."
