"""
Cost guard (tiêu chí 8).

Yêu cầu:
  • Cộng dồn chi phí LLM (tính theo token) vào Redis
  • Tổng chi phí vượt DAILY_BUDGET_USD (hoặc MONTHLY_BUDGET_USD) → HTTP 402
"""
from datetime import datetime, time as datetime_time, timedelta, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_RECORD_COST_SCRIPT = """
redis.call("INCRBYFLOAT", KEYS[1], ARGV[1])
if redis.call("TTL", KEYS[1]) < 0 then
    redis.call("EXPIREAT", KEYS[1], ARGV[2])
end
return 1
"""


def _daily_cost_key() -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    return f"llm_cost:daily:{today}"


def _next_utc_midnight_timestamp() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = now.date() + timedelta(days=1)
    midnight = datetime.combine(tomorrow, datetime_time.min, tzinfo=timezone.utc)
    return int(midnight.timestamp())


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    total_cost = float(r.get(_daily_cost_key()) or 0)
    if total_cost >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Daily budget exceeded",
                "spent_usd": round(total_cost, 8),
                "budget_usd": settings.daily_budget_usd,
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts must be non-negative")

    cost = (
        input_tokens / 1000 * PRICE_INPUT_PER_1K
        + output_tokens / 1000 * PRICE_OUTPUT_PER_1K
    )
    r.eval(
        _RECORD_COST_SCRIPT,
        1,
        _daily_cost_key(),
        f"{cost:.12f}",
        _next_utc_midnight_timestamp(),
    )
    return cost
