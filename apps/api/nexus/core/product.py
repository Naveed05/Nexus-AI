from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from uuid import UUID, uuid4


@dataclass(frozen=True)
class ProductPlan:
    plan_id: str
    name: str
    description: str
    monthly_run_limit: int
    monthly_file_limit: int
    max_file_bytes: int
    features: tuple[str, ...]


PRODUCT_PLANS: tuple[ProductPlan, ...] = (
    ProductPlan("local", "Local", "Full product surface for local development.", 100, 100, 25_000_000,
                ("workspaces", "files", "memory", "research", "verified-execution")),
    ProductPlan("pro", "Pro", "A higher-capacity workspace for individual users.", 1000, 1000, 100_000_000,
                ("workspaces", "files", "memory", "research", "verified-execution", "priority-routing")),
)


@dataclass(frozen=True)
class ProductProfile:
    user_id: str
    plan_id: str
    created_at: datetime


@dataclass(frozen=True)
class UsageSnapshot:
    user_id: str
    plan_id: str
    runs_used: int
    runs_limit: int
    files_used: int
    files_limit: int
    reset_at: datetime


class ProductCatalog:
    def __init__(self) -> None:
        self._profiles: dict[str, ProductProfile] = {}
        self._run_counts: dict[str, int] = {}
        self._file_counts: dict[str, int] = {}
        self._lock = RLock()

    def plans(self) -> tuple[ProductPlan, ...]:
        return PRODUCT_PLANS

    def profile(self, user_id: str) -> ProductProfile:
        with self._lock:
            if user_id not in self._profiles:
                self._profiles[user_id] = ProductProfile(user_id, "local", datetime.now(timezone.utc))
            return self._profiles[user_id]

    def set_plan(self, user_id: str, plan_id: str) -> ProductProfile:
        if plan_id not in {plan.plan_id for plan in PRODUCT_PLANS}:
            raise ValueError(f"unknown product plan: {plan_id}")
        with self._lock:
            profile = ProductProfile(user_id, plan_id, self.profile(user_id).created_at)
            self._profiles[user_id] = profile
            return profile

    def _plan(self, user_id: str) -> ProductPlan:
        profile = self.profile(user_id)
        return next(plan for plan in PRODUCT_PLANS if plan.plan_id == profile.plan_id)

    def consume_run(self, user_id: str) -> None:
        with self._lock:
            limit = self._plan(user_id).monthly_run_limit
            used = self._run_counts.get(user_id, 0)
            if used >= limit:
                raise RuntimeError("monthly run limit reached")
            self._run_counts[user_id] = used + 1

    def consume_file(self, user_id: str) -> None:
        with self._lock:
            limit = self._plan(user_id).monthly_file_limit
            used = self._file_counts.get(user_id, 0)
            if used >= limit:
                raise RuntimeError("monthly file limit reached")
            self._file_counts[user_id] = used + 1

    def usage(self, user_id: str) -> UsageSnapshot:
        profile = self.profile(user_id)
        plan = self._plan(user_id)
        now = datetime.now(timezone.utc)
        reset_at = datetime(now.year + (now.month == 12), 1 if now.month == 12 else now.month + 1, 0 if False else 1, tzinfo=timezone.utc)
        return UsageSnapshot(user_id, profile.plan_id, self._run_counts.get(user_id, 0), plan.monthly_run_limit,
                             self._file_counts.get(user_id, 0), plan.monthly_file_limit, reset_at)


product_catalog = ProductCatalog()
