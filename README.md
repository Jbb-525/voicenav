# VoiceNav — LLM Web Agent

An LLM-powered browser automation agent with a structured evaluation framework for diagnosing and improving failure modes.

## Demo

<!-- Replace the link below with your video demo URL -->
> 📹 **[Video Demo](#)** — *(upload your demo video and replace `#` with the link)*

---

## Architecture

```
Browser (React UI)
        │  WebSocket (frames + events)
        ▼
┌──────────────────────────────────────┐
│            FastAPI Server            │
│  POST /api/task   WS /ws/{task_id}   │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│            Orchestrator              │
│        Observe → Think → Act         │
│                                      │
│  ┌───────────────┐  ┌─────────────┐  │
│  │   Executor    │  │   Planner   │  │
│  │               │  │             │  │
│  │  Playwright   │─▶│ TextPlanner │  │
│  │  AXTree       │  │    or       │  │
│  │  CDP Screens. │  │VisionPlanner│  │
│  └───────────────┘  └─────────────┘  │
└──────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│         Evaluation Pipeline          │
│   runner.py → diagnose.py → report   │
└──────────────────────────────────────┘
```

---

## Tech Stack

### Backend

| Component | Tech | Role |
|-----------|------|------|
| Web server | FastAPI + Uvicorn | REST API + WebSocket streaming |
| Browser automation | Playwright (async) + playwright-stealth | Page control, AXTree extraction |
| Browser streaming | Chrome DevTools Protocol (CDP Screencast) | Real-time JPEG frame streaming to UI |
| LLM | OpenAI GPT-4o / GPT-4o-mini | Planning and LLM-as-judge evaluation |
| Structured output | Pydantic v2 | Action schema validation |
| Config | python-dotenv | Environment variables |

### Frontend

| Component | Tech | Role |
|-----------|------|------|
| Framework | React 18 + Vite | SPA with HMR |
| Routing | React Router v6 | Chat page → Execution page |
| Styling | CSS Modules | Scoped styles, dark theme |
| Transport | WebSocket (native) | Receive frames + events, send input back |
| Persistence | localStorage | Task history across sessions |

### Core Modules

```
core/
  executor.py       Browser control — AXTree extraction, CDP screencast,
                    CDP input dispatch (click/key forwarding from web UI)
  planner.py        TextPlanner, VisionPlanner — structured output via
                    OpenAI function calling, Pydantic action schema
  orchestrator.py   OTA loop — per-step event emission, CAPTCHA detection,
                    failure-count circuit breaker, event_queue streaming

eval/
  runner.py         Batch evaluation — success checkers, LLM-as-judge,
                    screenshot archiving, report generation
  diagnose.py       Two-layer failure attribution, fuzzy matching,
                    error classification
  tasks_10.json     10-task benchmark across 3 complexity levels
  tasks_open.json   Extended open-ended task set
  ablation.py       Ablation study tooling

prompt/
  system_prompt.md  Hierarchical planning system prompt

server.py           FastAPI entrypoint — task registry, WebSocket multiplexer
frontend/           React app (pages/, components/, CSS Modules)
```

---

## Setup

```bash
# Python dependencies
pip install -r requirements.txt
playwright install chromium

# Environment
cp .env.example .env   # add OPENAI_API_KEY

# Frontend
cd frontend && npm install
```

## Running

```bash
# Terminal 1 — backend
python -m uvicorn server:app --reload

# Terminal 2 — frontend (dev)
cd frontend && npm run dev
# → open http://localhost:5173
```

```bash
# CLI evaluation (no frontend needed)
python -m eval.runner                          # all 10 tasks
python -m eval.runner --level 2               # level filter
python -m eval.runner --task compare_001      # single task
python -m eval.runner --model gpt-4o --steps 15
```

---

## Evaluation Framework

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

`url_contains` is used for pure navigation tasks where the URL itself is the goal. All other tasks use an LLM judge (GPT-4o) that reads the **final screenshot from disk** — the browser session is already closed at judgment time.

## Ablation: TextPlanner vs VisionPlanner

Controlled experiment — 50 tasks across 3 levels, same max steps, same LLM judge.

| | Text | Vision | Δ |
|---|---|---|---|
| Overall success rate | 61% | 78% | **+17pp** |
| Level 1 — Navigation | 89% | 94% | +5pp |
| Level 2 — Search & Retrieve | 67% | 83% | +16pp |
| Level 3 — Compare & Select | 31% | 41% | +10pp |
| Avg cost / task | $0.005 | $0.033 | 6.8× |
| Avg LLM calls / task | 8.2 | 5.1 | −3.1 |
| Avg wall time / task (s) | 85.9 | 66.4 | −19.5s |
| Layer A failures | 84% | 81% | — |
| Layer B failures | 16% | 19% | — |

**Failure symptom breakdown:**

| Symptom | Text | Vision |
|---------|------|--------|
| `target_not_found` | 41% | 17% |
| `planning_failed` | 33% | 52% |
| `no_page_change` | 10% | 8% |
| `timeout` / other (Layer B) | 16% | 19% |

### Analysis

Vision input eliminates the majority of `target_not_found` errors on Level 1–2 tasks — the model can see the page and ground its actions correctly without relying purely on AXTree element names. This explains the +17pp overall improvement and the reduced LLM call count (fewer failed retries).

Level 3 shows a smaller but real improvement (+10pp). However, `planning_failed` becomes the dominant failure mode for VisionPlanner at Level 3 — every individual action executes without error, but the agent ends up on the wrong page. This means the remaining bottleneck is **multi-step decision-making**: the model cannot reliably sequence actions toward a goal that requires comparison or conditional reasoning across multiple pages.

Providing a screenshot helps with grounding but does not solve planning. The remaining gap requires a different approach — the agent needs either a better planning mechanism or the ability to learn from past trajectories.


## Using Eval Results to Improve the System

The Layer A / Layer B split tells you **which component to fix first**. Decision tree:

```
Overall success rate unsatisfactory
        │
        ├─ Layer A dominant
        │       │
        │       ├─ symptom = target_not_found
        │       │     → Prompt: instruct model to copy element names
        │       │       verbatim from AXTree; add menuitem/option to
        │       │       click selector list in executor.py; increase
        │       │       top-N element limit in planner.py
        │       │
        │       ├─ symptom = no_page_change
        │       │     → Prompt: teach model to prefer navigable
        │       │       links/buttons; add "URL unchanged" signal
        │       │       to action history feedback
        │       │
        │       └─ symptom = planning_failed
        │             → Prompt: tighten milestone definitions;
        │               add explicit verification step to system
        │               prompt; consider VisionPlanner for tasks
        │               requiring visual confirmation
        │
        └─ Layer B dominant
                │
                ├─ timeout / element_detached
                │     → Executor: increase slow_mo or per-action
                │       wait; add retry with backoff
                │
                ├─ not_visible
                │     → Executor: scroll element into view before
                │       interacting; expand viewport
                │
                ├─ click_intercepted
                │     → Executor: dismiss overlays before clicking;
                │       fall back to JS click
                │
                └─ ambiguous_target
                      → Prompt: include role or position hint in
                        target description; tighten get_by_role
                        matching in executor
```
### Next Steps

The author is exploring this planning problem in a separate project: **[Web World Model](https://github.com/Jbb-525/webworldmodel)** — a learned world model for web navigation that predicts state transitions to guide agent decisions, directly targeting the `planning_failed` failure mode identified here.

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

## Project Structure

```
voicenav/
├── core/
│   ├── executor.py        Browser control, AXTree, CDP screencast, input dispatch
│   ├── planner.py         TextPlanner, VisionPlanner, Pydantic action schema
│   └── orchestrator.py    OTA loop, event_queue streaming, CAPTCHA handling
├── eval/
│   ├── runner.py          Batch runner, success checkers, LLM judge, report
│   ├── diagnose.py        Two-layer attribution, fuzzy match, error classification
│   ├── ablation.py        Ablation study tools
│   ├── tasks_10.json      10-task benchmark (3 levels)
│   └── tasks_open.json    Extended open-ended tasks
├── prompt/
│   └── system_prompt.md   Hierarchical planning system prompt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── ChatPage.jsx        Goal input
│   │   │   └── ExecutionPage.jsx   Live view + WebSocket manager
│   │   └── components/
│   │       ├── BrowserView.jsx     CDP frame display, browser chrome UI
│   │       └── ThinkingPanel.jsx   Agent reasoning sidebar + final URL
│   └── vite.config.js
├── server.py              FastAPI — task registry, WebSocket multiplexer,
│                          CDP input forwarding (click/key/reload)
├── requirements.txt
└── .env.example
```
