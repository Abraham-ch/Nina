"""Evaluate the NINA analyst on docs/reference/analyst_eval.json against the configured dataset.

Uses the engine the server would use (Claude when ANTHROPIC_API_KEY is set, otherwise deterministic) and
writes data/reports/analyst_eval_<engine>_<timestamp>.json with every answer for review, plus a summary:

* traced: share of answers whose figures all appear in the tool results;
* abstention: out-of-scope items declined in the first sentence and answered without data tools, and in-scope
  items answered with them;
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
REFUSAL = ("cannot", "does not", "do not", "can't", "no puedo", "no puede", "no pronostica", "no mide", "no tiene", "no da",
           "no atribuye", "no usa")


def first_sentence_declines(answer: str) -> bool:
    first = answer.strip().split(". ")[0].lower()
    return any(marker in first for marker in REFUSAL)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine", choices=["auto", "deterministic"], default="auto")
    parser.add_argument("--limit", type=int, default=0, help="only the first N items")
    parser.add_argument("--abstain-only", action="store_true", help="only the out-of-scope items")
    parser.add_argument("--ids", nargs="*", default=None, help="only these item ids")
    args = parser.parse_args()
    if args.engine == "deterministic":
        os.environ["NINA_ANALYST_ENGINE"] = "deterministic"

    from nina import analyst
    from nina.analyst import AnalystQuestion, ask, engine_name
    from nina.config import DATA

    spec = json.loads((ROOT / "docs/reference/analyst_eval.json").read_text(encoding="utf-8"))
    items = [i for i in spec["items"] if (i["abstain"] or not args.abstain_only) and (not args.ids or i["id"] in args.ids)]
    items = items[: args.limit or None]
    engine = engine_name()
    rows = []
    for item in items:
        started = time.perf_counter()
        sessions: list = []
        original = analyst.Session.__init__

        def tracked(self, *a, _orig=original, _seen=sessions, **k):
            _orig(self, *a, **k)
            _seen.append(self)

        analyst.Session.__init__ = tracked
        try:
            result = ask(AnalystQuestion(question=item["question"], language=item["language"], context=spec["context"]))
        finally:
            analyst.Session.__init__ = original
        usage: dict[str, int] = {}
        for session in sessions:
            for key, value in session.usage.items():
                usage[key] = usage.get(key, 0) + value
        cost = analyst.question_cost(usage, result["model"] or analyst.model_name()) if usage else None
        elapsed = time.perf_counter() - started
        called = {tool["name"] for tool in result["tools"]}
        if item["abstain"]:
            abstention_ok = not (called & DATA_TOOLS) and first_sentence_declines(result["answer"])
        else:
            abstention_ok = bool(called & (DATA_TOOLS | {"method_notes"}))
        rows.append({
            "id": item["id"], "question": item["question"], "engine": result["engine"], "notice": result["notice"],
            "seconds": round(elapsed, 2), "traced": result["verification"]["passed"],
            "unverified": result["verification"]["unverified"], "abstention_ok": abstention_ok,
            "tools_ok": item["abstain"] or set(item["tools"]) <= called, "tools": sorted(called),
            "answer": result["answer"], "usage": usage, "cost_usd": cost,
            # An answerable question needs an explanation, not only a chart or a button.
            "substantive": item["abstain"] or len(result["answer"]) >= 250,
        })
        print(f"{item['id']:<24} {result['engine']:<13} {elapsed:5.1f}s traced={rows[-1]['traced']!s:<5} "
              f"abstention={abstention_ok!s:<5} tools={sorted(called)}")

    def share(key: str) -> float:
        return round(sum(bool(r[key]) for r in rows) / len(rows), 3) if rows else 0.0

    summary = {
        "engine": engine, "items": len(rows), "traced": share("traced"), "abstention": share("abstention_ok"),
        "tools": share("tools_ok"), "substantive": share("substantive"), "fell_back": sum(r["engine"] != engine for r in rows),
        "median_seconds": statistics.median(r["seconds"] for r in rows) if rows else None,
        "model": os.getenv("NINA_ANALYST_MODEL") or "claude-sonnet-5-5",
        "cost_usd_total": round(sum(r["cost_usd"] or 0 for r in rows), 4),
        "cost_usd_median_per_question": round(statistics.median(r["cost_usd"] or 0 for r in rows), 5) if rows else None,
    }
    folder = DATA / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = folder / f"analyst_eval_{engine}_{stamp}.json"
    path.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Written: {path}")
    return 0 if summary["traced"] == 1.0 and summary["abstention"] == 1.0 and summary["substantive"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
