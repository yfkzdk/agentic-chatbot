FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 构建时预下载 embedding 模型（不设离线标志，让它正常下载）
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; \
    m = SentenceTransformer('BAAI/bge-small-zh-v1.5', cache_folder='/app/.cache/huggingface'); \
    print('Model cached successfully')"

COPY . .

EXPOSE 8501

# API Keys — 部署时通过 -e 传入
ENV DEEPSEEK_API_KEY=""
ENV TAVILY_API_KEY=""
ENV OPENWEATHER_API_KEY=""

CMD ["streamlit", "run", "app_hitl.py", "--server.port", "8501", "--server.address", "0.0.0.0", "--server.headless", "true", "--server.enableXsrfProtection", "false", "--server.enableWebsocketCompression", "false"]
