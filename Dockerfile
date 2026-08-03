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

# 构建时预下载 embedding 模型
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; \
    import os; \
    m = SentenceTransformer('BAAI/bge-small-zh-v1.5', cache_folder='/app/.cache/huggingface'); \
    from huggingface_hub import snapshot_download; \
    local_path = snapshot_download('BAAI/bge-small-zh-v1.5', cache_dir='/app/.cache/huggingface', local_files_only=False); \
    print(f'MODEL_PATH={local_path}')"

COPY . .

EXPOSE 8501

# API Keys — 部署时通过 Sealos 环境变量传入真实值
ENV DEEPSEEK_API_KEY=""
ENV TAVILY_API_KEY=""
ENV OPENWEATHER_API_KEY=""
ENV HF_HOME=/app/.cache/huggingface
ENV HF_HUB_OFFLINE=1

CMD ["streamlit", "run", "app_hitl.py", "--server.port", "8501", "--server.address", "0.0.0.0", "--server.headless", "true", "--server.enableXsrfProtection", "false", "--server.enableWebsocketCompression", "false"]
