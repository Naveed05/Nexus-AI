from dataclasses import dataclass

from nexus.core.cross_memory_reasoner import CrossMemoryReasoning, CrossMemoryReasoner
from nexus.core.decision_engine import Decision, DecisionEngine
from nexus.core.decision_guard import DecisionGuard, DecisionGuardResult
from nexus.core.failure_predictor import FailurePrediction, FailurePredictor
from nexus.core.knowledge_synthesizer import KnowledgeSynthesis, KnowledgeSynthesizer
from nexus.core.orchestrator import TaskDecomposer, TaskPlan
from nexus.core.plan_optimizer import PlanOptimization, PlanOptimizer
from nexus.core.reasoning_engine import ReasoningAssessment, ReasoningEngine
from nexus.core.reasoning_improvement import ReasoningImprovement, ReasoningImprovementLoop
from nexus.core.risk_predictor import RiskPrediction, RiskPredictor
from nexus.core.self_critique import ReasoningCritique, SelfCritiqueEngine
from nexus.core.strategy_planner import StrategyAwarePlanner, StrategyPlan
from nexus.core.strategy_selector import DynamicStrategySelector, StrategySelection
from nexus.core.task import Task


@dataclass(frozen=True)
class AdvancedIntelligenceResult:
    """Complete, deterministic intelligence assessment with no autonomous execution."""

    plan: TaskPlan
    assessment: ReasoningAssessment
    critique: ReasoningCritique
    improvement: ReasoningImprovement
    optimization: PlanOptimization
    strategy: StrategySelection
    strategy_plan: StrategyPlan
    risk: RiskPrediction
    failure: FailurePrediction
    knowledge: KnowledgeSynthesis
    memory_reasoning: CrossMemoryReasoning
    decision: Decision
    safety: DecisionGuardResult


class AdvancedIntelligencePipeline:
    """Compose Phase 12 intelligence stages into one bounded decision pipeline."""

    def __init__(self) -> None:
        self._decomposer = TaskDecomposer()
        self._reasoner = ReasoningEngine()
        self._critic = SelfCritiqueEngine()
        self._improver = ReasoningImprovementLoop()
        self._optimizer = PlanOptimizer()
        self._selector = DynamicStrategySelector()
        self._strategy_planner = StrategyAwarePlanner()
        self._risk = RiskPredictor()
        self._failure = FailurePredictor()
        self._synthesizer = KnowledgeSynthesizer()
        self._memory_reasoner = CrossMemoryReasoner(self._synthesizer)
        self._decider = DecisionEngine()
        self._guard = DecisionGuard()

    def assess(self, task: Task, memories: tuple[str, ...] | list[str] = ()) -> AdvancedIntelligenceResult:
        plan = self._decomposer.decompose(task)
        assessment = self._reasoner.assess(task)
        critique = self._critic.critique(task, assessment)
        improvement = self._improver.improve(assessment, critique)
        optimization = self._optimizer.optimize(plan, improvement.improved)
        strategy = self._selector.select(improvement.improved, optimization)
        strategy_plan = self._strategy_planner.adapt(plan, strategy)
        risk = self._risk.predict(improvement.improved, optimization, plan)
        failure = self._failure.predict(improvement.improved, risk, plan)
        evidence = tuple(memories) if memories else (task.context or "",)
        knowledge = self._synthesizer.synthesize(evidence, query=task.objective)
        memory_reasoning = self._memory_reasoner.reason(evidence, query=task.objective)
        decision = self._decider.decide(improvement.improved, optimization, risk, strategy)
        safety = self._guard.evaluate(decision)
        return AdvancedIntelligenceResult(
            plan=plan,
            assessment=assessment,
            critique=critique,
            improvement=improvement,
            optimization=optimization,
            strategy=strategy,
            strategy_plan=strategy_plan,
            risk=risk,
            failure=failure,
            knowledge=knowledge,
            memory_reasoning=memory_reasoning,
            decision=decision,
            safety=safety,
        )
