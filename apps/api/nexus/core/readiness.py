from pathlib import Path

from nexus.core.config import Settings, settings
from nexus.core.production import ProductionReadiness, validate_production_settings


def check_readiness(config: Settings = settings) -> ProductionReadiness:
    """Report whether NEXUS is ready to accept production traffic."""
    result = validate_production_settings(config)
    issues = list(result.issues)

    for label, raw_path in (
        ("dataset_storage_path", config.dataset_storage_path),
        ("file_storage_path", config.file_storage_path),
        ("knowledge_index_path", config.knowledge_index_path),
    ):
        if not raw_path.strip():
            continue
        path = Path(raw_path)
        parent = path.parent if path.suffix else path
        try:
            parent.mkdir(parents=True, exist_ok=True)
            if not parent.is_dir():
                issues.append(f"{label} parent is not a directory")
        except OSError:
            issues.append(f"{label} parent is not writable")

    return ProductionReadiness(
        ready=not issues,
        environment=result.environment,
        issues=tuple(dict.fromkeys(issues)),
    )
