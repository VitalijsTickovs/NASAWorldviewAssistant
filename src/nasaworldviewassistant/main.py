from __future__ import annotations

from typing import List, Optional, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from langchain_core.messages import BaseMessage, HumanMessage

# import your compiled graph + helpers
from src.nasaworldviewassistant.graph import invoke_agent, stream_agent
from src.nasaworldviewassistant.config import load_env

load_env()

class AgentRequest(BaseModel):
    input: str
    thread_id: Optional[str] = None


class AgentStateOut(BaseModel):
    # We’ll serialize messages as dicts using LangChain’s .to_json() shape
    messages: List[dict]
    output: str
    images_output: List[Any]


app = FastAPI(title="Langgraph Agent", version="1.0.0")

# Adjust allowed origins for your FE dev/prod hosts
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


def _serialize_messages(msgs: List[BaseMessage]) -> List[dict]:
    """Turn LangChain messages into JSON-friendly dicts."""
    out = []
    for m in msgs:
        # .type is like "human", "ai", "system"
        out.append({
            "type": m.type,
            "content": m.content,
            "additional_kwargs": getattr(m, "additional_kwargs", {}) or {},
            "response_metadata": getattr(m, "response_metadata", {}) or {},
        })
    return out


@app.post("/api/agent", response_model=AgentStateOut)
def run_agent(body: AgentRequest):
    """
    One-shot invoke. Returns the full AgentState:
      { messages, output, images_output }
    """
    state = invoke_agent(body.input, thread_id=body.thread_id)
    return AgentStateOut(
        messages=_serialize_messages(state["messages"]),
        output=state.get("output", ""),
        images_output=state.get("images_output", []),
    )


@app.get("/api/agent/stream")
def stream_agent_sse(
    input: str = Query(..., description="User input"),
    thread_id: str | None = Query(default=None),
):
    """
    Server-Sent Events stream of state updates.
    Each event is a JSON object of the AgentState subset emitted by the graph.
    """
    def gen():
        for event in stream_agent(input, thread_id=thread_id):
            yield {
                "event": "update",
                "data": JSONResponse(content={
                    "messages": _serialize_messages(event.get("messages", [])),
                    "output": event.get("output", ""),
                    "images_output": event.get("images_output", []),
                }).body.decode("utf-8"),
            }
        yield {"event": "done", "data": ""}

    return EventSourceResponse(gen())


@app.websocket("/ws")
async def ws_agent(ws: WebSocket):
    """
    Optional WebSocket mirror of /api/agent/stream.
    Client sends: {"input": "...", "thread_id": "...?"}
    Server sends incremental JSON states and a final {"event":"done"}.
    """
    await ws.accept()
    try:
        while True:
            payload = await ws.receive_json()
            input_text = payload.get("input", "")
            thread_id = payload.get("thread_id")
            for event in stream_agent(input_text, thread_id=thread_id):
                await ws.send_json({
                    "messages": _serialize_messages(event.get("messages", [])),
                    "output": event.get("output", ""),
                    "images_output": event.get("images_output", []),
                })
            await ws.send_json({"event": "done"})
    except WebSocketDisconnect:
        pass
