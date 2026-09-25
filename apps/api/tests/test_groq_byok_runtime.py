from nexus.core.models import BYOKProviderManager, GROQ_MODEL_SPECS, InMemoryCredentialStore
from nexus.core.router import TaskRouter
from nexus.core.task import Task


def test_groq_model_catalog():
    assert {model.model_id for model in GROQ_MODEL_SPECS} >= {
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    }


def test_router_can_target_groq():
    decision = TaskRouter().decide(Task(objective="Explain this problem clearly"), provider="groq")
    assert decision.model.provider == "groq"


def test_byok_tracks_selected_provider():
    manager = BYOKProviderManager(InMemoryCredentialStore())
    manager.configure("user-1", "openai", "openai-test-key")
    manager.configure("user-1", "groq", "groq-test-key")
    assert manager.preferred("user-1") == "groq"
