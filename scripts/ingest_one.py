#!/usr/bin/env python3
"""
Phase 0 — ingest one tutor document into Qdrant and test retrieval.

Run from project root:
    make ingest
    # or with custom query:
    PYTHONPATH=src .venv/bin/python scripts/ingest_one.py --query "what is velocity"

Prerequisite: smoke_test.py all PASS.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

DEFAULT_DOC = PROJECT_ROOT / "data" / "knowledge_base" / "lesson_velocity.md"
DEFAULT_QUERY = "what is velocity"


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Simple fixed-size chunker with overlap — good enough for Phase 0."""
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def ensure_collection(client, collection_name: str, vector_size: int) -> None:
    from qdrant_client.models import Distance, VectorParams

    existing = {c.name for c in client.get_collections().collections}
    if collection_name in existing:
        info = client.get_collection(collection_name)
        current_size = info.config.params.vectors.size  # type: ignore[union-attr]
        if current_size != vector_size:
            raise ValueError(
                f"Collection '{collection_name}' has dim {current_size}, "
                f"but EMBEDDING_DIM={vector_size}. Use a new collection name or delete the old one."
            )
        return

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    print(f"Created collection '{collection_name}' (dim={vector_size}, cosine)")


def ingest(doc_path: Path, query: str, top_k: int = 3) -> int:
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct

    from infrastructure.config import EMBEDDING_DIM, QDRANT_API_KEY, QDRANT_COLLECTION_NAME, QDRANT_URL
    from infrastructure.llm.embeddings import get_default_embeddings

    if not doc_path.exists():
        raise FileNotFoundError(f"Document not found: {doc_path}")

    text = doc_path.read_text(encoding="utf-8")
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError(f"No content in {doc_path}")

    print(f"Document: {doc_path.name} ({len(text)} chars → {len(chunks)} chunks)")

    embedder = get_default_embeddings()
    vectors = embedder.embed_documents(chunks)
    if len(vectors[0]) != EMBEDDING_DIM:
        raise ValueError(f"Expected {EMBEDDING_DIM} dims, got {len(vectors[0])}")

    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30)
    ensure_collection(client, QDRANT_COLLECTION_NAME, EMBEDDING_DIM)

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "text": chunk,
                "source": doc_path.name,
                "chunk_index": i,
            },
        )
        for i, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]

    client.upsert(collection_name=QDRANT_COLLECTION_NAME, points=points)
    print(f"Upserted {len(points)} points → '{QDRANT_COLLECTION_NAME}'")

    query_vector = embedder.embed_query(query)
    hits = client.search(
        collection_name=QDRANT_COLLECTION_NAME,
        query_vector=query_vector,
        limit=top_k,
    )

    print(f"\nQuery: {query!r}")
    print("-" * 60)
    if not hits:
        print("No results — check collection and embedding model.")
        return 1

    for rank, hit in enumerate(hits, 1):
        preview = (hit.payload or {}).get("text", "")[:200].replace("\n", " ")
        print(f"  [{rank}] score={hit.score:.4f}  {preview}...")

    best = hits[0]
    best_text = (best.payload or {}).get("text", "").lower()
    if "velocity" in best_text or "velocity" in query.lower():
        print("\nRetrieval looks good — top chunk matches the topic.")
        return 0

    print("\nWarning: top chunk may not match query — review content or thresholds.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 — ingest one doc into Qdrant")
    parser.add_argument("--file", type=Path, default=DEFAULT_DOC, help="Markdown/text file to ingest")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Test search query after ingest")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    try:
        return ingest(args.file, args.query, args.top_k)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
