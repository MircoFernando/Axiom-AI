#!/usr/bin/env python3
"""
Phase 1 Step 1 — verify Redis connection and queue push/pop.

Usage:
    docker compose up -d redis
    uv pip install redis
    make test-redis
"""

from dotenv import load_dotenv

load_dotenv(override=True)

import json
import sys

import redis

from infrastructure.config import MESSAGE_QUEUE_KEY, REDIS_URL


def main() -> int:
    print("=" * 50)
    print("Phase 1 Step 1 — Redis smoke test")
    print("=" * 50)
    print(f"REDIS_URL         = {REDIS_URL}")
    print(f"MESSAGE_QUEUE_KEY = {MESSAGE_QUEUE_KEY}")
    print()

    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        pong = client.ping()
    except redis.ConnectionError as exc:
        print(f"FAIL  Could not connect to Redis: {exc}")
        print("      Run: make redis")
        return 1

    if pong is not True:
        print(f"FAIL  PING returned {pong!r}")
        return 1

    print("PASS  PING → PONG")

    test_payload = json.dumps({"step": 1, "test": True})
    client.rpush(MESSAGE_QUEUE_KEY, test_payload)
    result = client.blpop(MESSAGE_QUEUE_KEY, timeout=2)

    if result is None:
        print("FAIL  BLPOP timed out — job not retrieved")
        return 1

    queue_name, value = result
    if queue_name != MESSAGE_QUEUE_KEY or value != test_payload:
        print(f"FAIL  Unexpected pop result: {result!r}")
        return 1

    print(f"PASS  RPUSH + BLPOP on '{MESSAGE_QUEUE_KEY}'")
    print("=" * 50)
    print("Step 1 complete — Redis is ready for the message queue.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
