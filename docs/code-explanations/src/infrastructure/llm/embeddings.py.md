# `src/infrastructure/llm/embeddings.py`

> **Layer:** Infrastructure / LLM  
> **Depends on:** `infrastructure.config`  
> **Used by (later):** RAG ingest, RAG search, semantic cache (CAG), long-term memory  
> **Phase relevance:** Phase 0 Task 0.2 (ingest), Phase 2 (RAG), Phase 5 (cache)

---

## What this file is for

**Embeddings** turn text into a list of numbers (a vector). Similar meaning → vectors close together in space.

That powers:

- **RAG** — “find tutor notes similar to this question”
- **Semantic cache (CAG)** — “have we answered something like this before?”
- **Long-term memory** — “recall facts about this student”

This file does **not** call Qdrant or Supabase. It only gives you objects that can do:

```python
embed_query("one string")      → [0.12, -0.03, ...]
embed_documents(["a", "b"])    → [[...], [...]]
```

---

## Module docstring (lines 1–16)

Two flavours, picked by call site:

| Function | Model | Dims | Used for | Speed |
|---|---|---|---|---|
| `get_default_embeddings()` | OpenAI `text-embedding-3-*` | 1536 | RAG KB, long-term memory | Network (~100ms–1s) |
| `get_local_embedder()` | MiniLM (on your machine) | 384 | Semantic cache hot path | ~30ms |

**Why two flavours?**

- **Remote (OpenAI via OpenRouter):** higher quality on diverse tutor content; costs per call
- **Local (MiniLM):** good enough for “same question, different wording”; free after download; no network

**Design rule:** call site picks the embedder — this file doesn’t decide *when*, only *how*.

For **Phase 0 Task 0.2** (ingest one doc): use `get_default_embeddings()` only.

---

## Imports (lines 18–24)

| Import | Why |
|---|---|
| `Lock` | Thread-safe singleton for local model |
| `OpenAIEmbeddings` | LangChain wrapper for OpenAI-compatible embedding APIs |
| `logger` | Log when local model loads (cold start is slow) |
| From `config` | Model name, provider routing, API key — no secrets in this file |

**Dependency direction:** `embeddings.py` → `config.py` only. Correct.

---

## Part 1: Remote embeddings — `get_default_embeddings()`

```python
def get_default_embeddings(
    batch_size: int = 100,
    show_progress: bool = False,
    **kwargs: Any,
) -> OpenAIEmbeddings:
```

### What it returns

A LangChain `OpenAIEmbeddings` object. Same pattern as `llm_provider.py`: one client class, different base URL/key.

### How you’ll use it (later)

```python
embedder = get_default_embeddings()
vector = embedder.embed_query("What is velocity?")
# vector → list of 1536 floats

vectors = embedder.embed_documents(["chunk 1", "chunk 2", "chunk 3"])
# batch embed for ingest
```

### Parameters

- **`batch_size`** — reserved for ingest scripts / LangChain callers
- **`show_progress`** — tqdm bar when embedding thousands of chunks
- **`**kwargs`** — escape hatch without editing this file

### OpenRouter branch

If `PROVIDER == "openrouter"` in `param.yaml` (your default):

- Requests go to `https://openrouter.ai/api/v1`
- Key from `OPENROUTER_API_KEY`
- Model from `EMBEDDING_MODEL` → typically `openai/text-embedding-3-small` → **1536 dimensions**

That **1536** must match:

- `EMBEDDING_DIM` in `config.py`
- Qdrant collection `size` when you create `axiom_kb`

Mismatch = Qdrant rejects upserts or search returns garbage.

---

## Part 2: Local embeddings — constants

```python
LOCAL_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
LOCAL_EMBED_DIM = 384
```

- **MiniLM-L6-v2** — small, fast, widely used (~80MB download first time)
- **384 dimensions** — different from RAG’s 1536. CAG uses its **own** Qdrant collection (`cag_cache` in config). Never mix 384-dim and 1536-dim vectors in one collection.

---

## Part 2b: Singleton state

```python
_local_singleton: Optional["LocalEmbedder"] = None
_local_lock = Lock()
```

**Why singleton?** Loading `SentenceTransformer` takes seconds and ~500MB RAM. Load once per process, reuse forever.

**Why `Lock`?** Two concurrent first requests might both try to load the model. Lock ensures only one thread initializes.

Not needed until Phase 5 (semantic cache).

---

## Part 2c: `LocalEmbedder` class

Custom wrapper instead of LangChain’s `HuggingFaceEmbeddings` — minimal interface, explicit control.

### Lazy import inside `__init__`

```python
from sentence_transformers import SentenceTransformer  # inside __init__
```

Importing `sentence_transformers` is heavy (pulls PyTorch). If you only use remote embeddings in Phase 0, you never pay that cost until `get_local_embedder()` is called.

### `normalize_embeddings=True`

Forces each vector to unit length so **cosine similarity** = dot product. Qdrant cosine search assumes comparable scales.

### `.tolist()`

`encode()` returns NumPy; Qdrant/JSON want plain Python `list[float]`.

### `embed_query` vs `embed_documents`

Same model, different call shape — mimics LangChain’s embedder contract.

---

## Part 2d: `get_local_embedder()` — double-checked locking

```python
def get_local_embedder() -> LocalEmbedder:
    global _local_singleton
    if _local_singleton is None:
        with _local_lock:
            if _local_singleton is None:
                _local_singleton = LocalEmbedder()
    return _local_singleton
```

Classic pattern: after first load, almost zero overhead.

---

## How this file fits Axiom’s User Flow

```
Student: "explain velocity"
         ↓
[Phase 5] Semantic cache?
         embed_query() via get_local_embedder()  ← 384 dims, fast
         search cag_cache collection
         ↓ miss
[Phase 2] RAG path
         embed_query() via get_default_embeddings()  ← 1536 dims
         search axiom_kb collection
         ↓
         LLM synthesizes answer
```

Two collections, two embedders, two jobs. That’s intentional.

---

## What this file does NOT do

- Create Qdrant collections
- Chunk documents
- Store vectors
- Choose remote vs local (callers decide)

It’s a **factory** — returns ready-to-use embedders.

---

## Self-check

1. Which function for ingesting tutor PDFs into Qdrant? → `get_default_embeddings()`
2. What dimension must the Qdrant collection use for RAG? → **1536** (with current config)
3. Why not use local MiniLM for RAG? → Lower quality on long diverse notes; 384 dims ≠ RAG collection
4. When does PyTorch/MiniLM load? → First call to `get_local_embedder()` only
5. Where is the model name for remote embeddings set? → `config.py` → `EMBEDDING_MODEL` from YAML

---

## Optional mini-experiment

```bash
export PYTHONPATH=src
python
```

```python
from dotenv import load_dotenv
load_dotenv()

from infrastructure.llm.embeddings import get_default_embeddings

e = get_default_embeddings()
v = e.embed_query("velocity in physics")
print(len(v), v[:3])  # expect 1536 and three floats
```

---

*Last updated: July 2026 — Phase 0 learning notes*
