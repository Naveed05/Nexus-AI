from dataclasses import dataclass
from typing import Type


@dataclass(frozen=True)
class RetryPolicy:
    """Deterministic retry policy for transient runtime failures."""

    max_attempts: int = 1
    retryable_exceptions: tuple[Type[BaseException], ...] = (TimeoutError, ConnectionError)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if not self.retryable_exceptions:
            raise ValueError("retryable_exceptions cannot be empty")
        if any(not isinstance(exc, type) or not issubclass(exc, BaseException) for exc in self.retryable_exceptions):
            raise TypeError("retryable_exceptions must contain exception types")

    def allows(self, exc: BaseException, attempt: int) -> bool:
        if attempt < 1:
            raise ValueError("attempt must be at least 1")
        return attempt < self.max_attempts and isinstance(exc, self.retryable_exceptions)
