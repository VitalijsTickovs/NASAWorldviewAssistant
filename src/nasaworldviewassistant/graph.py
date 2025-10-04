from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict, List

from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver

# LangChain core primitives
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage

# LLM backend (swap if needed)
from langchain_openai import AzureChatOpenAI

from src.nasaworldviewassistant.models.model import AgentState


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SYSTEM_PATH = PROMPTS_DIR / "system.txt"
USER_PATH = PROMPTS_DIR / "user.txt"


def read_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def build_messages(user_input: str) -> List[BaseMessage]:
    """
    Load system.txt and user.txt, then compose into message list.
    """
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

    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]


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
    """
    Initialize message list from prompts and input text.
    """
    user_input = ""
    for m in state.get("messages", []):
        if isinstance(m, HumanMessage):
            user_input = m.content
            break

    messages = build_messages(user_input)
    return {"messages": messages, "output": "", "images_output": []}


def llm_node(state: AgentState) -> AgentState:
    llm = make_llm()
    messages = state["messages"]
    resp = llm.invoke(messages)
    ai_msg = AIMessage(content=resp.content)

    # Append model output to conversation
    new_messages = messages + [ai_msg]
    return {
        "messages": new_messages,
        "output": ai_msg.content,
        "images_output": [],  # placeholder for any generated imagery links
    }

def build_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("prepare", prepare_node)
    workflow.add_node("llm", llm_node)
    workflow.set_entry_point("prepare")
    workflow.add_edge("prepare", "llm")

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)


GRAPH = build_graph()

def invoke_agent(user_input: str, *, thread_id: str | None = None) -> AgentState:
    """
    Run a one-off agent invocation.
    """
    config = {"configurable": {"thread_id": thread_id}} if thread_id else {}
    initial_state = {"messages": [HumanMessage(content=user_input)]}
    return GRAPH.invoke(initial_state, config=config)


def stream_agent(user_input: str, *, thread_id: str | None = None):
    """
    Stream agent events for incremental UI updates.
    """
    config = {"configurable": {"thread_id": thread_id}} if thread_id else {}
    initial_state = {"messages": [HumanMessage(content=user_input)]}
    for event in GRAPH.stream(initial_state, config=config, stream_mode="values"):
        yield event
