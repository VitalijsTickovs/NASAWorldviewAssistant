from typing import TypedDict
from typing_extensions import List
from langchain_core.messages import BaseMessage


class AgentState(TypedDict, total=False):
    """
    Simplified agent state containing only messages, output, and images_output.
    """
    messages: List[BaseMessage]
    output: str
    images_output: List[bytes]