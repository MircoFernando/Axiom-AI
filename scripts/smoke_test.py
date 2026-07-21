#!/usr/bin/env python3
"""
Phase 0 — connection smoke test.

Verifies config, LLM, Supabase Postgres, and Qdrant Cloud before building agents.

Run from project root:
    make smoke
    # or
    PYTHONPATH=src .venv/bin/python scripts/smoke_test.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Project root = parent of scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)


def _status(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def _message_text(content: object) -> str:
    """Normalize AIMessage.content to str (may be str or multimodal blocks)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts)
    return str(content)


def check_config() -> tuple[bool, str]:
    """Check 1 — YAML config loads and required API key exists."""
    try:
        from infrastructure.config import (
            CHAT_MODEL,
            EMBEDDING_DIM,
            EMBEDDING_MODEL,
            PROVIDER,
            QDRANT_COLLECTION_NAME,
            validate,
        )

        validate()
        detail = (
            f"provider={PROVIDER}, chat={CHAT_MODEL}, "
            f"embed={EMBEDDING_MODEL} ({EMBEDDING_DIM}d), "
            f"qdrant_collection={QDRANT_COLLECTION_NAME}"
        )
        return True, detail
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}" if str(exc) else repr(exc)


def check_llm() -> tuple[bool, str]:
    """Check 2 — at least one chat LLM responds."""
    from langchain_core.messages import HumanMessage

    from infrastructure.config import get_api_key
    from infrastructure.llm.llm_provider import get_chat_llm, get_fast_chat_llm

    prompt = [HumanMessage(content="Your reply must be the word pong")]

    # Prefer OpenRouter (chat) — matches default stack
    if get_api_key("openrouter"):
        try:
            from infrastructure.config import CHAT_MODEL

            llm = get_chat_llm(max_tokens=16)
            response = llm.invoke(prompt)
            text = _message_text(response.content).strip().lower()
            if "pong" in text:
                return True, f"get_chat_llm() ({CHAT_MODEL}) replied: {text[:40]}"
            return False, f"get_chat_llm() unexpected reply ({CHAT_MODEL}): {text}"
        except Exception as exc:
            openrouter_err = str(exc)
    else:
        openrouter_err = "OPENROUTER_API_KEY not set"

    # Fallback: Groq fast chat
    if get_api_key("groq"):
        try:
            llm = get_fast_chat_llm(max_tokens=16)
            response = llm.invoke(prompt)
            text = _message_text(response.content).strip().lower()
            if "pong" in text:
                return True, f"get_fast_chat_llm() (Groq) replied: {text[:40]}"
            return False, f"get_fast_chat_llm() unexpected reply: {text[:80]}"
        except Exception as exc:
            return False, f"OpenRouter failed ({openrouter_err}); Groq failed ({exc})"

    return False, f"No LLM available. OpenRouter: {openrouter_err}. GROQ_API_KEY not set."


def _mask_db_url(url: str) -> str:
    import re
    return re.sub(r":([^:@/]+)@", ":***@", url)


def check_supabase() -> tuple[bool, str]:
    """Check 3 — Supabase Postgres accepts a connection."""
    import asyncpg

    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url or "xxxxx" in db_url:
        return False, "SUPABASE_DB_URL not set in .env"

    host_hint = _mask_db_url(db_url)

    async def _probe() -> tuple[bool, str]:
        # Transaction pooler (port 6543) uses PgBouncer — disable prepared statement cache
        conn = await asyncpg.connect(db_url, timeout=15, statement_cache_size=0)
        try:
            one = await conn.fetchval("SELECT 1")
            if one != 1:
                return False, f"SELECT 1 returned {one!r}"

            ext = await conn.fetchval(
                "SELECT extname FROM pg_extension WHERE extname = 'vector'"
            )
            pgvector = "installed" if ext else "missing (needed Phase 3+)"
            return True, f"SELECT 1 ok, pgvector={pgvector}"
        finally:
            await conn.close()

    try:
        return asyncio.run(_probe())
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}" if str(exc) else repr(exc)
        return False, f"{detail} | url={host_hint}"


def check_qdrant() -> tuple[bool, str]:
    """Check 4 — Qdrant Cloud lists collections."""
    from qdrant_client import QdrantClient

    from infrastructure.config import QDRANT_API_KEY, QDRANT_URL

    if not QDRANT_URL or "xxxxx" in QDRANT_URL:
        return False, "QDRANT_URL not set in .env"
    if not QDRANT_API_KEY or QDRANT_API_KEY.startswith("your_"):
        return False, "QDRANT_API_KEY not set in .env"

    try:
        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=15)
        names = [c.name for c in client.get_collections().collections]
        return True, f"{len(names)} collection(s): {names or '(empty — ok for Phase 0)'}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}" if str(exc) else repr(exc)


def main() -> int:
    checks = [
        ("Config", check_config),
        ("LLM", check_llm),
        ("Supabase", check_supabase),
        ("Qdrant", check_qdrant),
    ]

    print("=" * 60)
    print("Axiom AI — Phase 0 Smoke Test")
    print("=" * 60)

    all_passed = True
    for i, (name, fn) in enumerate(checks, 1):
        passed, detail = fn()
        all_passed = all_passed and passed
        print(f"[{i}/4] {name:12} {_status(passed):5}  {detail}")

    print("=" * 60)
    if all_passed:
        print("ALL CHECKS PASSED — ready for Task 0.2 (make ingest)")
        return 0
    print("SOME CHECKS FAILED — fix .env / network before Phase 1")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
