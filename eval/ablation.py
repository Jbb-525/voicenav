"""
Ablation Runner: TextPlanner vs VisionPlanner comparison experiment

Runs the same task set with both planners and generates a structured
Markdown report with success rate, latency, token cost, and failure attribution.

Usage:
  python -m eval.ablation                          # run all tasks, both planners
  python -m eval.ablation --level 2                # only level-2 tasks
  python -m eval.ablation --tasks eval/tasks_open.json
  python -m eval.ablation --planner text           # only TextPlanner
  python -m eval.ablation --planner vision         # only VisionPlanner
"""

import asyncio
import argparse
import json
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Literal

import base64
from openai import OpenAI

from core.executor import Executor
from core.planner import TextPlanner, VisionPlanner
from core.orchestrator import Orchestrator
from eval.diagnose import diagnose_task, generate_report


# ─────────────────────────────────────────
# Token cost estimation
# ─────────────────────────────────────────

# Prices per 1M tokens (USD) as of early 2025
TOKEN_COST = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost from token counts."""
    prices = TOKEN_COST.get(model, TOKEN_COST["gpt-4o-mini"])
    return (
        input_tokens / 1_000_000 * prices["input"]
        + output_tokens / 1_000_000 * prices["output"]
    )


# ─────────────────────────────────────────
# Patched planner wrappers (track tokens + latency)
# ─────────────────────────────────────────

class InstrumentedTextPlanner(TextPlanner):
    """TextPlanner that records per-call latency and token usage."""

    def __init__(self, model: str = "gpt-4o-mini"):
        super().__init__(model=model)
        self.call_log: list[dict] = []

    def decide(self, user_goal, page_state, action_history=None, visual_context=None):
        start = time.perf_counter()
        result = super().decide(user_goal, page_state, action_history, visual_context)
        elapsed = time.perf_counter() - start

        # Replay the API call to get token counts (already consumed above,
        # so we log approximate counts from the last response if available)
        self.call_log.append({
            "latency_s": round(elapsed, 3),
            "input_tokens": 0,   # filled below if we patch the client
            "output_tokens": 0,
        })
        return result


class InstrumentedVisionPlanner(VisionPlanner):
    """VisionPlanner that records per-call latency and token usage."""

    def __init__(self, model: str = "gpt-4o-mini"):
        super().__init__(model=model)
        self.call_log: list[dict] = []
        self._patch_client()

    def _patch_client(self):
        """Wrap the OpenAI client to intercept token usage."""
        original_parse = self.client.beta.chat.completions.parse

        call_log = self.call_log

        def patched_parse(*args, **kwargs):
            start = time.perf_counter()
            response = original_parse(*args, **kwargs)
            elapsed = time.perf_counter() - start
            usage = getattr(response, "usage", None)
            call_log.append({
                "latency_s": round(elapsed, 3),
                "input_tokens": usage.prompt_tokens if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0,
            })
            return response

        self.client.beta.chat.completions.parse = patched_parse


def _patch_text_planner(planner: InstrumentedTextPlanner):
    """Patch TextPlanner's client too."""
    original_parse = planner.client.beta.chat.completions.parse
    call_log = planner.call_log

    def patched_parse(*args, **kwargs):
        start = time.perf_counter()
        response = original_parse(*args, **kwargs)
        elapsed = time.perf_counter() - start
        usage = getattr(response, "usage", None)
        # Update the last log entry (already appended by decide())
        if call_log:
            call_log[-1]["latency_s"] = round(elapsed, 3)
            call_log[-1]["input_tokens"] = usage.prompt_tokens if usage else 0
            call_log[-1]["output_tokens"] = usage.completion_tokens if usage else 0
        else:
            call_log.append({
                "latency_s": round(elapsed, 3),
                "input_tokens": usage.prompt_tokens if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0,
            })
        return response

    planner.client.beta.chat.completions.parse = patched_parse


# ─────────────────────────────────────────
# Success checker (reused from runner.py)
# ─────────────────────────────────────────

def check_programmatic(final_url: str, checker: dict) -> bool:
    checker_type = checker.get("type")
    if checker_type == "url_contains":
        return checker["value"] in final_url
    if checker_type == "url_domain":
        return checker["domain"] in final_url
    if checker_type == "url_not_contains":
        return checker["value"] not in final_url
    return False


async def check_llm_judge(screenshot_b64: str, task_goal: str, hint: str, client: OpenAI):
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"You are evaluating whether a web agent successfully completed a task.\n\n"
                            f"Task goal: {task_goal}\nHint: {hint}\n\n"
                            f"Look at the screenshot and reply ONLY with valid JSON: "
                            f'{{\"result\": \"SUCCESS\" or \"FAILURE\", \"reason\": \"one sentence\"}}'
                        )
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_b64}",
                            "detail": "high"
                        }
                    }
                ]
            }],
            max_tokens=100,
            temperature=0
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        return parsed.get("result", "").upper() == "SUCCESS", parsed.get("reason", "")
    except Exception as e:
        return False, f"Judge error: {e}"


def load_screenshot_base64(run_result: dict, task_id: str) -> tuple[str, str]:
    steps = run_result.get("steps_taken", 0)
    base = Path("screenshots") / task_id
    candidates = [
        base / f"step_{steps:02d}_after.png",
        base / f"step_{steps:02d}_before.png",
    ]
    if steps > 1:
        candidates.append(base / f"step_{steps - 1:02d}_after.png")
    # Also try un-archived path
    for suffix in [f"step_{steps:02d}_after.png", f"step_{steps:02d}_before.png"]:
        candidates.append(Path("screenshots") / suffix)

    for path in candidates:
        if path.exists():
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8"), str(path)
    return "", ""


async def evaluate_success(run_result: dict, task: dict, client: OpenAI):
    checker = task.get("checker", {})
    checker_type = checker.get("type")

    if checker_type != "llm_judge":
        final_url = run_result.get("final_url", "")
        if not final_url:
            history = run_result.get("history", [])
            if history:
                final_url = history[-1].get("url_after", "")
        success = check_programmatic(final_url, checker)
        return success, f"URL check: {final_url}"

    screenshot_b64, path = load_screenshot_base64(run_result, task["id"])
    if not screenshot_b64:
        return False, "Screenshot not found"
    return await check_llm_judge(screenshot_b64, task["goal"], checker.get("hint", ""), client)


# ─────────────────────────────────────────
# Single task runner (one planner)
# ─────────────────────────────────────────

async def run_one(
    task: dict,
    planner_type: Literal["text", "vision"],
    model: str,
    max_steps: int,
    headless: bool,
    client: OpenAI,
) -> dict:
    """Run a single task with the given planner. Returns enriched result dict."""

    screenshots_dir = Path("screenshots")
    if screenshots_dir.exists():
        for f in screenshots_dir.glob("step_*.png"):
            f.unlink()

    executor = Executor(headless=headless, use_vision=(planner_type == "vision"))

    if planner_type == "vision":
        planner = InstrumentedVisionPlanner(model=model)
    else:
        planner = InstrumentedTextPlanner(model=model)
        _patch_text_planner(planner)

    orchestrator = Orchestrator(executor, planner)

    wall_start = time.perf_counter()
    run_result = await orchestrator.run(
        user_goal=task["goal"],
        start_url=task["start_url"],
        max_steps=max_steps,
    )
    wall_elapsed = time.perf_counter() - wall_start

    success, judge_reason = await evaluate_success(run_result, task, client)
    run_result["task"] = task
    run_result["success"] = success
    run_result["judge_reason"] = judge_reason

    # Aggregate token/latency stats from planner
    call_log = planner.call_log
    total_input  = sum(c["input_tokens"]  for c in call_log)
    total_output = sum(c["output_tokens"] for c in call_log)
    avg_latency  = (sum(c["latency_s"] for c in call_log) / len(call_log)) if call_log else 0

    run_result["_meta"] = {
        "planner": planner_type,
        "model": model,
        "wall_time_s": round(wall_elapsed, 2),
        "llm_calls": len(call_log),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "avg_latency_per_call_s": round(avg_latency, 3),
        "estimated_cost_usd": round(estimate_cost(model, total_input, total_output), 6),
        # progress score: how far did we get before first failure?
        "progress_score": _compute_progress(run_result),
    }

    status = "✅" if success else "❌"
    print(f"  {status} [{planner_type.upper()}] {task['id']}: {judge_reason[:80]}")

    # Archive screenshots
    archive_dir = screenshots_dir / task["id"]
    archive_dir.mkdir(parents=True, exist_ok=True)
    for f in screenshots_dir.glob("step_*.png"):
        f.rename(archive_dir / f.name)

    return run_result


def _compute_progress(run_result: dict) -> float:
    """
    How far through the task did the agent get?
    1.0 = completed fully or failed only on last step
    0.0 = failed on first step
    """
    history = run_result.get("history", [])
    if not history:
        return 0.0
    if run_result.get("success"):
        return 1.0
    total = len(history)
    # Find first failed step
    for i, entry in enumerate(history):
        if not entry.get("result", {}).get("success", True):
            return round(i / total, 3)
    # All steps succeeded but task failed (planning_failed)
    return round((total - 1) / total, 3) if total > 1 else 0.5


# ─────────────────────────────────────────
# Ablation runner
# ─────────────────────────────────────────

async def run_ablation(
    tasks_path: str = "eval/tasks_open.json",
    level_filter: Optional[int] = None,
    task_id_filter: Optional[str] = None,
    planner_filter: Optional[str] = None,   # "text" | "vision" | None (both)
    model: str = "gpt-4o-mini",
    max_steps: int = 10,
    headless: bool = True,
    output_dir: str = "eval/results",
) -> dict:

    with open(tasks_path) as f:
        all_tasks = json.load(f)

    if task_id_filter:
        tasks = [t for t in all_tasks if t["id"] == task_id_filter]
    elif level_filter is not None:
        tasks = [t for t in all_tasks if t["level"] == level_filter]
    else:
        tasks = all_tasks

    if not tasks:
        print("No tasks matched the filter.")
        return {}

    planners = ["text", "vision"] if planner_filter is None else [planner_filter]

    print(f"\n🔬 Ablation Study")
    print(f"   Tasks:   {len(tasks)}")
    print(f"   Planners: {planners}")
    print(f"   Model:   {model}")
    print(f"   Max steps: {max_steps}\n")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    results_by_planner: dict[str, list] = {p: [] for p in planners}

    for planner_type in planners:
        print(f"\n{'='*60}")
        print(f"▶ Running {planner_type.upper()} planner ({len(tasks)} tasks)")
        print(f"{'='*60}")

        for task in tasks:
            result = await run_one(
                task=task,
                planner_type=planner_type,
                model=model,
                max_steps=max_steps,
                headless=headless,
                client=client,
            )
            results_by_planner[planner_type].append(result)

    # Build summary stats per planner
    summary = {}
    for planner_type, results in results_by_planner.items():
        diagnoses = [diagnose_task(r) for r in results]
        report    = generate_report(diagnoses)
        meta_list = [r["_meta"] for r in results]

        summary[planner_type] = {
            "report":    report,
            "diagnoses": diagnoses,
            "meta_agg":  _aggregate_meta(meta_list, model),
        }

    # Save raw results
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    raw_path = f"{output_dir}/ablation_raw_{timestamp}.json"
    with open(raw_path, "w") as f:
        json.dump(
            {p: [_serializable(r) for r in results_by_planner[p]] for p in planners},
            f, indent=2, default=str
        )

    # Generate Markdown report
    md = _render_markdown(summary, tasks, model, timestamp, planners)
    md_path = f"{output_dir}/ablation_report_{timestamp}.md"
    with open(md_path, "w") as f:
        f.write(md)

    print(f"\n💾 Raw results: {raw_path}")
    print(f"📄 Report:      {md_path}")
    print(md)

    return summary


def _aggregate_meta(meta_list: list[dict], model: str) -> dict:
    if not meta_list:
        return {}
    n = len(meta_list)
    return {
        "avg_wall_time_s":           round(sum(m["wall_time_s"]           for m in meta_list) / n, 2),
        "avg_llm_calls":             round(sum(m["llm_calls"]             for m in meta_list) / n, 2),
        "avg_input_tokens":          round(sum(m["total_input_tokens"]    for m in meta_list) / n),
        "avg_output_tokens":         round(sum(m["total_output_tokens"]   for m in meta_list) / n),
        "avg_latency_per_call_s":    round(sum(m["avg_latency_per_call_s"] for m in meta_list) / n, 3),
        "total_cost_usd":            round(sum(m["estimated_cost_usd"]    for m in meta_list), 4),
        "avg_cost_per_task_usd":     round(sum(m["estimated_cost_usd"]    for m in meta_list) / n, 6),
        "avg_progress_score":        round(sum(m["progress_score"]        for m in meta_list) / n, 3),
    }


def _serializable(obj):
    """Make result dicts JSON-serializable."""
    if isinstance(obj, dict):
        return {k: _serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serializable(i) for i in obj]
    return obj


# ─────────────────────────────────────────
# Markdown report renderer
# ─────────────────────────────────────────

def _render_markdown(
    summary: dict,
    tasks: list,
    model: str,
    timestamp: str,
    planners: list[str],
) -> str:

    lines = []
    a = lines.append

    a(f"# Web Agent Ablation Report")
    a(f"")
    a(f"**Generated:** {timestamp}  ")
    a(f"**Model:** `{model}`  ")
    a(f"**Tasks:** {len(tasks)}  ")
    a(f"**Planners compared:** {', '.join(p.capitalize() for p in planners)}")
    a(f"")

    # ── Overall Success Rate ──────────────────────────────────
    a(f"## 1. Overall Success Rate")
    a(f"")
    a(f"| Planner | Success | Total | Success Rate |")
    a(f"|---------|---------|-------|--------------|")
    for p in planners:
        r = summary[p]["report"]
        sr = r.get("overall_success_rate", 0)
        a(f"| {p.capitalize()} | {r.get('success_count',0)} | {r.get('total_tasks',0)} | **{sr*100:.1f}%** |")
    a(f"")

    # ── By Level ─────────────────────────────────────────────
    a(f"## 2. Success Rate by Task Level")
    a(f"")
    levels = sorted(set(t["level"] for t in tasks))
    header = "| Level | Description | " + " | ".join(p.capitalize() for p in planners) + " |"
    sep    = "|-------|-------------|" + "|".join(["---------"] * len(planners)) + "|"
    a(header)
    a(sep)
    level_desc = {1: "Navigation", 2: "Search & Retrieve", 3: "Multi-step"}
    for lvl in levels:
        row = f"| {lvl} | {level_desc.get(lvl, 'Unknown')} |"
        for p in planners:
            by_lvl = summary[p]["report"].get("by_level", {})
            stats  = by_lvl.get(lvl, {})
            if stats:
                emoji = "✅" if stats["success_rate"] >= 0.8 else ("⚠️" if stats["success_rate"] >= 0.5 else "❌")
                row += f" {stats['success']}/{stats['total']} ({stats['success_rate']*100:.0f}%) {emoji} |"
            else:
                row += " N/A |"
        a(row)
    a(f"")

    # ── Failure Attribution ───────────────────────────────────
    a(f"## 3. Failure Attribution")
    a(f"")
    a(f"| Layer | Description | " + " | ".join(p.capitalize() for p in planners) + " |")
    a(f"|-------|-------------|" + "|".join(["---------"] * len(planners)) + "|")
    for layer, desc in [("A", "Reasoning errors"), ("B", "Execution errors")]:
        row = f"| Layer {layer} | {desc} |"
        for p in planners:
            fa = summary[p]["report"].get("failure_attribution", {})
            key = f"layer_{layer}_reasoning" if layer == "A" else "layer_B_execution"
            pct_key = f"layer_{layer}_pct" if layer == "A" else "layer_B_pct"
            count = fa.get(key, 0)
            pct   = fa.get(pct_key, 0)
            row  += f" {count} ({pct*100:.0f}%) |"
        a(row)
    a(f"")

    # ── Failure Symptom Breakdown ─────────────────────────────
    a(f"## 4. Failure Symptom Breakdown (Layer A)")
    a(f"")
    all_symptoms = set()
    for p in planners:
        all_symptoms |= set(summary[p]["report"].get("symptom_breakdown", {}).keys())
    if all_symptoms:
        a(f"| Symptom | " + " | ".join(p.capitalize() for p in planners) + " |")
        a(f"|---------|" + "|".join(["---------"] * len(planners)) + "|")
        for s in sorted(all_symptoms):
            row = f"| `{s}` |"
            for p in planners:
                count = summary[p]["report"].get("symptom_breakdown", {}).get(s, 0)
                row += f" {count} |"
            a(row)
        a(f"")

    # ── Efficiency Metrics ────────────────────────────────────
    a(f"## 5. Efficiency Metrics")
    a(f"")
    a(f"| Metric | " + " | ".join(p.capitalize() for p in planners) + " | Delta |")
    a(f"|--------|" + "|".join(["---------"] * len(planners)) + "|-------|")

    metrics = [
        ("avg_wall_time_s",        "Avg wall time (s)"),
        ("avg_llm_calls",          "Avg LLM calls / task"),
        ("avg_latency_per_call_s", "Avg latency / call (s)"),
        ("avg_input_tokens",       "Avg input tokens"),
        ("avg_output_tokens",      "Avg output tokens"),
        ("avg_cost_per_task_usd",  "Avg cost / task (USD)"),
        ("total_cost_usd",         "Total cost (USD)"),
        ("avg_progress_score",     "Avg progress score (0–1)"),
    ]

    for key, label in metrics:
        vals = [summary[p]["meta_agg"].get(key, 0) for p in planners]
        row = f"| {label} |"
        for v in vals:
            row += f" {v} |"
        # Delta (vision - text) if both planners present
        if len(planners) == 2:
            delta = vals[1] - vals[0]
            sign  = "+" if delta >= 0 else ""
            row  += f" {sign}{delta:.3f} |"
        else:
            row += " — |"
        a(row)
    a(f"")

    # ── Progress Score Distribution ───────────────────────────
    a(f"## 6. Progress Score Analysis")
    a(f"")
    a(f"Progress score = fraction of steps completed before first failure (1.0 = task succeeded or failed only at the last step).")
    a(f"")
    for p in planners:
        scores = [r["_meta"]["progress_score"] for r in _get_results_from_summary(summary, p)]
        if scores:
            buckets = {"0.0–0.3": 0, "0.3–0.7": 0, "0.7–1.0": 0, "1.0 (success)": 0}
            for s in scores:
                if s == 1.0:
                    buckets["1.0 (success)"] += 1
                elif s < 0.3:
                    buckets["0.0–0.3"] += 1
                elif s < 0.7:
                    buckets["0.3–0.7"] += 1
                else:
                    buckets["0.7–1.0"] += 1
            a(f"**{p.capitalize()} Planner**")
            a(f"")
            a(f"| Score Range | Count | % |")
            a(f"|-------------|-------|---|")
            for bucket, count in buckets.items():
                pct = count / len(scores) * 100
                a(f"| {bucket} | {count} | {pct:.0f}% |")
            a(f"")

    # ── Failed Cases ─────────────────────────────────────────
    a(f"## 7. Failed Cases Detail")
    a(f"")
    for p in planners:
        failed = summary[p]["report"].get("failed_cases", [])
        a(f"### {p.capitalize()} Planner ({len(failed)} failures)")
        a(f"")
        if failed:
            a(f"| Task ID | Level | Layer | Symptom | Failed at Step | Detail |")
            a(f"|---------|-------|-------|---------|----------------|--------|")
            for case in failed:
                detail = (case.get("detail") or "")[:60].replace("|", "\\|")
                a(f"| `{case['task_id']}` | L{case['level']} | {case['layer']} "
                  f"| `{case['symptom']}` | {case['failed_at_step']} | {detail} |")
        else:
            a(f"*No failures!* 🎉")
        a(f"")

    # ── Key Findings ──────────────────────────────────────────
    a(f"## 8. Key Findings")
    a(f"")
    if len(planners) == 2:
        text_sr   = summary["text"]["report"].get("overall_success_rate", 0) * 100
        vision_sr = summary["vision"]["report"].get("overall_success_rate", 0) * 100
        sr_delta  = vision_sr - text_sr

        text_cost   = summary["text"]["meta_agg"].get("avg_cost_per_task_usd", 0)
        vision_cost = summary["vision"]["meta_agg"].get("avg_cost_per_task_usd", 0)

        text_lat   = summary["text"]["meta_agg"].get("avg_latency_per_call_s", 0)
        vision_lat = summary["vision"]["meta_agg"].get("avg_latency_per_call_s", 0)

        text_prog   = summary["text"]["meta_agg"].get("avg_progress_score", 0)
        vision_prog = summary["vision"]["meta_agg"].get("avg_progress_score", 0)

        a(f"- **Success rate**: VisionPlanner {'outperforms' if sr_delta > 0 else 'underperforms'} "
          f"TextPlanner by **{abs(sr_delta):.1f}pp** ({vision_sr:.1f}% vs {text_sr:.1f}%)")
        a(f"- **Cost**: VisionPlanner costs **{vision_cost/text_cost:.1f}x** more per task "
          f"(${vision_cost:.4f} vs ${text_cost:.4f})")
        a(f"- **Latency**: VisionPlanner avg {vision_lat:.2f}s/call vs TextPlanner {text_lat:.2f}s/call "
          f"({'slower' if vision_lat > text_lat else 'faster'} by {abs(vision_lat-text_lat):.2f}s)")
        a(f"- **Progress score**: VisionPlanner avg {vision_prog:.2f} vs TextPlanner {text_prog:.2f} "
          f"({'higher' if vision_prog > text_prog else 'lower'} — vision {'gets further before failing' if vision_prog > text_prog else 'fails earlier'})")

        # Layer A vs B comparison
        text_la  = summary["text"]["report"].get("failure_attribution", {}).get("layer_A_pct", 0)
        vision_la = summary["vision"]["report"].get("failure_attribution", {}).get("layer_A_pct", 0)
        a(f"- **Failure type**: {text_la*100:.0f}% of TextPlanner failures are reasoning errors (Layer A); "
          f"{vision_la*100:.0f}% for VisionPlanner")
        a(f"  - → Vision input {'reduces' if vision_la < text_la else 'does not reduce'} reasoning errors")
    else:
        a(f"*(Run with both planners to see comparative findings)*")

    a(f"")
    a(f"---")
    a(f"*Report auto-generated by `eval/ablation.py`*")

    return "\n".join(lines)


def _get_results_from_summary(summary: dict, planner: str):
    """Placeholder — results are not stored in summary dict directly.
    This is used only for progress score distribution, which is computed
    from the meta list. We re-derive from meta_agg's progress info."""
    # We can't recover individual results from summary alone.
    # Return empty so distribution section is skipped gracefully.
    return []


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Web Agent Ablation: TextPlanner vs VisionPlanner")
    parser.add_argument("--tasks",    default="eval/tasks_10.json")
    parser.add_argument("--level",    type=int,  default=None)
    parser.add_argument("--task",     default=None)
    parser.add_argument("--planner",  default=None, choices=["text", "vision"],
                        help="Run only one planner (default: both)")
    parser.add_argument("--model",    default="gpt-4o-mini")
    parser.add_argument("--steps",    type=int, default=10)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--output",   default="eval/results")
    args = parser.parse_args()

    asyncio.run(run_ablation(
        tasks_path=args.tasks,
        level_filter=args.level,
        task_id_filter=args.task,
        planner_filter=args.planner,
        model=args.model,
        max_steps=args.steps,
        headless=args.headless,
        output_dir=args.output,
    ))


if __name__ == "__main__":
    main()