"""Evaluate the NINA analyst on docs/reference/analyst_eval.json against the configured dataset.

Uses the engine the server would use (Claude when ANTHROPIC_API_KEY is set, otherwise deterministic) and
writes data/reports/analyst_eval_<engine>_<timestamp>.json with every answer for review, plus a summary:

* traced: share of answers whose figures all appear in the tool results;
* abstention: out-of-scope items answered without data tools, and in-scope items answered with them;
* tools: in-scope items that called every expected tool;
* latency per answer.

Model runs cost money: each item is one conversation with a few tool calls. Usage:

    .venv\\Scripts\\python.exe scripts/eval_analyst.py [--engine deterministic] [--limit 5]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA_TOOLS = {"territory_profile", "activity_series", "compare_departments", "validation_summary"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine", choices=["auto", "deterministic"], default="auto")
    parser.add_argument("--limit", type=int, default=0, help="only the first N items")
    args = parser.parse_args()
    if args.engine == "deterministic":
        os.environ["NINA_ANALYST_ENGINE"] = "deterministic"

    from nina.analyst import AnalystQuestion, ask, engine_name
    from nina.config import DATA

    spec = json.loads((ROOT / "docs/reference/analyst_eval.json").read_text(encoding="utf-8"))
    items = spec["items"][: args.limit or None]
    engine = engine_name()
    rows = []
    for item in items:
        started = time.perf_counter()
        result = ask(AnalystQuestion(question=item["question"], language=item["language"], context=spec["context"]))
        elapsed = time.perf_counter() - started
        called = {tool["name"] for tool in result["tools"]}
        if item["abstain"]:
            abstention_ok = not (called & DATA_TOOLS)
        else:
            abstention_ok = bool(called & (DATA_TOOLS | {"method_notes"}))
        rows.append({
            "id": item["id"], "question": item["question"], "engine": result["engine"], "notice": result["notice"],
            "seconds": round(elapsed, 2), "traced": result["verification"]["passed"],
            "unverified": result["verification"]["unverified"], "abstention_ok": abstention_ok,
            "tools_ok": item["abstain"] or set(item["tools"]) <= called, "tools": sorted(called),
            "answer": result["answer"],
        })
        print(f"{item['id']:<24} {result['engine']:<13} {elapsed:5.1f}s traced={rows[-1]['traced']!s:<5} "
              f"abstention={abstention_ok!s:<5} tools={sorted(called)}")

    def share(key: str) -> float:
        return round(sum(bool(r[key]) for r in rows) / len(rows), 3) if rows else 0.0

    summary = {
        "engine": engine, "items": len(rows), "traced": share("traced"), "abstention": share("abstention_ok"),
        "tools": share("tools_ok"), "fell_back": sum(r["engine"] != engine for r in rows),
        "median_seconds": statistics.median(r["seconds"] for r in rows) if rows else None,
    }
    folder = DATA / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = folder / f"analyst_eval_{engine}_{stamp}.json"
    path.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Written: {path}")
    return 0 if summary["traced"] == 1.0 and summary["abstention"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
