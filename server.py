"""
FastAPI server for VoiceNav web UI.

Endpoints:
  POST /api/task   — create and start a task
  WS   /ws/{id}   — stream execution events + browser frames
"""

import asyncio
import json
import uuid
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.executor import Executor
from core.orchestrator import Orchestrator
from core.planner import VisionPlanner

app = FastAPI(title="VoiceNav API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory task registry: task_id → {"event_queue", "frame_queue", "status"}
_tasks: Dict[str, Dict] = {}


class TaskRequest(BaseModel):
    goal: str
    start_url: str = "https://www.google.com"


@app.post("/api/task")
async def create_task(req: TaskRequest):
    task_id = str(uuid.uuid4())
    event_queue: asyncio.Queue = asyncio.Queue()
    frame_queue: asyncio.Queue = asyncio.Queue()

    _tasks[task_id] = {
        "event_queue": event_queue,
        "frame_queue": frame_queue,
        "status": "pending",
        "goal": req.goal,
        "start_url": req.start_url,
    }

    # Launch the agent in the background
    asyncio.create_task(_run_task(task_id, req.goal, req.start_url, event_queue, frame_queue))

    return {"task_id": task_id}


async def _run_task(
    task_id: str,
    goal: str,
    start_url: str,
    event_queue: asyncio.Queue,
    frame_queue: asyncio.Queue,
):
    """Run the orchestrator for a task and stream events."""
    _tasks[task_id]["status"] = "running"
    executor = Executor(headless=True, frame_queue=frame_queue)
    _tasks[task_id]["executor"] = executor  # expose for input forwarding
    planner = VisionPlanner()
    orchestrator = Orchestrator(executor=executor, planner=planner, event_queue=event_queue)

    try:
        result = await orchestrator.run(goal, start_url, max_steps=15)
        _tasks[task_id]["status"] = "done"
        _tasks[task_id]["result"] = result
    except Exception as e:
        await event_queue.put({"type": "error", "message": str(e)})
        _tasks[task_id]["status"] = "error"
    finally:
        # Signal WebSocket consumers that streaming is finished
        await event_queue.put(None)
        await frame_queue.put(None)


@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """Multiplex browser frames and agent events over one WebSocket connection."""
    if task_id not in _tasks:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    task = _tasks[task_id]
    event_queue: asyncio.Queue = task["event_queue"]
    frame_queue: asyncio.Queue = task["frame_queue"]

    # We'll drain both queues concurrently and send to client
    async def send_frames():
        while True:
            frame = await frame_queue.get()
            if frame is None:
                break
            try:
                await websocket.send_text(json.dumps({"type": "frame", "data": frame}))
            except Exception:
                break

    async def send_events():
        while True:
            event = await event_queue.get()
            if event is None:
                break
            try:
                await websocket.send_text(json.dumps(event))
            except Exception:
                break

    async def receive_inputs():
        """Forward click/key events from the frontend to the browser via CDP."""
        executor: Executor = task.get("executor")
        while True:
            try:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                if executor is None:
                    executor = task.get("executor")
                if executor is None:
                    continue
                if msg.get("type") == "input_click":
                    await executor.dispatch_click(int(msg["x"]), int(msg["y"]))
                elif msg.get("type") == "input_key":
                    await executor.dispatch_key(msg.get("text", ""))
                elif msg.get("type") == "input_reload":
                    await executor.dispatch_reload()
            except WebSocketDisconnect:
                break
            except Exception:
                break

    try:
        await asyncio.gather(send_frames(), send_events(), receive_inputs())
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# Serve built React frontend (when available)
import os
_frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        index = os.path.join(_frontend_dist, "index.html")
        return FileResponse(index)
