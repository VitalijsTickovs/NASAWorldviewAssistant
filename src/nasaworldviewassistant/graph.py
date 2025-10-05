from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from langgraph.graph import StateGraph
from langgraph.checkpoint.postgres import PostgresSaver

# LangChain core primitives
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    BaseMessage,
    ToolMessage,
)

# LLM backend (swap if needed)
from langchain_openai import AzureChatOpenAI

from uuid import uuid4

from .models.model import AgentState
from .tools import worldview_link


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SYSTEM_PATH = PROMPTS_DIR / "system.txt"
USER_PATH = PROMPTS_DIR / "user.txt"


def read_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def build_messages(user_input: str) -> tuple[SystemMessage, HumanMessage]:
    """Return system and formatted human prompts for the current turn."""
    system_prompt = read_prompt(SYSTEM_PATH)
    user_prompt_tmpl = read_prompt(USER_PATH)

    if not system_prompt:
        system_prompt = "You are a helpful NASA Worldview assistant."

    try:
        user_prompt = user_prompt_tmpl.format(input=user_input)
    except Exception:
        user_prompt = ""

    if not user_prompt.strip():
        user_prompt = user_input

    if not user_input and user_prompt_tmpl and "{input" in user_prompt_tmpl:
        user_prompt = user_prompt_tmpl.format(input="")

    return SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)


def make_llm() -> AzureChatOpenAI:
    """
    Create a LangChain chat model (OpenAI by default).
    Set via env:
      MODEL (default: gpt-4o-mini)
      TEMPERATURE (default: 0.2)
    """
    model = os.getenv("MODEL", "gpt-4o-mini")
    temperature = float(os.getenv("TEMPERATURE", "0"))
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
    return AzureChatOpenAI(model=model, temperature=temperature, deployment_name=deployment)


def prepare_node(state: AgentState) -> AgentState:
    """Append the system prompt once and inject the latest human turn."""
    history = list(state.get("messages", []))
    user_input = state.get("user_input", "") or ""

    system_msg, human_msg = build_messages(user_input)
    new_messages: list[BaseMessage] = []

    if not any(isinstance(m, SystemMessage) for m in history):
        new_messages.append(system_msg)

    human_text = human_msg.content.strip()
    if human_text:
        raw_kwargs = {"raw_input": user_input}
        combined_kwargs = dict(getattr(human_msg, "additional_kwargs", {}) or {})
        combined_kwargs.update(raw_kwargs)
        new_messages.append(
            HumanMessage(
                content=human_text,
                additional_kwargs=combined_kwargs,
                response_metadata=getattr(human_msg, "response_metadata", {}) or {},
            )
        )

    return {
        "messages": new_messages,
        "output": "",
        "images_output": [],
        "user_input": "",
    }


def llm_node(state: AgentState) -> AgentState:
    # Bind tools to enable function/tool calling
    tools = [worldview_link]
    llm = make_llm().bind_tools(tools)

    transcript = list(state.get("messages", []))
    if not transcript:
        return {"messages": [], "output": "", "images_output": []}

    name_to_tool = {t.name: t for t in tools}
    new_messages: list[BaseMessage] = []

    # First model call
    resp = llm.invoke(transcript)
    transcript.append(resp)
    new_messages.append(resp)

    # Process tool calls iteratively (up to a small cap)
    max_tool_rounds = 3
    rounds = 0
    while (
        isinstance(resp, AIMessage)
        and getattr(resp, "tool_calls", None)
        and rounds < max_tool_rounds
    ):
        tool_messages: list[ToolMessage] = []
        for tc in resp.tool_calls:
            tool_name = tc.get("name")
            tool_args = tc.get("args", {}) or {}
            tool_id = tc.get("id")
            tool = name_to_tool.get(tool_name)
            if tool is None:
                continue
            try:
                result = tool.invoke(tool_args)
                tool_messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))
            except Exception as e:
                tool_messages.append(ToolMessage(content=f"Tool error: {e}", tool_call_id=tool_id))

        if not tool_messages:
            break

        transcript.extend(tool_messages)
        new_messages.extend(tool_messages)

        resp = llm.invoke(transcript)
        transcript.append(resp)
        new_messages.append(resp)
        rounds += 1

    # Return the final AI message content
    final_text = resp.content if isinstance(resp, AIMessage) else str(resp)
    return {"messages": new_messages, "output": final_text, "images_output": []}

def _build_workflow() -> StateGraph:
    """
    Create the workflow (uncompiled). No DB here.
    """
    wf = StateGraph(AgentState)
    wf.add_node("prepare", prepare_node)  # your existing function
    wf.add_node("llm", llm_node)          # your existing function
    wf.set_entry_point("prepare")
    wf.add_edge("prepare", "llm")
    return wf


def invoke_agent(user_input: str, *, thread_id: str | None = None) -> AgentState:
    """
    One-off invocation using a *scoped* Postgres checkpointer.
    The connection is opened for this call and closed afterward.
    """
    dsn = os.environ["PG_DSN"]
    with PostgresSaver.from_conn_string(dsn) as checkpointer:
        # Ensure tables exist (safe to call repeatedly)
        checkpointer.setup()

        # Build and compile the graph within the context
        workflow = _build_workflow()
        graph = workflow.compile(checkpointer=checkpointer)

        # Prepare initial state and config
        initial_state: AgentState = {"messages": [], "user_input": user_input}
        # Ensure a thread_id is always provided when using a checkpointer
        tid = thread_id or f"thread-{uuid4()}"
        config = {"configurable": {"thread_id": tid}}

        # Run and return final state (messages/output/images_output)
        return graph.invoke(initial_state, config=config)


def stream_agent(user_input: str, *, thread_id: str | None = None) -> Generator[AgentState, None, None]:
    """
    Streaming generator using a *scoped* Postgres checkpointer.
    Yields AgentState chunks and closes the connection when done.
    """
    dsn = os.environ["PG_DSN"]
    with PostgresSaver.from_conn_string(dsn) as checkpointer:
        checkpointer.setup()

        workflow = _build_workflow()
        graph = workflow.compile(checkpointer=checkpointer)

        initial_state: AgentState = {"messages": [], "user_input": user_input}
        # Ensure a thread_id is always provided when using a checkpointer
        tid = thread_id or f"thread-{uuid4()}"
        config = {"configurable": {"thread_id": tid}}

        for event in graph.stream(initial_state, config=config, stream_mode="values"):
            # Each 'event' is a (partial) AgentState dict with the same keys your state defines.
            yield event


