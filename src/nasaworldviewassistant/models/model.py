from typing import Annotated, TypedDict
from typing_extensions import List
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class AgentState(TypedDict, total=False):
    """Simplified agent state containing conversation and artifacts."""

    messages: Annotated[List[BaseMessage], add_messages]
    output: str
    images_output: List[bytes]
    user_input: str
