"""
合约风控审查 Agent 系统 — Pydantic Settings 配置管理.

基于 pydantic-settings，从 .env + config/settings.yaml 加载配置，
启动时校验所有必需字段。
"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# 子配置共享的 env_file 片段，确保嵌套 BaseSettings 各自能读取 .env
# .env 绝对路径（避免 IDE/CWD 不同时找不到）
_ENV_PATH = str(Path(__file__).resolve().parent.parent.parent / ".env")
_ENV_FILE_CONFIG = {"env_file": _ENV_PATH, "env_file_encoding": "utf-8", "extra": "ignore"}


class LLMSettings(BaseSettings):
    """LLM 供应商配置."""
    model_config = SettingsConfigDict(env_prefix="LLM_", **_ENV_FILE_CONFIG)
    provider: str = "deepseek"
    api_key: str = ""
    base_url: Optional[str] = None
    model: str = "deepseek-chat"
    temperature: float = 0.3
    max_tokens: int = 4096


class EmbeddingSettings(BaseSettings):
    """Embedding 模型配置."""
    model_config = SettingsConfigDict(env_prefix="EMBEDDING_", **_ENV_FILE_CONFIG)
    model: str = "BAAI/bge-large-zh-v1.5"
    device: str = "cpu"


class MilvusSettings(BaseSettings):
    """Milvus 向量数据库配置.

    db_uri 支持两种模式：
    - Milvus Lite（嵌入式）: "./milvus_data.db"
    - Milvus 服务端: "http://localhost:19530"
    """
    model_config = SettingsConfigDict(env_prefix="MILVUS_", **_ENV_FILE_CONFIG)
    db_uri: str = str(Path(__file__).resolve().parent.parent.parent / "milvus_data.db")
    db_name: str = "contract_review"
    collection_name: str = "legal_knowledge"


class MySQLSettings(BaseSettings):
    """MySQL 关系数据库配置."""
    model_config = SettingsConfigDict(env_prefix="MYSQL_", **_ENV_FILE_CONFIG)
    host: str = "localhost"
    port: int = 3306
    user: str = "contract_review"
    password: str = ""
    database: str = "contract_review"

    @property
    def url(self) -> str:
        return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class Settings(BaseSettings):
    """应用全局配置."""

    model_config = SettingsConfigDict(
        env_file=_ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 部署环境
    env: str = "development"
    log_level: str = "INFO"

    # 子配置
    llm: LLMSettings = LLMSettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    milvus: MilvusSettings = MilvusSettings()
    mysql: MySQLSettings = MySQLSettings()

    # 项目根目录
    base_dir: Path = Path(__file__).resolve().parent.parent.parent


def load_settings() -> Settings:
    """加载并验证配置."""
    settings = Settings()
    if not settings.llm.api_key:
        raise ValueError(
            "LLM_API_KEY 未设置。请在 .env 文件中配置或设置环境变量。"
        )
    return settings
