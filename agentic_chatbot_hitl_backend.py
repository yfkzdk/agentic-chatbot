import os
from dotenv import load_dotenv

# ============================================================
# LangSmith 追踪 — 必须在所有 LangChain import 之前设置
# ============================================================
load_dotenv(override=True)
if os.getenv("LANGSMITH_TRACING", "false").lower() == "true":
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY", "")
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "agentic-chatbot")
    os.environ["LANGCHAIN_ENDPOINT"] = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

from langgraph.graph import StateGraph, START, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
import sqlite3
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_tavily import TavilySearch
from langchain_core.tools import tool
import math
import requests
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from typing import Any
from langgraph.types import interrupt, Command

# LLM
llm = ChatOpenAI(
    model="deepseek-chat",
    temperature=0.7,
    base_url="https://api.deepseek.com",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
)


# Embedding 模型（中文优化，本地运行，免费）
# 使用缓存目录避免每次重启都重新下载
import shutil
model_cache_dir = "/app/.cache/huggingface"
os.makedirs(model_cache_dir, exist_ok=True)
os.environ["HF_HOME"] = model_cache_dir
os.environ["TRANSFORMERS_CACHE"] = model_cache_dir

embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-zh-v1.5",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
    cache_folder=model_cache_dir,
)



def ingest_rag_document(file_path):
    DB_PATH = "faiss_db"
    loader = PyPDFLoader(file_path)
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)
    vector_store = FAISS.from_documents(chunks, embeddings)
    vector_store.save_local(DB_PATH)
    


def get_retriever():
    DB_PATH = "faiss_db"
    vector_store = FAISS.load_local(
            folder_path=DB_PATH,
            embeddings=embeddings,
            allow_dangerous_deserialization=True
        )
    
    retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 4}
    )

    return retriever




# rag tool

@tool
def rag_tool(query: str) -> str:
    """
    Retrieve relevant information from the PDF document.

    Use this tool when the user asks factual or conceptual questions
    that may be answered using the stored PDF documents.

    Args:
        query: The question or search query used to retrieve PDF content.
    """
    retriever = get_retriever()
    documents = retriever.invoke(query)

    if not documents:
        return "No relevant information was found in the PDF."

    formatted_documents = []

    for index, document in enumerate(documents, start=1):
        source = document.metadata.get("source", "Unknown source")
        page = document.metadata.get("page", "Unknown page")

        formatted_documents.append(
            f"Document {index}\n"
            f"Source: {source}\n"
            f"Page: {page}\n"
            f"Content: {document.page_content}"
        )

    return "\n\n".join(formatted_documents)




# Tools

search_tool = TavilySearch(
    max_results=5,
    topic="general",
    search_depth="advanced"
)


@tool
def calculator(expression: str) -> str:
    """
    Useful for simple math calculations.
    Input should be a valid math expression.
    Example: 2 + 2, math.sqrt(16), 10 * 5
    """

    try:
        allowed = {
            "math": math,
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum
        }

        result = eval(expression, {"__builtins__": {}}, allowed)
        return str(result)

    except Exception as e:
        return f"Calculation error: {str(e)}"




@tool
def get_stock_price(symbol: str) -> dict:
    """
    Fetch latest stock price for a given symbol (e.g. 'AAPL', 'TSLA') 
    using Alpha Vantage with API key in the URL.
    """
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "demo")
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"
    r = requests.get(url)
    return r.json()



@tool
def purchase_stock(symbol: str, quantity: int) -> dict:
    """
    Simulate purchasing a given quantity of a stock symbol.

    HUMAN-IN-THE-LOOP:
    Before confirming the purchase, this tool will interrupt
    and wait for a human decision ("yes" / anything else).
    """
    # This pauses the graph and returns control to the caller
    decision = interrupt(f"Approve buying {quantity} shares of {symbol}? (yes/no)")

    if isinstance(decision, str) and decision.lower() == "yes":
        return {
            "status": "success",
            "message": f"Purchase order placed for {quantity} shares of {symbol}.",
            "symbol": symbol,
            "quantity": quantity,
        }
    
    else:
        return {
            "status": "cancelled",
            "message": f"Purchase of {quantity} shares of {symbol} was declined by human.",
            "symbol": symbol,
            "quantity": quantity,
        }




@tool
def get_current_weather(location: str) -> str:
    """
    Get the current real-time weather for a given city or location.

    Args:
        location: City or location name, for example:
                  "Dhaka", "London, UK", or "New York, US".

    Returns:
        A formatted current weather report.
    """

    api_key = os.getenv("OPENWEATHER_API_KEY")

    if not api_key:
        return (
            "Weather API key is missing. "
            "Set the OPENWEATHER_API_KEY environment variable."
        )

    try:
        # Step 1: Convert the location name into latitude and longitude
        geocoding_url = "https://api.openweathermap.org/geo/1.0/direct"

        geocoding_params = {
            "q": location,
            "limit": 1,
            "appid": api_key,
        }

        geo_response = requests.get(
            geocoding_url,
            params=geocoding_params,
            timeout=10,
        )
        geo_response.raise_for_status()

        locations: list[dict[str, Any]] = geo_response.json()

        if not locations:
            return f"Could not find the location: {location}"

        latitude = locations[0]["lat"]
        longitude = locations[0]["lon"]
        resolved_name = locations[0].get("name", location)
        country = locations[0].get("country", "")
        state = locations[0].get("state", "")

        # Step 2: Get current weather using latitude and longitude
        weather_url = "https://api.openweathermap.org/data/2.5/weather"

        weather_params = {
            "lat": latitude,
            "lon": longitude,
            "appid": api_key,
            "units": "metric",
        }

        weather_response = requests.get(
            weather_url,
            params=weather_params,
            timeout=10,
        )
        weather_response.raise_for_status()

        weather_data = weather_response.json()

        temperature = weather_data["main"]["temp"]
        feels_like = weather_data["main"]["feels_like"]
        humidity = weather_data["main"]["humidity"]
        pressure = weather_data["main"]["pressure"]
        description = weather_data["weather"][0]["description"]
        wind_speed = weather_data.get("wind", {}).get("speed", "N/A")
        visibility_meters = weather_data.get("visibility")

        visibility_km = (
            round(visibility_meters / 1000, 1)
            if visibility_meters is not None
            else "N/A"
        )

        location_parts = [resolved_name]

        if state:
            location_parts.append(state)

        if country:
            location_parts.append(country)

        display_location = ", ".join(location_parts)

        return (
            f"Current weather in {display_location}:\n"
            f"- Condition: {description.title()}\n"
            f"- Temperature: {temperature}°C\n"
            f"- Feels like: {feels_like}°C\n"
            f"- Humidity: {humidity}%\n"
            f"- Pressure: {pressure} hPa\n"
            f"- Wind speed: {wind_speed} m/s\n"
            f"- Visibility: {visibility_km} km"
        )

    except requests.Timeout:
        return "The weather service request timed out. Please try again."

    except requests.HTTPError as error:
        status_code = error.response.status_code if error.response else "unknown"

        if status_code == 401:
            return "The OpenWeather API key is invalid or inactive."

        return f"Weather API returned an HTTP error: {status_code}"

    except requests.RequestException as error:
        return f"Could not connect to the weather service: {error}"

    except (KeyError, TypeError, ValueError) as error:
        return f"Unexpected weather API response: {error}"
    


# Make tool list
tools = [search_tool,calculator, get_stock_price,get_current_weather, rag_tool, purchase_stock]

# Make the LLM tool-aware
llm_with_tools = llm.bind_tools(tools)




# State
class ChatState(TypedDict):

    messages: Annotated[list[BaseMessage], add_messages]



def _clean_tool_calls(messages: list) -> list:
    """移除没有对应 ToolMessage 的 AIMessage 中的 tool_calls。

    DeepSeek API 要求带 tool_calls 的 AIMessage 后面必须紧跟
    对应的 ToolMessage，否则会报 400 错误。
    """
    cleaned = []
    for i, msg in enumerate(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            # 检查后面是否有对应每个 tool_call_id 的 ToolMessage
            remaining = messages[i + 1:]
            for tc in msg.tool_calls:
                matched = any(
                    isinstance(m, ToolMessage) and m.tool_call_id == tc.get("id")
                    for m in remaining
                )
                if not matched:
                    # 有孤儿 tool_call，移除整个 tool_calls
                    msg = AIMessage(
                        content=msg.content,
                        id=msg.id,
                    )
                    break
        cleaned.append(msg)
    return cleaned


# Nodes 1
def chat_node(state: ChatState):
    """LLM node that can answer directly or call an appropriate tool."""

    system_message = SystemMessage(
        content=(
            "你是一个友好的智能聊天助手，可以使用多种工具来帮助用户。\n\n"

            "工具使用说明：\n"
            "- 使用 `rag_tool` 回答与已上传的 PDF 文档相关的问题。"
            "在回答 PDF 相关问题前，始终先检索相关文档内容。\n"
            "- 使用 `search_tool` 搜索时事新闻、最新信息或需要联网查询的内容。\n"
            "- 使用 `calculator` 进行数学计算。当有计算器可用时，不要手动计算复杂表达式。\n"
            "- 使用 `get_stock_price` 查询用户询问的股票当前价格。\n"
            "- 使用 `purchase_stock` 当用户想要购买股票时。\n"
            "- 使用 `get_current_weather` 查询用户询问的城市天气。\n\n"

            "不需要工具时直接回答一般性问题。"
            "不要凭空编造上传文档中的信息。"
            "如果用户询问 PDF 相关内容但没有上传文档，请提示用户上传 PDF。"
            "收到工具结果后，请用中文给出清晰、有帮助的最终回答。"
        )
    )

    # 过滤孤儿 tool_calls，避免 DeepSeek 400 错误
    history = _clean_tool_calls(list(state["messages"]))

    messages = [
        system_message,
        *history
    ]

    response = llm_with_tools.invoke(messages)

    return {"messages": [response]}




# Nodes 2 - tool node
tool_node = ToolNode(tools)



# Checkpointer
conn = sqlite3.connect(database="chatbot.db", check_same_thread=False)
checkpoint = MemorySaver()



# graph
graph = StateGraph(ChatState)

# add nodes
graph.add_node('chat_node', chat_node)
graph.add_node('tools', tool_node)

#add edges
graph.add_edge(START, 'chat_node')
graph.add_conditional_edges("chat_node",tools_condition)
graph.add_edge('tools', 'chat_node')

chatbot = graph.compile(checkpointer=checkpoint)



# Helper functions for Streamlit frontend
def get_all_threads():
    all_threads = set()
    for ckpt in checkpoint.list(None):
        all_threads.add(ckpt.config['configurable']['thread_id'])

    return list(all_threads)


