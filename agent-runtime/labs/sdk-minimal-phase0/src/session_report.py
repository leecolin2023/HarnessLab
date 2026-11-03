"""Summarize native JSONL Session files WITHOUT printing sensitive event payloads."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

MAX_FILE_BYTES = 32 * 1024 * 1024


def classify(obj: object) -> str:
    if not isinstance(obj, dict):
        return "unknown"
    for key in ("kind", "type", "event_type"):
        value = obj.get(key)
        if isinstance(value, str):
            return value
    nested = obj.get("event")
    return classify(nested) if isinstance(nested, dict) else "unknown"


def summarize(home: Path) -> dict:
    sessions = home / "sessions"
    if not sessions.is_dir():
        raise FileNotFoundError(f"Session directory not found: {sessions}")
    files = sorted(sessions.rglob("*.jsonl"))
    result = {"sessions_directory": str(sessions), "file_count": len(files),
              "files": [], "aggregate_kinds": {}}
    counts: Counter[str] = Counter()
    for file in files:
        info = {"file": str(file.relative_to(sessions)), "bytes": file.stat().st_size,
                "lines": 0, "invalid_json_lines": 0, "event_kinds": {}}
        if file.stat().st_size > MAX_FILE_BYTES:
            info["skipped"] = "file exceeds 32 MiB viewer limit"
            result["files"].append(info)
            continue
        kinds: Counter[str] = Counter()
        with file.open(encoding="utf-8") as source:
            for line in source:
                if not line.strip():
                    continue
                info["lines"] += 1
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    info["invalid_json_lines"] += 1
                    continue
                kinds[classify(obj)] += 1
        info["event_kinds"] = dict(sorted(kinds.items()))
        counts.update(kinds)
        result["files"].append(info)
    result["aggregate_kinds"] = dict(sorted(counts.items()))
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsh-home", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        value = summarize(args.dsh_home.resolve())
    except (FileNotFoundError, PermissionError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(value, ensure_ascii=False, indent=2))
    if value["file_count"] == 0:
        print("ERROR: no native Session JSONL yet; not evidence of a real run", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
