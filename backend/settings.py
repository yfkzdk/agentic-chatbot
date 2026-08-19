from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置：从 .env 读取，缺失必填项在启动期直接报错。"""

    # 数据库（默认 PostgreSQL；如需本地 SQLite 可改为 sqlite:///chatbot.db）
    database_url: str = "postgresql://postgres:yfk520715123@127.0.0.1:5432/chatbot"

    # JWT
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # 允许的前端来源（生产环境改为具体域名）
    cors_origins: str = "*"

    class Config:
        env_file = ".env"
        extra = "ignore"  # 忽略 .env 中 LangSmith 等其他变量

    def validate_required(self):
        """启动期校验：secret_key 未配置则拒绝启动。"""
        if not self.secret_key:
            raise RuntimeError(
                "SECRET_KEY 未配置。请在 .env 中设置一个随机密钥，"
                "例如：SECRET_KEY=$(python -c \"import secrets; print(secrets.token_hex(32))\")"
            )


settings = Settings()
