from dataclasses import dataclass

from nexus.core.config import Settings, settings


@dataclass(frozen=True)
class ProductionReadiness:
    ready: bool
    environment: str
    issues: tuple[str, ...]


def validate_production_settings(config: Settings = settings) -> ProductionReadiness:
    """Validate deployment-critical configuration without exposing secrets."""
    issues: list[str] = []
    environment = config.environment.strip().lower()

    if environment not in {"development", "test", "staging", "production"}:
        issues.append("environment must be development, test, staging, or production")

    if environment == "production":
        if not config.openai_api_key:
            issues.append("openai_api_key is required in production")
        if not config.dataset_storage_path.strip():
            issues.append("dataset_storage_path cannot be empty")
        if not config.file_storage_path.strip():
            issues.append("file_storage_path cannot be empty")
        if not config.knowledge_index_path.strip():
            issues.append("knowledge_index_path cannot be empty")

    return ProductionReadiness(
        ready=not issues,
        environment=environment,
        issues=tuple(issues),
    )
