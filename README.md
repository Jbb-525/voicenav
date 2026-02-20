# Web Agent

An LLM-powered web automation agent with a structured evaluation framework for diagnosing failure modes.

## Architecture

```
User Goal
    │
    ▼
┌─────────────────────────────────────────┐
│              Orchestrator               │
│         (Observe → Think → Act)         │
│                                         │
│  ┌──────────┐      ┌─────────────────┐  │
│  │ Executor │      │     Planner     │  │
│  │          │      │                 │  │
│  │Playwright│      │ TextPlanner or  │  │
│  │AXTree    │─────▶│ VisionPlanner   │  │
│  │Screenshot│      │ (GPT-4o)        │  │
│  └──────────┘      └─────────────────┘  │
└─────────────────────────────────────────┘
```

**Executor** (`core/executor.py`) — Manages a Playwright browser instance. Extracts page state via the Accessibility Tree (AXTree) and optionally screenshots. Supports actions: `goto`, `click`, `type`, `scroll`, `select`, `done`.

**Planner** (`core/planner.py`) — Given the current page state and action history, uses an LLM to output a structured decision: a high-level milestone plan, the current step, a reasoning trace, and the next action.

- `TextPlanner` — AXTree only
- `VisionPlanner` — AXTree + screenshot

**Orchestrator** (`core/orchestrator.py`) — Runs the OTA loop, records per-step snapshots (`elements_before`, `url_before`, `url_after`) needed for post-hoc evaluation.

## Evaluation Framework

Tasks are categorised by complexity:

| Level | Type | Example | Checker |
|-------|------|---------|---------|
| 1 | Navigation | Go to Hacker News | `url_contains` |
| 2 | Search & Retrieve | Find Nike sustainability report | `llm_judge` |
| 3 | Compare & Select | Cheapest pencil on Amazon | `llm_judge` |

### Two-Layer Failure Attribution

Rather than reporting only a final success rate, every failed run is attributed to one of two layers:

```
Layer A — Reasoning
  The model described a target that does not exist on the page,
  or navigated in the wrong direction.

  Symptoms:
    target_not_found   target string absent from AXTree elements
    no_page_change     click succeeded but URL did not change
    planning_failed    all steps executed cleanly but goal not met

Layer B — Execution
  The target was present in the AXTree but Playwright failed
  to interact with it.

  Error types (from raw Playwright errors):
    timeout            element present but not ready in time
    not_visible        element off-screen or hidden
    element_detached   dynamic page replaced element mid-action
    click_intercepted  element covered by overlay
    ambiguous_target   name matched multiple elements
```

The attribution logic in `eval/diagnose.py`:

```
For each failed step:
  1. Fuzzy-match action.target against elements_before
  2. Classify the raw error message → error_type
  3. If matched AND error_type not in {element_not_found, ambiguous_target}
       → Layer B  (found it, couldn't click it)
     Else
       → Layer A  (model got the target wrong)
  4. If all steps succeeded but task still failed
       → Layer A / planning_failed
```

### Success Checking

`url_contains` is only used when the URL itself *is* the goal (Level 1 navigation tasks). All other tasks use an LLM judge (GPT-4o) that reads the **final screenshot from disk** — the browser session is already closed at judgment time.

```python
# screenshots are archived per-task after each run
screenshots/
  nav_001/step_01_after.png ...
  search_001/step_03_after.png ...
```

## Setup

```bash
pip install playwright openai playwright-stealth python-dotenv
playwright install chromium

cp .env.example .env   # add OPENAI_API_KEY
```

## Usage

```bash
# run full eval
python -m eval.runner

# single task (useful for debugging)
python -m eval.runner --task compare_001

# level filter
python -m eval.runner --level 2

# stronger model
python -m eval.runner --model gpt-4o --steps 15
```

## Sample Report Output

```
══════════════════════════════════════════════════════════════
EVALUATION REPORT 202602200542
══════════════════════════════════════════════════════════════
Total Tasks:    10
Success Rate:   50%  (5/10)

By Level:
  Level 1: 3/3 = 100%  ✅
  Level 2: 2/4 =  50%  ⚠️
  Level 3: 0/3 =   0%  ❌

Failure Attribution (5 failures):
  Layer A (Reasoning):  4  (80%)  → fix prompt / observation
  Layer B (Execution):  1  (20%)  → fix executor / wait strategy

Layer B error type breakdown:
  timeout          2  → increase wait time
  not_visible      1  → scroll or viewport issue
  element_detached 1  → dynamic page, add explicit wait
══════════════════════════════════════════════════════════════
```

## Project Structure

```
core/
  executor.py       browser control, AXTree extraction, screenshot
  planner.py        TextPlanner, VisionPlanner, action schema
  orchestrator.py   OTA loop, per-step recording

eval/
  tasks.json        10 benchmark tasks across 3 levels
  diagnose.py       two-layer attribution, fuzzy matching, error classification
  runner.py         batch runner, success checker, report generation

prompt/
  system_prompt.md  agent system prompt
```
