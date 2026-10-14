"""Small dependency-free HTTP benchmark; saves only status and latency."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid


def percentile(data, q):
    if not data:
        return None
    values = sorted(data)
    pos = (len(values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (pos - lo), 2)


def call(url, content, key):
    boundary = "----OCR" + uuid.uuid4().hex
    prefix = (f"--{boundary}\r\n"
              'Content-Disposition: form-data; name="file"; filename="sample.png"\r\n'
              "Content-Type: image/png\r\n\r\n").encode()
    payload = prefix + content + f"\r\n--{boundary}--\r\n".encode()
    req = Request(url, method="POST", data=payload, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    begin = time.perf_counter()
    try:
        with urlopen(req, timeout=90) as response:
            response.read()
            status = response.status
    except HTTPError as exc:
        status = exc.code
        exc.close()
    except (URLError, TimeoutError, OSError):
        status = 0
    return {"status": status,
            "latency_ms": round((time.perf_counter() - begin) * 1000, 2)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8008/v1/ocr")
    parser.add_argument("--image", required=True)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--out", default="results/baseline")
    args = parser.parse_args()
    key = os.getenv("MODEL_API_KEY", "")
    if len(key) < 24 or args.requests < 1 or args.concurrency < 1:
        parser.error("Set MODEL_API_KEY, --requests and --concurrency")
    data = Path(args.image).read_bytes()
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        tasks = [pool.submit(call, args.url, data, key) for _ in range(args.requests)]
        results = [t.result() for t in as_completed(tasks)]
    wall = time.perf_counter() - start
    good = [r["latency_ms"] for r in results if r["status"] == 200]
    summary = {
        "requests": args.requests, "concurrency": args.concurrency,
        "wall_seconds": round(wall, 2),
        "status_counts": {str(s): sum(r["status"] == s for r in results)
                          for s in sorted({r["status"] for r in results})},
        "success_rate": round(len(good) / len(results), 4),
        "success_qps": round(len(good) / wall, 3) if wall else 0,
        "success_p50_ms": percentile(good, 0.5),
        "success_p95_ms": percentile(good, 0.95),
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["status", "latency_ms"])
        w.writeheader()
        w.writerows(results)
    path.with_suffix(".json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
