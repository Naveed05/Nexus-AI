from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from uuid import UUID

from nexus.core.data_engine import DataIntelligenceEngine
from nexus.core.data_pipeline import DataPipeline
from nexus.core.dataset_workspace import DatasetNotFoundError, DatasetWorkspace
from nexus.core.knowledge import search_knowledge
from nexus.core.ml_tools import baseline_ml
from nexus.core.research import research_knowledge

RISK_LEVELS = {"low", "medium", "high"}
PERMISSION_LEVELS = {"read", "modify", "high_risk"}
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class ToolSpec:
    """Immutable contract describing one executable NEXUS capability."""

    name: str
    description: str
    input_schema: dict[str, Any]
    risk_level: str
    handler: Callable[..., Any]
    permission: str = "read"
    timeout_seconds: float = 30.0
    cost_units: float = 0.0
    sandbox_required: bool = False
    max_output_bytes: int = 1_048_576
    version: str = "1.0.0"
    capabilities: frozenset[str] = field(default_factory=frozenset)
    idempotent: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool name cannot be empty")
        if not self.description.strip():
            raise ValueError("tool description cannot be empty")
        if self.risk_level not in RISK_LEVELS:
            raise ValueError(f"Unsupported risk level: {self.risk_level}")
        if self.permission not in PERMISSION_LEVELS:
            raise ValueError(f"Unsupported permission level: {self.permission}")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self.cost_units < 0:
            raise ValueError("cost_units cannot be negative")
        if self.max_output_bytes < 1:
            raise ValueError("max_output_bytes must be greater than zero")
        if not self.version.strip():
            raise ValueError("tool version cannot be empty")
        normalized = frozenset(capability.strip().lower() for capability in self.capabilities)
        if any(not capability for capability in normalized):
            raise ValueError("tool capabilities cannot contain empty values")
        object.__setattr__(self, "capabilities", normalized)

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
            "strict": True,
        }

    def contract(self) -> dict[str, Any]:
        """Return provider-neutral metadata for capability discovery and auditing."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "risk_level": self.risk_level,
            "permission": self.permission,
            "timeout_seconds": self.timeout_seconds,
            "cost_units": self.cost_units,
            "sandbox_required": self.sandbox_required,
            "max_output_bytes": self.max_output_bytes,
            "capabilities": sorted(self.capabilities),
            "idempotent": self.idempotent,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    """Deterministic registry and capability-discovery boundary for tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ValueError(f"Unknown tool: {name}") from exc

    def all(self) -> tuple[ToolSpec, ...]:
        return tuple(self._tools.values())

    def find(
        self,
        capabilities: Iterable[str] = (),
        *,
        maximum_risk: str | None = None,
        maximum_cost_units: float | None = None,
        require_sandbox: bool = False,
    ) -> tuple[ToolSpec, ...]:
        """Find compatible tools without executing or bypassing authorization."""
        required = frozenset(value.strip().lower() for value in capabilities if value.strip())
        if maximum_risk is not None and maximum_risk not in RISK_LEVELS:
            raise ValueError(f"Unsupported risk level: {maximum_risk}")
        if maximum_cost_units is not None and maximum_cost_units < 0:
            raise ValueError("maximum_cost_units cannot be negative")

        matches = [
            tool
            for tool in self._tools.values()
            if required.issubset(tool.capabilities)
            and (maximum_risk is None or RISK_ORDER[tool.risk_level] <= RISK_ORDER[maximum_risk])
            and (maximum_cost_units is None or tool.cost_units <= maximum_cost_units)
            and (not require_sandbox or tool.sandbox_required)
        ]
        return tuple(sorted(matches, key=lambda tool: (tool.cost_units, RISK_ORDER[tool.risk_level], tool.name)))

    def capabilities(self) -> tuple[str, ...]:
        return tuple(sorted({capability for tool in self._tools.values() for capability in tool.capabilities}))

    def contracts(self) -> tuple[dict[str, Any], ...]:
        return tuple(tool.contract() for tool in self._tools.values())

    def openai_tools(self) -> list[dict[str, Any]]:
        return [tool.as_openai_tool() for tool in self._tools.values()]


_dataset_workspace: DatasetWorkspace | None = None


def configure_dataset_workspace(workspace: DatasetWorkspace | None) -> None:
    global _dataset_workspace
    _dataset_workspace = workspace


def _require_workspace() -> DatasetWorkspace:
    if _dataset_workspace is None:
        raise RuntimeError("Dataset workspace is not configured")
    return _dataset_workspace


def calculator(expression: str) -> dict[str, str]:
    allowed = set("0123456789+-*/(). %")
    if not expression or any(char not in allowed for char in expression):
        raise ValueError("Expression contains unsupported characters")
    try:
        result = eval(expression, {"__builtins__": {}}, {})
    except Exception as exc:
        raise ValueError("Invalid arithmetic expression") from exc
    return {"expression": expression, "result": str(result)}


def _profile_frame(frame) -> dict[str, Any]:
    engine = DataIntelligenceEngine()
    profile = engine.profile(frame)
    quality = engine.quality_report(frame)
    return {"profile": {"rows": profile.rows, "columns": profile.columns, "duplicate_rows": profile.duplicate_rows, "memory_estimate_bytes": profile.memory_estimate_bytes, "column_profiles": [{"name": c.name, "dtype": c.dtype, "null_count": c.null_count, "null_ratio": c.null_ratio, "unique_count": c.unique_count} for c in profile.column_profiles]}, "quality": quality}


def profile_dataset(csv_text: str) -> dict[str, Any]:
    if not csv_text.strip():
        raise ValueError("CSV payload cannot be empty")
    return _profile_frame(DataIntelligenceEngine().load_bytes(csv_text.encode("utf-8"), "csv"))


def profile_dataset_by_id(dataset_id: str) -> dict[str, Any]:
    try:
        frame = _require_workspace().load(UUID(dataset_id))
    except (ValueError, DatasetNotFoundError) as exc:
        raise ValueError(f"Invalid or unknown dataset_id: {dataset_id}") from exc
    return _profile_frame(frame)


def analyze_dataset(csv_text: str, target: str | None = None) -> dict[str, Any]:
    if not csv_text.strip():
        raise ValueError("CSV payload cannot be empty")
    return DataPipeline().analyze(DataIntelligenceEngine().load_bytes(csv_text.encode("utf-8"), "csv"), target=target)


def analyze_dataset_by_id(dataset_id: str, target: str | None = None) -> dict[str, Any]:
    try:
        frame = _require_workspace().load(UUID(dataset_id))
    except (ValueError, DatasetNotFoundError) as exc:
        raise ValueError(f"Invalid or unknown dataset_id: {dataset_id}") from exc
    return DataPipeline().analyze(frame, target=target)


tool_registry = ToolRegistry()
tool_registry.register(ToolSpec("calculator", "Perform basic arithmetic calculations.", {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"], "additionalProperties": False}, "low", calculator, timeout_seconds=5.0, capabilities=frozenset({"calculation", "deterministic"}), idempotent=True))
tool_registry.register(ToolSpec("profile_dataset", "Profile a UTF-8 CSV dataset and identify data-quality issues.", {"type": "object", "properties": {"csv_text": {"type": "string"}}, "required": ["csv_text"], "additionalProperties": False}, "low", profile_dataset, timeout_seconds=15.0, cost_units=0.1, capabilities=frozenset({"data_profiling", "data_quality", "tabular_data"}), idempotent=True))
tool_registry.register(ToolSpec("analyze_dataset", "Analyze CSV data with cleaning, EDA, correlations, problem formulation, and recommendations.", {"type": "object", "properties": {"csv_text": {"type": "string"}, "target": {"type": ["string", "null"]}}, "required": ["csv_text", "target"], "additionalProperties": False}, "low", analyze_dataset, timeout_seconds=30.0, cost_units=0.5, capabilities=frozenset({"data_analysis", "eda", "tabular_data"}), idempotent=True))
tool_registry.register(ToolSpec("profile_dataset_by_id", "Profile a registered NEXUS dataset by dataset_id.", {"type": "object", "properties": {"dataset_id": {"type": "string"}}, "required": ["dataset_id"], "additionalProperties": False}, "low", profile_dataset_by_id, timeout_seconds=15.0, cost_units=0.1, capabilities=frozenset({"data_profiling", "data_quality", "tabular_data", "workspace_data"}), idempotent=True))
tool_registry.register(ToolSpec("analyze_dataset_by_id", "Analyze a registered NEXUS dataset by dataset_id.", {"type": "object", "properties": {"dataset_id": {"type": "string"}, "target": {"type": ["string", "null"]}}, "required": ["dataset_id", "target"], "additionalProperties": False}, "low", analyze_dataset_by_id, timeout_seconds=30.0, cost_units=0.5, capabilities=frozenset({"data_analysis", "eda", "tabular_data", "workspace_data"}), idempotent=True))
tool_registry.register(ToolSpec("baseline_ml", "Train and evaluate a conservative baseline ML model for an explicit target column.", {"type": "object", "properties": {"csv_text": {"type": "string"}, "target": {"type": "string"}}, "required": ["csv_text", "target"], "additionalProperties": False}, "medium", baseline_ml, permission="read", timeout_seconds=60.0, cost_units=2.0, capabilities=frozenset({"machine_learning", "classification", "regression", "tabular_data"}), idempotent=False))
tool_registry.register(ToolSpec("search_knowledge", "Search workspace documents using hybrid retrieval and return grounded evidence with citations.", {"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "minimum": 1, "maximum": 20}, "document_id": {"type": ["string", "null"]}}, "required": ["query", "top_k", "document_id"], "additionalProperties": False}, "low", search_knowledge, timeout_seconds=15.0, cost_units=0.2, capabilities=frozenset({"knowledge_retrieval", "search", "evidence"}), idempotent=True))
tool_registry.register(ToolSpec("research_knowledge", "Run bounded evidence-first research across workspace knowledge and return deduplicated cited sources.", {"type": "object", "properties": {"question": {"type": "string"}, "max_queries": {"type": "integer", "minimum": 1, "maximum": 8}, "results_per_query": {"type": "integer", "minimum": 1, "maximum": 20}}, "required": ["question", "max_queries", "results_per_query"], "additionalProperties": False}, "low", research_knowledge, timeout_seconds=45.0, cost_units=0.8, capabilities=frozenset({"research", "knowledge_retrieval", "evidence", "synthesis"}), idempotent=True))
