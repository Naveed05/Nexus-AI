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
    run_storage_path: str = ".nexus/runs.sqlite3"
    artifact_storage_path: str = ".nexus/artifacts"
    artifact_registry_path: str = ".nexus/artifacts.sqlite3"
    job_storage_path: str = ".nexus/jobs.sqlite3"
    collaboration_audit_storage_path: str = ".nexus/collaboration_audit.sqlite3"
    log_level: str = "INFO"
    request_metrics_max_samples: int = 1000
    service_version: str = "0.1.0"
    beta_access_key: str | None = None
    rate_limit_per_minute: int = 120
    max_request_body_bytes: int = 10 * 1024 * 1024
    state_backend: str = "sqlite"
    cache_backend: str = "memory"
    object_storage_backend: str = "filesystem"
    queue_backend: str = "sqlite"
    deployment_mode: str = "single"
    deployment_region: str = ""
    instance_id: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
