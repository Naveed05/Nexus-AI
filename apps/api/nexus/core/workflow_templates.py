from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowTemplate:
    template_id: str
    name: str
    description: str
    objective: str
    capabilities: tuple[str, ...]
    risk_level: str = "low"


WORKFLOW_TEMPLATES: tuple[WorkflowTemplate, ...] = (
    WorkflowTemplate("research-brief", "Research brief", "Turn a question into an evidence-backed brief.",
                     "Research the topic, collect reliable evidence, compare the key findings, and produce a concise cited brief.",
                     ("research", "retrieval")),
    WorkflowTemplate("data-profile", "Data profile", "Profile a dataset and surface the most important quality and statistical findings.",
                     "Profile the supplied dataset, identify quality issues, summarize important statistics, and explain the most useful findings.",
                     ("data-analysis",)),
    WorkflowTemplate("document-review", "Document review", "Extract and organize the important points from workspace documents.",
                     "Review the relevant workspace documents, identify key points and risks, and produce a structured summary with evidence.",
                     ("document-intelligence", "retrieval")),
    WorkflowTemplate("code-review", "Code review", "Inspect code for correctness, maintainability, and concrete risks.",
                     "Review the relevant code, identify concrete correctness and maintainability issues, and propose actionable fixes.",
                     ("developer-intelligence",)),
)


def list_workflow_templates() -> tuple[WorkflowTemplate, ...]:
    return WORKFLOW_TEMPLATES


def get_workflow_template(template_id: str) -> WorkflowTemplate:
    for template in WORKFLOW_TEMPLATES:
        if template.template_id == template_id:
            return template
    raise KeyError(template_id)
