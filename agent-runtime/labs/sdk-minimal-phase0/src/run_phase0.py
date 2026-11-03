"""Run a small observable SDK turn INSIDE a separate isolated Docker container.

sdk-minimal is danger-full-access inside the process; cwd alone is not sandbox.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
from importlib import metadata
import json
import os
from pathlib import Path
import sys

DEFAULT_PROMPT = (
    "这是一个隔离工作区实验。请先使用 bash 工具执行 `pwd`，再执行 `ls -la .`。"
    "只检查当前目录；不访问上级目录、环境变量或网络，也不修改文件。"
    "请用中文说明你实际调用的工具及返回结果；工具不可用就如实说明，"
    "不要编造执行记录。"
)


def event_kind(event: object) -> str:
    """Only structural labels, never payload content."""
    if isinstance(event, dict):
        for key in ("kind", "type", "event_type"):
            if isinstance(event.get(key), str):
                return event[key]
        nested = event.get("event")
        if isinstance(nested, dict):
            return event_kind(nested)
    else:
        for name in ("kind", "type", "event_type"):
            value = getattr(event, name, None)
            if isinstance(value, str):
                return value
    return type(event).__name__


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--dsh-home", type=Path, required=True)
    p.add_argument("--patch", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--session-id", required=True)
    p.add_argument("--model", default=os.environ.get("DSH_MODEL", "deepseek-v4-flash"))
    p.add_argument("--prompt", default=DEFAULT_PROMPT)
    args = p.parse_args(argv)

    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        print("ERROR: DEEPSEEK_API_KEY missing; no model request attempted", file=sys.stderr)
        return 2
    workspace = args.workspace.resolve(strict=True)
    home = args.dsh_home.resolve(strict=True)
    patch = args.patch.resolve(strict=True)
    if not (workspace.is_dir() and home.is_dir() and patch.is_file()):
        print("ERROR: workspace, dsh-home and patch must exist", file=sys.stderr)
        return 2
    if workspace == home or workspace.is_relative_to(home) or home.is_relative_to(workspace):
        print("ERROR: workspace and dsh-home must be separate", file=sys.stderr)
        return 2

    from deepseek_harness import DeepSeekHarness
    started = datetime.now(timezone.utc)
    with DeepSeekHarness(
        provider="deepseek-official",
        model=args.model,
        max_tokens=4096,
        cwd=str(workspace),
        dsh_home=str(home),
        profile="sdk-minimal",
        patches=(str(patch),),
    ) as harness:
        result = harness.run(args.prompt, session_id=args.session_id)
    finished = datetime.now(timezone.utc)

    kinds = Counter(event_kind(e) for e in result.events)
    record = {
        "observed_at_utc": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "session_id": result.session_id,
        "provider": "deepseek-official",
        "model": args.model,
        "profile": "sdk-minimal",
        "sdk_version": metadata.version("deepseek-harness-sdk"),
        "finish_reason": result.finish_reason,
        "root_event_count": len(result.events),
        "notification_count": len(result.notifications),
        "root_event_kinds": dict(sorted(kinds.items())),
        "final_response_length": len(result.final_response or ""),
        "session_log_directory": str(home / "sessions"),
        "session_log_upload_disabled_by_patch": True,
        "caveat": "Metadata alone does not prove tool execution; verify native Session events.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SESSION_ID={result.session_id}")
    print(f"FINISH_REASON={result.finish_reason}")
    print(f"ROOT_EVENTS={len(result.events)}  NOTIFICATIONS={len(result.notifications)}")
    print(f"METADATA={args.output}")
    print("FINAL_RESPONSE_START")
    print(result.final_response or "")
    print("FINAL_RESPONSE_END")
    if result.finish_reason not in (None, "completed"):
        print("ERROR: agent did not report completed; inspect Session logs", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
