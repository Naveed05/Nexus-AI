from nexus.core.config import Settings
from nexus.core.production import validate_production_settings
from nexus.core.readiness import check_readiness


def test_production_requires_ai_configuration():
    config = Settings(environment="production", openai_api_key=None)
    result = validate_production_settings(config)
    assert not result.ready
    assert "openai_api_key is required in production" in result.issues


def test_production_configuration_is_ready_with_required_values(tmp_path):
    config = Settings(
        environment="production",
        openai_api_key="test-key",
        dataset_storage_path=str(tmp_path / "data"),
        file_storage_path=str(tmp_path / "files"),
        knowledge_index_path=str(tmp_path / "knowledge" / "index.json"),
    )
    result = check_readiness(config)
    assert result.ready
    assert result.issues == ()


def test_invalid_environment_is_rejected():
    result = validate_production_settings(Settings(environment="unknown"))
    assert not result.ready
    assert "environment must be development, test, staging, or production" in result.issues
