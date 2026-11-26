"""
Rate limiting (tiêu chí 7).

Yêu cầu:
  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window)
  • Vượt giới hạn → HTTP 429, nên kèm header Retry-After
  • State lưu trong Redis để mọi worker / instance dùng chung và vẫn còn sau khi
    restart agent (script chấm sẽ restart agent để kiểm tra)
"""
import hashlib
import time
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

_SLIDING_WINDOW_SCRIPT = """
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cutoff = now - window
redis.call("ZREMRANGEBYSCORE", KEYS[1], "-inf", cutoff)
local count = redis.call("ZCARD", KEYS[1])
local limit = tonumber(ARGV[3])
if count >= limit then
    local oldest = redis.call("ZRANGE", KEYS[1], 0, 0, "WITHSCORES")
    local retry_after = math.max(1, math.ceil(window - (now - tonumber(oldest[2]))))
    return {0, retry_after}
end
redis.call("ZADD", KEYS[1], now, ARGV[4])
redis.call("EXPIRE", KEYS[1], window)
return {1, 0}
"""


def check_rate_limit(key: str) -> None:
    key_digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    now = time.time()
    allowed, retry_after = r.eval(
        _SLIDING_WINDOW_SCRIPT,
        1,
        f"rate_limit:{key_digest}",
        now,
        60,
        settings.rate_limit_per_minute,
        f"{now}:{uuid.uuid4().hex}",
    )
    if not int(allowed):
        retry_after = int(retry_after)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )
