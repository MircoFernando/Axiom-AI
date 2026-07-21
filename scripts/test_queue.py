#!/usr/bin/env python3
"""
Phase 1 Step 2 — verify job schema + enqueue/dequeue round-trip.

Usage:
    make redis        # if not already running
    make test-queue
"""

from dotenv import load_dotenv

load_dotenv(override=True)

import sys

from services.messaging.queue import dequeue_message, enqueue_message, queue_depth
from services.messaging.schemas import IdentityContext, InboundMessageJob


def main() -> int:
    print("=" * 50)
    print("Phase 1 Step 2 — Message queue test")
    print("=" * 50)

    identity = IdentityContext(
        role="student",
        tenant_id="dev-tenant-001",
        student_id="stu-dev-001",
        class_ids=["physics-al-2026"],
    )

    job = InboundMessageJob(
        message_id="wamid.test001",
        from_phone="94771234567",
        text="What is velocity?",
        received_at=1710000000.0,
        identity=identity,
        raw_metadata={"phone_number_id": "111"},
    )

    try:
        enqueue_message(job)
    except Exception as exc:
        print(f"FAIL  enqueue_message: {exc}")
        print("      Run: make redis")
        return 1

    depth = queue_depth()
    if depth < 1:
        print(f"FAIL  queue_depth expected >= 1, got {depth}")
        return 1

    print(f"PASS  enqueued job (queue depth={depth})")

    got = dequeue_message(timeout_seconds=2)
    if got is None:
        print("FAIL  dequeue_message timed out")
        return 1

    if got.message_id != job.message_id:
        print(f"FAIL  message_id mismatch: {got.message_id!r}")
        return 1

    if got.text != job.text:
        print(f"FAIL  text mismatch: {got.text!r}")
        return 1

    if got.identity.tenant_id != identity.tenant_id:
        print(f"FAIL  tenant_id mismatch: {got.identity.tenant_id!r}")
        return 1

    if got.identity.class_ids != identity.class_ids:
        print(f"FAIL  class_ids mismatch: {got.identity.class_ids!r}")
        return 1

    print("PASS  dequeued job with matching identity + payload")
    print("=" * 50)
    print("Step 2 complete — message queue is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
