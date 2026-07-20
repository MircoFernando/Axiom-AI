# `src/infrastructure/llm/llm_provider.py`

> **Layer:** Infrastructure / LLM  
> **Depends on:** `infrastructure.config`  
> **Used by (later):** Router, agents, RAG synthesis, memory distillation  
> **Phase relevance:** Phase 0 smoke test (LLM check), Phase 2 (`get_chat_llm`), Phase 4 (`get_router_llm`)

---

## What this file is for

Builds **chat LLMs** (text in → text out). Pairs with `embeddings.py` (text in → vector out).

Your system needs different models for different jobs:

| Job | Needs | Bad choice |
|---|---|---|
| Route intent | Fast, reliable JSON | Slow expensive flagship model |
| Extract fields from slip | Tiny structured output | Gemini for a 20-token JSON blob |
| Answer student with RAG context | Quality, long context, tutor tone | 8B model that hallucinates |
| Reply "Hi sir!" | Fast, conversational | Full RAG pipeline |

This file exposes **four ready-made clients**, each tuned for one role.

---

## Docstring vs `config.py` — source of truth

File header and function docstrings may describe an **older** setup. **`config.py` wins:**

| Getter | Actual model | Provider |
|---|---|---|
| `get_router_llm()` | `llama-3.3-70b-versatile` | Groq |
| `get_fast_chat_llm()` | `llama-3.3-70b-versatile` | Groq |
| `get_extractor_llm()` | `llama-3.1-8b-instant` | Groq |
| `get_chat_llm()` | `google/gemini-2.5-flash` | OpenRouter |

Router and fast chat **share the same 70B Groq model** on purpose.

---

## Imports

**Why `ChatOpenAI` for everything?**

OpenRouter and Groq expose an **OpenAI-compatible HTTP API** — same request shape (`/v1/chat/completions`), different base URL and key.

```
Your code → ChatOpenAI → HTTP POST
              ↓
    OpenRouter  OR  Groq  OR  OpenAI
              ↓
         Actual model (Gemini, Llama, etc.)
```

---

## The core: `_build_llm()` (private factory)

```python
def _build_llm(model, provider, temperature=0, streaming=False, max_tokens=None, **kwargs) -> ChatOpenAI
```

**WHAT:** Internal builder. Public functions never construct `ChatOpenAI` directly.

**WHY:** DRY — provider wiring in one place. Add a provider → one `elif`, not four copy-pastes.

**HOW:**

1. Build kwargs: model, temperature, streaming, max_tokens
2. Branch on `provider`:
   - `openrouter` → `OPENROUTER_BASE_URL` + `get_api_key("openrouter")`
   - `groq` → `GROQ_BASE_URL` + `get_api_key("groq")`
   - `openai` → `get_api_key("openai")`
3. Return `ChatOpenAI(**llm_kwargs)` — configured, not called yet

Each branch passes an **explicit** provider to `get_api_key()`, not global `PROVIDER` from YAML. Router uses Groq even when `param.yaml` says `default: openrouter`.

### Parameters

| Param | Default | Meaning |
|---|---|---|
| `temperature` | `0` | Randomness. 0 = deterministic (routing/JSON) |
| `streaming` | `False` | Token-by-token vs full response |
| `max_tokens` | `None` | Cap output length |
| `**kwargs` | — | Pass through (e.g. `timeout=30`) |

---

## The four public getters

### 1. `get_router_llm()` — intent classification

- **Model:** Groq `llama-3.3-70b-versatile`, `temperature=0`
- **WHEN (Phase 4):** After guardrail + cache miss
- **Output:** Structured route, e.g. `{"route": "academic"}`

| Message | Expected route |
|---|---|
| "explain momentum" | `academic` |
| "send last week's physics paper" | `resource` |
| "I want to join Chemistry 2026" | `admissions` |
| "class fee paid" + image | `finance` |

### 2. `get_fast_chat_llm()` — direct / concierge

- **Model:** Same 70B Groq, `temperature=0.3`
- **WHEN:** Router picks `"direct"` — greetings, thanks, small talk
- **WHY separate from chat:** Skip RAG for "Hi sir"

### 3. `get_extractor_llm()` — structured extraction

- **Model:** Groq `llama-3.1-8b-instant`, `temperature=0`
- **WHEN:** Bank slip fields, memory distillation, escalation tags
- **WHY 8B:** Tiny JSON, speed, runs often

### 4. `get_chat_llm()` — flagship synthesis

- **Model:** `google/gemini-2.5-flash` via OpenRouter, `temperature=0`
- **WHEN (Phase 2):** User-facing RAG answers, tutor tone, long context
- **WHY Gemini:** Quality, context window, multimodal later (slips, MCQ photos)

---

## Visual: where each LLM fires

```
Student message
      ↓
Guardrail
      ↓
Semantic cache (embeddings — no LLM)
      ↓ miss
get_router_llm().invoke(...)     ← Groq 70B, temp=0
      ↓
   ┌──┴──┬──────────┬─────────┐
   ↓     ↓          ↓         ↓
direct  academic  resource  finance
   ↓     ↓          ↓         ↓
fast    RAG + get_chat_llm()   tools + get_chat_llm()
chat    (Gemini)
(Groq 70B)
```

**Rule:** Groq for fast internal decisions; Gemini for answers the student reads.

---

## What `.invoke()` does (conceptually)

```python
from langchain_core.messages import HumanMessage

llm = get_chat_llm()
response = llm.invoke([HumanMessage(content="Explain velocity")])
print(response.content)
```

1. LangChain builds OpenAI-format messages JSON
2. HTTP POST to provider base URL
3. Response → `AIMessage` with `.content`

---

## Keys required in `.env`

| Getter | Env var |
|---|---|
| `get_router_llm()` | `GROQ_API_KEY` |
| `get_fast_chat_llm()` | `GROQ_API_KEY` |
| `get_extractor_llm()` | `GROQ_API_KEY` |
| `get_chat_llm()` | `OPENROUTER_API_KEY` |

---

## What this file does NOT do

- Route messages (`agents/router.py` — Phase 4)
- Build prompts (`agents/prompts/` — Phase 2)
- Stream to WhatsApp (API/worker — Phase 1)
- Trace calls (`observability.py` — Phase 5)

---

## Self-check

1. Why is `_build_llm` private? → Hide generic builder; expose intent-specific getters
2. Why shared 70B for router + fast chat? → Same provider/latency; different prompts and temperature
3. Phase 2 Academic RAG synthesis? → `get_chat_llm()`
4. "Admissions or finance?" → `get_router_llm()`
5. Why `ChatOpenAI` for Groq? → Groq mimics OpenAI’s API shape

See **Deep dives** in `CodeExplanation.md` (section: LLM Provider FAQ) for full explanations.

---

## Optional mini-experiment

```python
from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import HumanMessage
from infrastructure.llm.llm_provider import get_fast_chat_llm, get_chat_llm

fast = get_fast_chat_llm()
print(fast.invoke([HumanMessage(content="Reply with exactly: pong")]).content)

chat = get_chat_llm()
print(chat.invoke([HumanMessage(content="Reply with exactly: pong")]).content)
```

---

*Last updated: July 2026 — Phase 0 learning notes*
