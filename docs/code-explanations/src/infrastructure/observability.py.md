# `src/infrastructure/observability.py`

> **Layer:** Infrastructure / Cross-cutting  
> **Depends on:** `infrastructure.config` (optional), `.env`, LangFuse SDK  
> **Used by (later):** Agents, RAG service, chat router, API lifespan  
> **Phase relevance:** Phase 5 (production patterns) — safe to ignore in Phase 0–4

---

## What this file is for

**Observability** answers: *“What happened when this student sent that message, and why did the bot reply that way?”*

In production you need more than `logger.info()`. You need:

- **Traces** — full path of one request (webhook → router → RAG → LLM → reply)
- **Spans** — each step inside a trace (embed, search, generate)
- **Generations** — LLM calls with input/output, model name, token usage, cost
- **Metadata** — which student, which tenant, which route was chosen

This file wraps **[LangFuse](https://langfuse.com)** so the rest of your code can trace without importing LangFuse everywhere.

---

## The problem it solves (Axiom context)

A tutor asks: *“Why did the AI tell my student the wrong fee amount?”*

Without observability you grep logs and guess. With LangFuse you open one **trace** and see:

```
Trace: whatsapp-msg-abc123
  user_id: +94771234567
  session_id: student-uuid-xyz
  ├─ span: guardrail          → pass
  ├─ span: semantic_cache     → miss
  ├─ span: route              → finance
  ├─ generation: router_llm   → {"route":"finance"}  (Groq, 120 tokens)
  ├─ span: finance_agent
  ├─ generation: chat_llm     → "Your payment is confirmed..." (Gemini, 450 tokens)
  └─ total latency: 3.2s, cost: $0.002
```

That’s what this module enables — when wired in Phase 5.

---

## Configuration (two toggles)

### 1. Tracing on/off — `param.yaml`

```yaml
observability:
  enabled: true   # false → all @observe decorators become no-ops
```

Read by `_is_enabled()`. Lets you disable tracing in dev or when keys are missing.

### 2. Secrets — `.env`

```bash
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com   # optional
```

Read by `get_langfuse()`. No keys → client is `None`, app still runs.

### 3. Prompt source — separate toggle

```bash
LANGFUSE_PROMPTS=true   # optional; default OFF
```

| Setting | Prompts live in… | Tracing |
|---|---|---|
| `LANGFUSE_PROMPTS` unset/false | Local Python files (`agents/prompts/`) | Still works if keys set |
| `LANGFUSE_PROMPTS=true` | LangFuse Prompt Management dashboard | Still works |

**Why separate?** During development you edit prompts in code and want changes immediately. Remote prompt management is for ops/production tuning without redeploy.

---

## File structure (five sections)

```
1. _is_enabled()           — config flag
2. get_langfuse()          — singleton client
3. fetch_prompt()          — prompt management + local fallback
4. observe                 — tracing decorator
5. update_current_*        — enrich traces/spans
6. flush()                 — send pending events on shutdown
```

---

## Section 1: `_is_enabled()`

```python
_ENABLED: Optional[bool] = None

def _is_enabled() -> bool:
    global _ENABLED
    if _ENABLED is not None:
        return _ENABLED
    try:
        from infrastructure.config import _get_nested, _PARAMS
        _ENABLED = _get_nested(_PARAMS, "observability", "enabled", default=True)
    except Exception:
        _ENABLED = True
    return _ENABLED
```

**WHAT:** Cached boolean — is tracing allowed?

**WHY cache?** Avoid re-reading YAML on every `@observe` call.

**WHY default `True` on import error?** Fail open for tracing if config broken; missing LangFuse keys still disable client later.

**HOW to disable:** Set `observability.enabled: false` in `param.yaml`.

---

## Section 2: `get_langfuse()` — singleton client

```python
_langfuse_client = None
_initialised = False

def get_langfuse():
    ...
```

**WHAT:** One LangFuse client per process.

**WHY singleton?** Connection pooling, auth handshake once, consistent trace context.

**Decision tree:**

```
get_langfuse() called
    ↓
Already initialised? → return cached client (or None)
    ↓
_is_enabled() == False? → return None, log info
    ↓
Missing LANGFUSE_* keys? → return None, log warning
    ↓
Try Langfuse(...) → success or log error, return None
```

**Critical design:** **Never crash the app** if LangFuse is down or misconfigured. Returns `None`; callers and decorators handle it.

Same pattern as `get_local_embedder()` — lazy, once-only init flag `_initialised`.

---

## Section 3: Prompt management

### `_langfuse_prompts_enabled()`

Checks env `LANGFUSE_PROMPTS` for true/1/yes/on. Default **off**.

### `fetch_prompt(name, *, fallback, **compile_vars)`

**WHAT:** Resolve a prompt string before sending to LLM.

**HOW:**

```
LANGFUSE_PROMPTS enabled?
    YES → try client.get_prompt(name) from LangFuse
          success → compile with Mustache {{var}} syntax
          fail    → use local fallback
    NO  → fallback.format(**compile_vars)  # Python {var} syntax
```

**Example (later, in an agent):**

```python
from infrastructure.observability import fetch_prompt

system_prompt = fetch_prompt(
    "academic_assistant",
    fallback=_ACADEMIC_FALLBACK,
    tutor_name="Mr. Perera",
    subject="Physics",
)
```

**WHY fallback always required:** LangFuse prompt might not exist yet; dev works offline; no dashboard dependency for v1.

**Syntax difference:**

| Source | Template syntax |
|---|---|
| Local fallback | Python `{tutor_name}` |
| LangFuse | Mustache `{{tutor_name}}` |

### `prefetch_prompts(names)`

Called at **API startup** (Week 13: `main.py` lifespan). Loads all prompt names into LangFuse client cache so first student message doesn’t pay network latency.

Returns count warmed. No-op when `LANGFUSE_PROMPTS` is off.

---

## Section 4: `@observe` decorator

```python
def observe(*, name=None, as_type=None):
    if not _is_enabled() or _lf_observe is None:
        return _noop_decorator  # function unchanged
    return _lf_observe(name=name, as_type=as_type)
```

**WHAT:** Wraps a function so LangFuse records it as a **span** or **generation** in the current trace.

**WHY wrap LangFuse’s decorator?** Single place to disable tracing; import failure doesn’t break app.

**Usage (later):**

```python
from infrastructure.observability import observe

@observe(name="route_intent")
async def classify_intent(message: str) -> str:
    ...

@observe(name="rag_synthesis", as_type="generation")
async def synthesize_answer(context: str, question: str) -> str:
    ...
```

| `as_type` | LangFuse treats it as… | Use for |
|---|---|---|
| `None` (default) | Span | Routing, DB, cache, tool calls |
| `"generation"` | LLM generation | Chat, router JSON from LLM |

**No-op behavior:** When disabled, `@observe` returns the original function — zero overhead, no LangFuse calls.

---

## Section 5: Trace & span helpers

### `update_current_trace(user_id, session_id, metadata, tags)`

Tags the **whole request** — one WhatsApp message lifecycle.

**Axiom mapping:**

| Parameter | Axiom value |
|---|---|
| `user_id` | Student phone or `student.id` |
| `session_id` | WhatsApp thread / `session_id` from `st_turns` |
| `metadata` | `{"tenant_id": "...", "channel": "whatsapp"}` |
| `tags` | `["finance", "production"]` |

Call once at start of worker processing.

### `update_current_observation(input, output, metadata, usage, model)`

Enriches the **current span or generation** inside the trace.

**Auto-detection:**

- If `model` or `usage` provided → `update_current_generation()` (LLM call)
- Else → `update_current_span()` (generic step)

**Example after LLM call:**

```python
update_current_observation(
    input=question,
    output=answer,
    model="google/gemini-2.5-flash",
    usage={"input": 1200, "output": 180, "total": 1380},
)
```

**WHY safe no-op:** Wrapped in try/except; failures log at DEBUG — tracing never breaks student replies.

---

## Section 6: `flush()`

```python
def flush() -> None:
    """Send pending LangFuse events before process exit."""
```

LangFuse batches events asynchronously. Short scripts (smoke tests, workers) may exit before events send.

**Call `flush()`:**

- On FastAPI shutdown (lifespan)
- End of worker batch
- After integration tests that use tracing

---

## How it fits your architecture

```
WhatsApp message
      ↓
Worker starts trace
  update_current_trace(user_id=phone, session_id=..., metadata={tenant_id})
      ↓
@observe guardrail
@observe cache_lookup
@observe route_intent          ← generation if LLM router
@observe rag_retrieve
@observe synthesize_answer     ← generation
      ↓
flush() on shutdown
      ↓
LangFuse dashboard shows full tree
```

**Phase 0–4:** File exists; you don’t need to wire it yet.  
**Phase 5:** Add `@observe` to router, RAG, agents; tag traces with `tenant_id` for multi-tenant billing/debug.

---

## What this file does NOT do

- Replace `log.py` — logs are for developers; traces are for request replay and cost
- Store traces in Supabase — LangFuse is the trace store
- Automatically trace everything — you add `@observe` to functions you care about
- Enforce multi-tenant isolation in LangFuse — you pass `tenant_id` in metadata yourself

---

## Comparison with `log.py`

| | `log.py` | `observability.py` |
|---|---|---|
| Output | stderr / log file | LangFuse cloud UI |
| Granularity | Line by line | Request tree with nested spans |
| Cost tracking | Manual | Built into generations |
| Required for app to run | No (but useful) | No |
| Phase 0 | Optional | Skip |

Use **both**: logs for dev debugging, LangFuse for production “why did this message fail?”

---

## Self-check

1. App crashes if LangFuse keys missing? → **No** — returns None, no-ops
2. How to disable all tracing? → `observability.enabled: false` in `param.yaml`
3. Where do prompts live by default? → Local files; LangFuse opt-in via `LANGFUSE_PROMPTS=true`
4. Difference between span and generation? → Span = any step; generation = LLM call with tokens/cost
5. When to call `flush()`? → Before process exit so events aren’t lost
6. Which phase to wire this? → **Phase 5** (cache, observability, multi-tenant)

---

## Optional mini-experiment (Phase 5)

After you have LangFuse keys:

```python
from dotenv import load_dotenv
load_dotenv()

from infrastructure.observability import get_langfuse, observe, flush

@observe(name="smoke_test")
def hello():
    return "pong"

client = get_langfuse()
print("Client:", "OK" if client else "disabled (no keys)")

result = hello()
print(result)
flush()
```

Check LangFuse dashboard for a `smoke_test` span.

---

*Last updated: July 2026 — Phase 0 learning notes*
