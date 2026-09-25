from nexus.core.engine import NexusEngine
from nexus.core.models import model_registry
from nexus.core.task import Task


def test_engine_propagates_user_provider_context_to_executor() -> None:
    calls = []

    class Executor:
        def execute(self, task, model, allowed_tools=(), user_id=None, use_byok=False):
            calls.append((user_id, use_byok, tuple(allowed_tools)))
            return None

    engine = NexusEngine(executor=Executor())
    engine._execute_compatibly(
        Task(objective="context propagation"),
        model_registry.get("astra"),
        ("calculator",),
        user_id="local-user-123",
        use_byok=True,
    )
    assert calls == [("local-user-123", True, ("calculator",))]
