"""
Eval Runner: Batch evaluation with two-layer failure attribution

Usage:
  python -m eval.runner                          # run all tasks
  python -m eval.runner --level 1                # only level-1 tasks
  python -m eval.runner --task nav_001           # single task
  python -m eval.runner --tasks eval/tasks.json  # custom task file
"""

import asyncio
import argparse
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

import base64
from openai import OpenAI
from core.executor import Executor
from core.planner import VisionPlanner
from core.orchestrator import Orchestrator
from eval.diagnose import diagnose_task, generate_report, print_report


# ─────────────────────────────────────────
# Success checkers
# ─────────────────────────────────────────

def check_programmatic(final_url: str, checker: dict) -> bool:
    """
    Deterministic URL-based success check.
    Handles: url_contains, url_domain, url_not_contains
    """
    checker_type = checker.get('type')

    if checker_type == 'url_contains':
        return checker['value'] in final_url

    if checker_type == 'url_domain':
        return checker['domain'] in final_url

    if checker_type == 'url_not_contains':
        return checker['value'] not in final_url

    return False


async def check_llm_judge(
    screenshot_base64: str,
    task_goal: str,
    hint: str,
    client: OpenAI
) -> tuple[bool, str]:
    """
    Use GPT-4o to judge task success from screenshot.
    Returns (success: bool, reason: str)
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"""You are evaluating whether a web agent successfully completed a task.

Task goal: {task_goal}
Hint: {hint}

Look at the screenshot carefully and answer:
- Did the agent successfully complete the task?
- Reply ONLY with valid JSON: {{"result": "SUCCESS" or "FAILURE", "reason": "one sentence"}}
- SUCCESS only if the goal is clearly achieved on screen
- FAILURE if still on wrong page, goal not met, or unclear"""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_base64}",
                            "detail": "high"
                        }
                    }
                ]
            }],
            max_tokens=100,
            temperature=0
        )

        raw = response.choices[0].message.content.strip()
        # Strip markdown fences if present
        raw = raw.replace('```json', '').replace('```', '').strip()
        parsed = json.loads(raw)
        success = parsed.get('result', '').upper() == 'SUCCESS'
        reason = parsed.get('reason', '')
        return success, reason

    except Exception as e:
        print(f"⚠️  LLM judge failed: {e}")
        return False, f"Judge error: {e}"


def load_screenshot_base64(run_result: dict) -> tuple[str, str]:
    """
    Load the final screenshot from disk.
    Returns (base64_string, path_used).

    Strategy: use steps_taken to find the last after-screenshot.
    Falls back to the last before-screenshot if after not found.
    """
    steps_taken = run_result.get('steps_taken', 0)
    screenshots_dir = Path("screenshots")

    # Primary: last after-screenshot
    candidates = [
        screenshots_dir / f"step_{steps_taken:02d}_after.png",
        screenshots_dir / f"step_{steps_taken:02d}_before.png",
    ]

    # Also try steps_taken - 1 in case the final step only saved before
    if steps_taken > 1:
        candidates.append(screenshots_dir / f"step_{steps_taken - 1:02d}_after.png")

    for path in candidates:
        if path.exists():
            import base64
            with open(path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8'), str(path)

    return '', ''


async def evaluate_success(
    run_result: dict,
    task: dict,
    client: OpenAI
) -> tuple[bool, str]:
    """
    Determine task success using the appropriate checker.
    Returns (success, reason).

    For url_contains: uses final_url from run_result.
    For llm_judge: reads the last saved screenshot from disk.
    """
    checker = task.get('checker', {})
    checker_type = checker.get('type')

    # ── programmatic check ────────────────────────────────────
    if checker_type != 'llm_judge':
        final_url = run_result.get('final_url', '')

        # final_url is only set when agent says 'done'
        # if task ended via max_steps/failure, pull url from last history entry
        if not final_url:
            history = run_result.get('history', [])
            if history:
                final_url = history[-1].get('url_after', '')

        success = check_programmatic(final_url, checker)
        reason = f"URL check ({checker_type}): {final_url}"
        return success, reason

    # ── llm judge: read screenshot from disk ─────────────────
    screenshot_b64, screenshot_path = load_screenshot_base64(run_result)

    if not screenshot_b64:
        steps = run_result.get('steps_taken', 0)
        return False, f"Screenshot not found (steps_taken={steps})"

    print(f"   📸 Using screenshot: {screenshot_path}")

    return await check_llm_judge(
        screenshot_base64=screenshot_b64,
        task_goal=task['goal'],
        hint=checker.get('hint', ''),
        client=client
    )


# ─────────────────────────────────────────
# Single task runner
# ─────────────────────────────────────────

async def run_single_task(
    task: dict,
    model: str = "gpt-4o-mini",
    max_steps: int = 10,
    headless: bool = True,
    client: Optional[OpenAI] = None,
) -> dict:
    """
    Run one task end-to-end and return a result dict ready for diagnosis.

    Screenshots are saved to screenshots/ during the run.
    evaluate_success reads the final screenshot from there.
    The screenshots/ directory is cleared before each task to avoid
    step numbers from a previous task bleeding into the next.
    """
    print(f"\n{'─'*60}")
    print(f"▶ Task [{task['id']}] L{task['level']}: {task['goal'][:70]}")
    print(f"{'─'*60}")

    # Clear screenshots dir so step numbers are always relative to this task
    screenshots_dir = Path("screenshots")
    if screenshots_dir.exists():
        for f in screenshots_dir.glob("step_*.png"):
            f.unlink()

    executor = Executor(headless=headless, use_vision=True)
    planner  = VisionPlanner(model=model)
    orchestrator = Orchestrator(executor, planner)

    run_result = await orchestrator.run(
        user_goal=task['goal'],
        start_url=task['start_url'],
        max_steps=max_steps
    )
    # browser is closed here (orchestrator.stop() called in finally)

    if client is None:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # evaluate_success reads screenshots from disk — no live browser needed
    success, judge_reason = await evaluate_success(run_result, task, client)

    run_result['task'] = task
    run_result['success'] = success
    run_result['judge_reason'] = judge_reason

    status = "✅" if success else "❌"
    print(f"{status} Task {task['id']}: {judge_reason}")

    # Archive this task's screenshots so they aren't deleted next iteration
    archive_dir = screenshots_dir / task['id']
    archive_dir.mkdir(parents=True, exist_ok=True)
    for f in screenshots_dir.glob("step_*.png"):
        f.rename(archive_dir / f.name)

    return run_result


# ─────────────────────────────────────────
# Batch runner
# ─────────────────────────────────────────

async def run_eval(
    tasks_path: str = "eval/tasks.json",
    level_filter: Optional[int] = None,
    task_id_filter: Optional[str] = None,
    model: str = "gpt-4o-mini",
    max_steps: int = 10,
    headless: bool = True,
    output_dir: str = "eval/results"
) -> dict:
    """
    Run the full evaluation and generate a report.
    """
    # Load tasks
    with open(tasks_path) as f:
        all_tasks = json.load(f)

    # Filter
    if task_id_filter:
        tasks = [t for t in all_tasks if t['id'] == task_id_filter]
    elif level_filter is not None:
        tasks = [t for t in all_tasks if t['level'] == level_filter]
    else:
        tasks = all_tasks

    if not tasks:
        print("No tasks matched the filter.")
        return {}

    print(f"\n🚀 Starting evaluation: {len(tasks)} tasks, model={model}")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Run tasks sequentially (browser sessions can't easily share state)
    task_results = []
    for task in tasks:
        result = await run_single_task(
            task=task,
            model=model,
            max_steps=max_steps,
            headless=headless,
            client=client
        )
        task_results.append(result)

    # Diagnose each task
    task_diagnoses = [diagnose_task(r) for r in task_results]

    # Generate report
    report = generate_report(task_diagnoses)
    print_report(report)

    # Save results
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report_path = f"{output_dir}/report_{timestamp}.json"
    with open(report_path, 'w') as f:
        json.dump({
            'report': report,
            'task_diagnoses': task_diagnoses,
        }, f, indent=2, default=str)

    print(f"\n💾 Report saved: {report_path}")
    return report


# ─────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Web Agent Evaluator")
    parser.add_argument('--tasks',   default='eval/tasks.json', help='Path to tasks JSON')
    parser.add_argument('--level',   type=int, default=None,    help='Filter by task level')
    parser.add_argument('--task',    default=None,              help='Run a single task by ID')
    parser.add_argument('--model',   default='gpt-4o-mini',     help='LLM model to use')
    parser.add_argument('--steps',   type=int, default=10,      help='Max steps per task')
    parser.add_argument('--headless', action='store_true',      help='Run browser headless')
    parser.add_argument('--output',  default='eval/results',    help='Output directory')
    args = parser.parse_args()

    asyncio.run(run_eval(
        tasks_path=args.tasks,
        level_filter=args.level,
        task_id_filter=args.task,
        model=args.model,
        max_steps=args.steps,
        headless=args.headless,
        output_dir=args.output
    ))


if __name__ == '__main__':
    main()