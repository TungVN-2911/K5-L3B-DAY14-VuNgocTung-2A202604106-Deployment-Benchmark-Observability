"""
Production AI Agent — Part 6 Final Project (bản khung)

Hoàn thành các TODO để đạt đủ 12 tiêu chí trong README.md, rồi kiểm tra:
    python check_production_ready.py

Bản khung này chạy được (uvicorn app.main:app) nhưng chưa đạt tiêu chí nào.
"""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "event": getattr(record, "event_name", record.getMessage()),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


logger = logging.getLogger("production_agent")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)

@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        r.close()
        logger.info(
            "shutdown_completed",
            extra={"event_name": "shutdown_completed", "fields": {}},
        )


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis is not ready")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, _api_key: str = Depends(verify_api_key)) -> dict[str, str]:
    check_rate_limit(_api_key)
    check_budget()

    started_at = time.perf_counter()
    answer = llm_ask(body.question)
    record_cost(
        input_tokens=max(1, len(body.question.split())),
        output_tokens=max(1, len(answer.split())),
    )
    logger.info(
        "request_completed",
        extra={
            "event_name": "request_completed",
            "fields": {
                "path": "/ask",
                "status": 200,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "question_length": len(body.question),
            },
        },
    )
    return {"question": body.question, "answer": answer}
