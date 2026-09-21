from nexus.core.workflow_templates import get_workflow_template, list_workflow_templates


def test_workflow_templates_are_deterministic() -> None:
    first = list_workflow_templates()
    second = list_workflow_templates()
    assert first == second
    assert len(first) >= 4


def test_workflow_template_lookup() -> None:
    template = get_workflow_template("research-brief")
    assert template.risk_level == "low"
    assert "research" in template.capabilities
