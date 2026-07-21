# Axiom AI — Code Explanations

**Project:** Axiom AI (Tutor AI)  
**Purpose:** Structured walkthroughs of infrastructure code — what, why, and how  
**Audience:** Developer learning the codebase before Phase 0–6 implementation  
**Export:** Open in Cursor/VS Code → Print or Markdown PDF → `CodeExplanation.pdf`

---

## Table of contents

1. [How to use this document](#how-to-use-this-document)
2. [Infrastructure overview](#infrastructure-overview)
3. [`embeddings.py`](#srcinfrastructurellmembeddingspy)
4. [`llm_provider.py`](#srcinfrastructurellmllm_providerpy)
5. [LLM Provider — deep dives (FAQ)](#llm-provider--deep-dives-faq)
6. [`observability.py`](#srcinfrastructureobservabilitypy)
7. [Phase 1 — Redis & message queue](#phase-1--redis--message-queue)
8. [Index of pending files](#index-of-pending-files)

---

## How to use this document

- **Per-file docs** also live under `docs/code-explanations/src/...` mirroring the repo.
- When you ask the agent to explain a new file, it should update both the per-file `.md` and this master doc.
- **Stale docstrings:** trust `config.py` over comments in source files.

**Run imports from project root:**

```bash
export PYTHONPATH=src
python scripts/your_script.py
```

---

## Infrastructure overview

`src/infrastructure/` is **plumbing** — not business logic, agents, or webhooks.

```
config.yaml + .env
       ↓
   config.py  ← single source of truth
       ↓
  ┌────┴────┬──────────┬────────────┐
  ↓         ↓          ↓              ↓
log.py  llm/*   observability.py  utils.py
                              models.py (RAG data shapes)
```

| Layer (later) | Depends on infrastructure for… |
|---|---|
| `api/` | config, logging, LLM clients |
| `agents/` | config, LLM factories, observability |
| `services/rag/` | config thresholds, embeddings, utils |
| `memory/` | config memory limits, DB clients (not built yet) |
| `workers/` | config, logging |

**Rule:** infrastructure never imports from agents or API. One-way dependency only.

---

## `src/infrastructure/llm/embeddings.py`

> Full per-file copy: [`src/infrastructure/llm/embeddings.py.md`](src/infrastructure/llm/embeddings.py.md)

### What this file is for

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

### Two flavours (by design)

| Function | Model | Dims | Used for | Speed |
|---|---|---|---|---|
| `get_default_embeddings()` | OpenAI `text-embedding-3-*` | 1536 | RAG KB, long-term memory | Network (~100ms–1s) |
| `get_local_embedder()` | MiniLM (on your machine) | 384 | Semantic cache hot path | ~30ms |

**Phase 0 Task 0.2:** use `get_default_embeddings()` only.

### `get_default_embeddings()`

- Returns LangChain `OpenAIEmbeddings`
- If `PROVIDER == "openrouter"`: routes to OpenRouter with `OPENROUTER_API_KEY`
- **1536 dimensions** must match `EMBEDDING_DIM` in config and Qdrant collection size

### `LocalEmbedder` + `get_local_embedder()`

- Model: `sentence-transformers/all-MiniLM-L6-v2` (384 dims)
- Lazy import of PyTorch/sentence-transformers (heavy — only loads when called)
- `normalize_embeddings=True` for correct cosine similarity in Qdrant
- **Singleton + Lock:** load model once per process, thread-safe

### User Flow mapping

```
[Phase 5] Cache miss path → get_local_embedder() → cag_cache (384 dims)
[Phase 2] RAG path        → get_default_embeddings() → axiom_kb (1536 dims)
```

### Self-check

1. Ingest tutor notes? → `get_default_embeddings()`
2. RAG Qdrant dimension? → **1536**
3. Why not MiniLM for RAG? → Quality + wrong dimension for RAG collection
4. When does PyTorch load? → First `get_local_embedder()` call
5. Remote model name? → `EMBEDDING_MODEL` in `config.py`

---

## `src/infrastructure/llm/llm_provider.py`

> Full per-file copy: [`src/infrastructure/llm/llm_provider.py.md`](src/infrastructure/llm/llm_provider.py.md)

### What this file is for

Builds **chat LLMs** (text in → text out). Four role-specific clients:

| Getter | Model (config.py) | Provider | Role |
|---|---|---|---|
| `get_router_llm()` | `llama-3.3-70b-versatile` | Groq | Intent classification |
| `get_fast_chat_llm()` | `llama-3.3-70b-versatile` | Groq | Greetings / direct route |
| `get_extractor_llm()` | `llama-3.1-8b-instant` | Groq | Structured extraction |
| `get_chat_llm()` | `google/gemini-2.5-flash` | OpenRouter | RAG synthesis / tutor voice |

### `_build_llm()` (private)

Internal factory. Wires `ChatOpenAI` to OpenRouter, Groq, or OpenAI via base URL + API key. Public getters hide model/provider selection.

### User Flow mapping

```
Cache miss → get_router_llm() → route
  direct   → get_fast_chat_llm()
  academic → RAG chunks + get_chat_llm()
  finance  → tools + get_chat_llm() (+ get_extractor_llm() later)
```

### Keys in `.env`

- Groq getters → `GROQ_API_KEY`
- Chat getter → `OPENROUTER_API_KEY`

### Self-check (short)

1. `_build_llm` private → intent-specific public getters
2. Shared 70B → same weights, different prompts/temperatures
3. Phase 2 synthesis → `get_chat_llm()`
4. admissions vs finance → `get_router_llm()`
5. `ChatOpenAI` for Groq → OpenAI-compatible API protocol

---

## LLM Provider — deep dives (FAQ)

Expanded explanations for the five self-check questions.

### 1. Why is `_build_llm` private (leading `_`)?

In Python, `_` means **internal — don’t call from outside this module.**

**Public (use these):**

```python
get_router_llm()
get_chat_llm()
get_fast_chat_llm()
get_extractor_llm()
```

**Private (this file only):**

```python
_build_llm(model, provider, temperature, ...)
```

**Why it matters**

`_build_llm` is generic — you must pass `model` and `provider` every time. Public getters encode **intent**:

```python
router = get_router_llm()   # "I need routing"
chat = get_chat_llm()       # "I need final answers"
```

**Failure mode if everyone used `_build_llm`:**

```python
# Bug: chat model used for routing
llm = _build_llm(CHAT_MODEL, CHAT_PROVIDER)
```

Slow, expensive Gemini for every classification. Public getters lock the right model per role; change once in `config.py`.

**Analogy:** Public menu (Router special, Chat special) vs kitchen `_build_llm` (same oven, different recipes).

---

### 2. Why can router and fast chat share one model?

Both use **`llama-3.3-70b-versatile` on Groq**. Same weights — different **usage**.

| | Router | Fast chat |
|---|---|---|
| Question | What kind of request? | What to say back? |
| Output | Short JSON | Natural language |
| Temperature | `0` | `0.3` |
| Prompt | Classify: academic, finance, … | Friendly brief reply |

**Why not two models?** 8B was too unreliable for conversational replies (nonsense outputs). 70B handles both classification and short replies with one Groq key and latency profile.

**Nuance:** Shared **model name** ≠ shared **client instance**. Each getter creates a new `ChatOpenAI` object (cheap). Conversation state is not shared.

**Axiom example — "ok sir thanks":**

1. Router (temp 0): `{"route": "direct"}`
2. Fast chat (temp 0.3): `"You're welcome! Good luck with your studies."`

**"explain velocity from lesson 5":**

1. Router: `{"route": "academic"}`
2. RAG + **`get_chat_llm()`** (Gemini) — not fast chat

---

### 3. Which LLM for Phase 2 Academic RAG synthesis? → `get_chat_llm()`

Phase 2 pipeline:

```
Question → embed → search Qdrant → chunks + prompt → LLM answer → reply
                                                      ↑
                                              get_chat_llm()
```

**Why Gemini:**

- Grounded explanations from chunks
- Long context (many chunks + history)
- Quality the student reads
- Later: Singlish, tutor tone, multimodal

**Why not others:**

| LLM | Why not |
|---|---|
| `get_router_llm()` | Labels/JSON, not teaching |
| `get_extractor_llm()` | `{field: value}`, not paragraphs |
| `get_fast_chat_llm()` | OK for hi/thanks; weak for multi-chunk physics explanations |

**Mental model:** Groq 70B = internal staff; Gemini = tutor voice on hard questions.

---

### 4. Which for "is this admissions or finance?" → `get_router_llm()`

**Classification**, not teaching or chatting.

**Router output (conceptual):**

```json
{"route": "admissions", "confidence": 0.92}
```

or for bank slip + "class fee paid" → `{"route": "finance"}`

**Why `get_router_llm()`:**

- Speed — every cache miss hits router first
- Cost — thousands of messages/day
- Determinism — `temperature=0`
- Task fit — short structured decision

**Good separation:**

```
Router:  "admissions"     (label only)
Agent:   CRM tools, collect name/school
Chat:    friendly WhatsApp reply
```

**Phase 4 routing table:**

| Message | Route |
|---|---|
| "join Science 2026" | `admissions` |
| "send last week physics paper" | `resource` |
| "explain momentum" | `academic` |
| bank slip + "paid" | `finance` |
| "hi sir" | `direct` |

---

### 5. Why `ChatOpenAI` for Groq? → OpenAI API shape

**`ChatOpenAI` = client for OpenAI Chat Completions API format**, not "OpenAI company only."

Standard request:

```http
POST /v1/chat/completions
Authorization: Bearer <api_key>

{"model": "...", "messages": [{"role": "user", "content": "Hello"}], "temperature": 0}
```

| Provider | Base URL | Same LangChain class? |
|---|---|---|
| OpenAI | `api.openai.com/v1` | `ChatOpenAI` |
| OpenRouter | `openrouter.ai/api/v1` | `ChatOpenAI` + base override |
| Groq | `api.groq.com/openai/v1` | `ChatOpenAI` + base override |

Your `_build_llm` only changes URL, key, and model string.

**Why not `ChatGroq`?** One adapter, same `.invoke()` everywhere, swap models in config.

**Parallel in embeddings.py:** `OpenAIEmbeddings` used via OpenRouter — same "protocol not vendor" idea.

---

### How all five concepts fit one message

```
"Sir I paid for class" + [bank slip]

1. get_router_llm()     → finance
2. get_extractor_llm()  → {amount, date}  (Phase 6)
3. get_chat_llm()       → "Thanks, payment recorded..."

get_chat_llm() does NOT decide finance vs admissions — that's get_router_llm().
```

---

## `src/infrastructure/observability.py`

> Full per-file copy: [`src/infrastructure/observability.py.md`](src/infrastructure/observability.py.md)

### What this file is for

**Observability** answers: *“What happened when this student sent that message, and why did the bot reply that way?”*

Wraps **LangFuse** for traces, spans, LLM generations (tokens/cost), and optional remote prompt management. Business code imports this module — not LangFuse directly.

**Phase 0–4:** exists but you don’t wire it yet. **Phase 5:** add `@observe`, tag `tenant_id`, call `flush()` on shutdown.

### Configuration

| Toggle | Where | Effect |
|---|---|---|
| Tracing on/off | `param.yaml` → `observability.enabled` | `false` → `@observe` is no-op |
| LangFuse keys | `.env` → `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY` | Missing → client `None`, app still runs |
| Prompt source | `.env` → `LANGFUSE_PROMPTS=true` | Opt-in remote prompts; default = local files |

Tracing and prompt management are **independent toggles**.

### Main API

| Function | Purpose |
|---|---|
| `get_langfuse()` | Singleton LangFuse client; `None` if disabled |
| `fetch_prompt(name, fallback=..., **vars)` | LangFuse prompt or local `str.format()` fallback |
| `prefetch_prompts(names)` | Warm prompt cache at API startup |
| `@observe(name=..., as_type=...)` | Trace a function as span or generation |
| `update_current_trace(...)` | Tag trace with student phone, session, tenant |
| `update_current_observation(...)` | Attach I/O, model, token usage to current step |
| `flush()` | Send batched events before process exit |

### Trace example (Axiom)

```
Trace: whatsapp-msg-abc123
  user_id: +94771234567
  metadata: {tenant_id: "..."}
  ├─ span: guardrail → pass
  ├─ span: semantic_cache → miss
  ├─ generation: router_llm → {"route":"finance"}
  ├─ span: finance_agent
  └─ generation: chat_llm → "Payment confirmed..."
```

### Design principles

1. **Never crash the app** — missing keys, import errors, LangFuse down → no-op
2. **Local prompts by default** — code changes apply immediately in dev
3. **Separate span vs generation** — generations track LLM cost; spans track everything else
4. **Complements `log.py`** — logs for dev lines; LangFuse for request trees and billing

### Self-check

1. Crash without keys? → No
2. Disable tracing? → `observability.enabled: false`
3. Default prompt source? → Local Python files
4. `flush()` when? → API/worker shutdown
5. Wire in which phase? → Phase 5

---

## Phase 1 — Redis & message queue

**Full doc:** [`phase1-redis-message-queue.md`](phase1-redis-message-queue.md)

### What & why

Meta WhatsApp requires **200 OK within ~3 seconds**. The webhook must **enqueue** and return — not run LLM/RAG. Redis sits between FastAPI (producer) and the worker (consumer).

### Architecture (Steps 1–2 done)

```text
docker-compose.yml → Redis :6379
config.py           → REDIS_URL, MESSAGE_QUEUE_KEY
schemas.py          → IdentityContext, InboundMessageJob
queue.py            → enqueue_message (RPUSH), dequeue_message (BLPOP)
```

### Data contract (`InboundMessageJob`)

Every queued message carries **`identity.tenant_id`** and **`identity.class_ids`** for Phase 2 RAG — not read from `.env` in production.

### Verify locally

```bash
make redis && make test-redis && make test-queue
```

### Celery — later

Raw Redis LIST for Phase 1–2 (learn the pipeline). **Celery** planned Phase 5–6 for PDF ingest, OCR, retries, cron — same `InboundMessageJob` schema, different transport.

### Redis vs BackgroundTasks

| | BackgroundTasks | Redis + workers |
|---|-----------------|-----------------|
| Meta 200 | ✅ | ✅ |
| Scalable SaaS | ❌ | ✅ |
| Instant ack | ✅ (same process) | ✅ (first worker step) |

**Full comparison:** [`phase1-redis-message-queue.md`](phase1-redis-message-queue.md) — sections *Mental model* and *Redis vs FastAPI BackgroundTasks*.

### Self-check

1. Webhook command? → RPUSH via `enqueue_message`
2. Worker command? → BLPOP via `dequeue_message`
3. Celery now? → No
4. BackgroundTasks for production SaaS? → No — finish Redis path
5. Scale how? → More **worker** processes, not more queues per tenant

---

## Index of pending files

| Source file | Status |
|---|---|
| `src/infrastructure/config.py` | Pending |
| `src/infrastructure/log.py` | Pending |
| `src/infrastructure/models.py` | Pending |
| `src/infrastructure/utils.py` | Pending |
| `src/infrastructure/db/*` | Pending (not built) |

---

*Document version: 1.2 — July 2026*  
*Covers: embeddings.py, llm_provider.py, LLM Provider FAQ, observability.py, Phase 1 Redis message queue*
