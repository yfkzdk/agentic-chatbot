from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# 状态
class ChatState(TypedDict):

    messages: Annotated[list[BaseMessage], add_messages]
