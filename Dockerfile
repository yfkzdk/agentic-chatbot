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

COPY . .

EXPOSE 8501

# API Keys — 部署时通过 --env-file .env 或 -e 传入
ENV DEEPSEEK_API_KEY=""
ENV TAVILY_API_KEY=""
ENV OPENWEATHER_API_KEY=""

CMD ["streamlit", "run", "app_hitl.py", "--server.port", "8501", "--server.address", "0.0.0.0", "--server.headless", "true", "--server.enableXsrfProtection", "false", "--server.enableWebsocketCompression", "false"]
