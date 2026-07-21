"""Redis-backed inbound message queue."""

from __future__ import annotations

from typing import Optional

import redis
from loguru import logger

from infrastructure.config import MESSAGE_QUEUE_KEY, REDIS_URL
from services.messaging.schemas import InboundMessageJob

_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """Return a singleton Redis client (decode responses as str)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        _redis_client.ping()
        logger.info("Connected to Redis at {}", REDIS_URL)
    return _redis_client


def enqueue_message(job: InboundMessageJob) -> str:
    """
    Push a job onto the inbound message queue (FIFO).

    Returns:
        The queue key used.
    """
    client = get_redis_client()
    client.rpush(MESSAGE_QUEUE_KEY, job.model_dump_json())
    logger.info(
        "Enqueued message {} from {} (tenant={})",
        job.message_id,
        job.from_phone,
        job.identity.tenant_id,
    )
    return MESSAGE_QUEUE_KEY


def dequeue_message(timeout_seconds: int = 5) -> Optional[InboundMessageJob]:
    """
    Block up to *timeout_seconds* for the next inbound job.

    Returns:
        Parsed job, or ``None`` on timeout.
    """
    client = get_redis_client()
    result = client.blpop(MESSAGE_QUEUE_KEY, timeout=timeout_seconds)
    if result is None:
        return None

    _, raw = result
    job = InboundMessageJob.model_validate_json(raw)
    logger.debug("Dequeued message {}", job.message_id)
    return job


def queue_depth() -> int:
    """Return the number of pending jobs (useful for health checks)."""
    client = get_redis_client()
    return int(client.llen(MESSAGE_QUEUE_KEY))
