from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NEXUS AI"
    environment: str = "development"
    openai_api_key: str | None = None
    embedding_provider: str = "auto"
    embedding_model: str = "text-embedding-3-small"
    dataset_storage_path: str = ".nexus/data"
    file_storage_path: str = ".nexus/files"
    knowledge_index_path: str = ".nexus/knowledge/index.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
