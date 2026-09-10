from dataclasses import dataclass
from typing import Any, Callable

from nexus.core.data_engine import DataIntelligenceEngine
from nexus.core.data_pipeline import DataPipeline


RISK_LEVELS = {"low", "medium", "high"}
PERMISSION_LEVELS = {"read", "modify", "high_risk"}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    risk_level: str
    handler: Callable[..., Any]
    permission: str = "read"
    timeout_seconds: float = 30.0
    cost_units: float = 0.0
    sandbox_required: bool = False

    def __post_init__(self) -> None:
        if self.risk_level not in RISK_LEVELS:
            raise ValueError(f"Unsupported risk level: {self.risk_level}")
        if self.permission not in PERMISSION_LEVELS:
            raise ValueError(f"Unsupported permission level: {self.permission}")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self.cost_units < 0:
            raise ValueError("cost_units cannot be negative")

    def as_openai_tool(self) -> dict[str, Any]:
        return {"type": "function", "name": self.name, "description": self.description, "parameters": self.input_schema, "strict": True}


class ToolRegistry:
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

    def openai_tools(self) -> list[dict[str, Any]]:
        return [tool.as_openai_tool() for tool in self._tools.values()]


def calculator(expression: str) -> dict[str, str]:
    """Evaluate basic arithmetic using a restricted expression character set."""
    allowed = set("0123456789+-*/(). %")
    if not expression or any(char not in allowed for char in expression):
        raise ValueError("Expression contains unsupported characters")
    try:
        result = eval(expression, {"__builtins__": {}}, {})
    except Exception as exc:
        raise ValueError("Invalid arithmetic expression") from exc
    return {"expression": expression, "result": str(result)}


def profile_dataset(csv_text: str) -> dict[str, Any]:
    """Profile a UTF-8 CSV payload without executing user-supplied code."""
    engine = DataIntelligenceEngine()
    frame = engine.load_bytes(csv_text.encode("utf-8"), "csv")
    profile = engine.profile(frame)
    return {
        "rows": profile.rows,
        "columns": profile.columns,
        "duplicate_rows": profile.duplicate_rows,
        "null_columns": [
            {"column": c.name, "null_count": c.null_count, "null_ratio": c.null_ratio}
            for c in profile.column_profiles if c.null_count
        ],
    }


def analyze_dataset(csv_text: str) -> dict[str, Any]:
    """Run the conservative NEXUS cleaning + EDA pipeline over CSV text."""
    if not csv_text.strip():
        raise ValueError("CSV payload cannot be empty")
    frame = DataIntelligenceEngine().load_bytes(csv_text.encode("utf-8"), "csv")
    return DataPipeline().analyze(frame)


tool_registry = ToolRegistry()
tool_registry.register(ToolSpec(
    name="calculator", description="Perform basic arithmetic calculations.",
    input_schema={"type": "object", "properties": {"expression": {"type": "string", "description": "A basic arithmetic expression."}}, "required": ["expression"], "additionalProperties": False},
    risk_level="low", permission="read", timeout_seconds=5.0, cost_units=0.0, handler=calculator,
))
tool_registry.register(ToolSpec(
    name="profile_dataset", description="Profile a UTF-8 CSV dataset and identify missing values, duplicates, and constant columns.",
    input_schema={"type": "object", "properties": {"csv_text": {"type": "string", "description": "The complete UTF-8 CSV payload to analyze."}}, "required": ["csv_text"], "additionalProperties": False},
    risk_level="low", permission="read", timeout_seconds=15.0, cost_units=0.1, handler=profile_dataset,
))
tool_registry.register(ToolSpec(
    name="analyze_dataset", description="Analyze a CSV dataset: create a cleaning plan, apply conservative cleaning, and produce exploratory statistics.",
    input_schema={"type": "object", "properties": {"csv_text": {"type": "string", "description": "The complete UTF-8 CSV payload to analyze."}}, "required": ["csv_text"], "additionalProperties": False},
    risk_level="medium", permission="read", timeout_seconds=30.0, cost_units=0.5, handler=analyze_dataset,
))
