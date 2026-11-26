"""Application settings loaded from environment variables."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    port: int
    environment: str
    agent_api_key: str
    redis_url: str
    rate_limit_per_minute: int
    daily_budget_usd: float


def _positive_int(name: str, default: str) -> int:
    value = int(os.getenv(name, default))
    if value < 1:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _positive_float(name: str, default: str) -> float:
    value = float(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _budget() -> float:
    if "DAILY_BUDGET_USD" in os.environ:
        return _positive_float("DAILY_BUDGET_USD", "1.0")
    return _positive_float(
        "MONTHLY_BUDGET_USD",
        os.getenv("MONTHLY_BUDGET_USD", "1.0"),
    )


settings = Settings(
    port=_positive_int("PORT", "8000"),
    environment=os.getenv("ENVIRONMENT", "development"),
    agent_api_key=os.getenv("AGENT_API_KEY", ""),
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    rate_limit_per_minute=_positive_int("RATE_LIMIT_PER_MINUTE", "10"),
    daily_budget_usd=_budget(),
)
