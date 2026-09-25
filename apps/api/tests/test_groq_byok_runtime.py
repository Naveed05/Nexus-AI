from nexus.core.models import InMemoryCredentialStore, BYOKProviderManager, model_registry
from nexus.core.router import TaskRouter
from nexus.core.task import Task


def test_groq_models_are_registered():
    models = [model for model in model_registry.all() if model.provider == "groq"]
    assert {model.model_id for model in models} >= {
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    }


def test_router_can_target_configured_groq_provider():
    router = TaskRouter()
    decision = router.decide(Task(objective="Explain this problem clearly"), provider="groq")
    assert decision.model.provider == "groq"


def test_byok_manager_tracks_latest_selected_provider():
    manager = BYOKProviderManager(InMemoryCredentialStore())
    manager.configure("user-1", "openai", "openai-test-key")
    manager.configure("user-1", "groq", "groq-test-key")
    assert manager.preferred("user-1") == "groq"
