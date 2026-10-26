#!/usr/bin/env python3
"""One-time, reproducible migration of processed Markdown from ingest2md.

Runs inside a checked-out destination repository and reads a separate checked-out
ingest2md source. Never modifies source repository contents.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

BUSINESS = ("从探图到行动", "对话孙宇晨", "小生意", "E146.")
LIFE = ("孕35周", "待产包")
CAREER = ("面试", "简历", "offer", "看看行情", "直播答疑", "武汉", "深圳30k",
          "上海35K", "重庆50k", "杭州阿里技术支持", "西安35k", "教授",
          "字节外包", "实战面试", "真题", "招聘", "就业")
RAG = ("rag", "bm25", "rerank", "topk", "pgvector", "embedding", "召回",
       "向量", "知识库", "检索", "查询流程", "数据中台")
MODEL = ("llm", "模型微调", "推理引擎", "大模型", "本地部署", "模型服务",
         "量化", "降维", "hugging face", "预填充", "token")
ENTERPRISE = ("客服", "销售考核", "自媒体运营", "素材管理", "rtc",
              "直播切片项目")
AGENT = ("agent", "agengt", "langchain", "mcp", "skills", "意图识别",
         "human-in-the-loop", "本体论")
def classify(name: str) -> tuple[str, str]:
    low = name.lower()
    if any(s.lower() in low for s in LIFE):
        return "archive", "life"
    if any(s.lower() in low for s in BUSINESS):
        return "archive", "business"
    # Technical depth takes precedence over a video's incidental "interview" label.
    if any(s in low for s in RAG):
        return "harness", "rag"
    if "意图识别" in low:
        return "harness", "agent-runtime"
    if any(s in low for s in MODEL):
        return "harness", "model-platform"
    if any(s in low for s in ENTERPRISE):
        return "harness", "enterprise-ai"
    # Job-market examples with a named city / salary go to the AI career archive.
    if any(s.lower() in low for s in ("看看行情", "武汉", "深圳30k", "上海35k",
                                     "重庆50k", "杭州阿里技术支持", "西安35k",
                                     "字节外包", "深信服18k", "求职", "简历", "直播答疑")):
        return "harness", "ai-career"
    if any(s in low for s in AGENT):
        return "harness", "agent-runtime"
    if any(s.lower() in low for s in CAREER):
        return "harness", "ai-career"
    # Generic lecture titles in the current source batch are LLM/AI-related.
    if any(s in low for s in ("评测集", "直播", "ai", "答疑", "项目")):
        return "harness", "enterprise-ai"
    return "archive", "inbox"

def target_path(src: Path, classification: str) -> str:
    name = src.name
    if name == "README.md":
        return "materials/_migration/output-Refinement-README.md"
    if name == "PROCESSING_INDEX.md":
        return "materials/_migration/output-Learning-PROCESSING_INDEX.md"
    if src.parent.name == "output-Learning":
        stem = re.sub(r"__(DeepRead|Learning)\.md$", "", name)
        suffix = "deep-read.md" if name.endswith("__DeepRead.md") else "learning.md"
        if stem == name:
            stem = name[:-3]
    else:
        stem, suffix = name[:-3], "refinement.md"
    if classification.startswith("materials/"):
        return f"{classification}/{stem}/{suffix}"
    return f"{classification}/{stem}/{suffix}"

def relink(text: str) -> str:
    # Keep relative source links functional after moving to a different repo.
    return text.replace("../output/", "https://github.com/leecolin2023/ingest2md/blob/main/output/")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=("harness", "archive"), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    dest_root = args.root.resolve()
    source = args.source.resolve()
    src_commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    entries = []
    selected = []
    for directory in ("output-Refinement", "output-Learning"):
        for src in sorted((source / directory).glob("*.md")):
            is_meta = src.name in ("README.md", "PROCESSING_INDEX.md")
            destination, topic = ("harness", "_migration") if is_meta else classify(src.name)
            if destination != args.target:
                continue
            prefix = f"materials/{topic}" if destination == "harness" else topic
            relative_dest = target_path(src, prefix)
            selected.append((src, relative_dest))
    used = set()
    for src, relative_dest in selected:
        if relative_dest in used:
            raise RuntimeError(f"Destination collision: {relative_dest}")
        used.add(relative_dest)
        raw = src.read_bytes()
        content = relink(raw.decode("utf-8"))
        output = dest_root / relative_dest
        if output.exists() and output.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Refusing to overwrite existing material: {relative_dest}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        entries.append({
            "source_path": str(src.relative_to(source)),
            "target_path": relative_dest,
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "target_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        })
    # Prune only files recorded in the previous manifest, and only when their
    # digest still matches. Never delete user-edited material.
    manifest_path = (
        dest_root / "materials" / "_migration" / "MIGRATION_MANIFEST.json"
        if args.target == "harness" else dest_root / "MIGRATION_MANIFEST.json"
    )
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        new_paths = set(used)
        for item in previous.get("files", []):
            stale = item["target_path"]
            if stale not in new_paths:
                file_path = (dest_root / stale).resolve()
                if not file_path.is_relative_to(dest_root):
                    raise RuntimeError("Invalid prior manifest path")
                if file_path.exists():
                    digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
                    if digest != item["target_sha256"]:
                        raise RuntimeError(f"Refusing to delete edited file: {stale}")
                    file_path.unlink()
    if args.target == "archive":
        (dest_root / "inbox").mkdir(exist_ok=True)
        (dest_root / "inbox" / ".gitkeep").touch()
    manifest_path = (
        dest_root / "materials" / "_migration" / "MIGRATION_MANIFEST.json"
        if args.target == "harness" else dest_root / "MIGRATION_MANIFEST.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"source_repo": "leecolin2023/ingest2md",
                    "source_commit": src_commit,
                    "target": args.target,
                    "count": len(entries),
                    "files": entries}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"{args.target}: {len(entries)} files; source={src_commit}")
    print(json.dumps({k: len([e for e in entries if e["target_path"].startswith(k)])
                      for k in ("materials/rag/", "materials/model-platform/", "materials/agent-runtime/",
                                "materials/enterprise-ai/", "materials/ai-career/",
                                "business/", "life/", "inbox/")}, ensure_ascii=False))
if __name__ == "__main__":
    main()
