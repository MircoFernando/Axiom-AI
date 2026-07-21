# Code Explanations — Axiom AI

Structured walkthroughs of the codebase: **what**, **why**, and **how** for each file. Written for learning and PDF export, not as API reference.

## How to use

| When you… | Do this |
|---|---|
| Want the full book | Open [`CodeExplanation.md`](CodeExplanation.md) |
| Want one file only | Open the matching path under `src/…` below |
| Ask the agent to explain a file | Say: *"Explain `src/path/to/file.py` and add it to code-explanations"* |

After each new explanation, the agent should:

1. Add or update `docs/code-explanations/<mirror-path>.md`
2. Append a section to `CodeExplanation.md`
3. Update the index table in this README

## Export to PDF

- **Cursor / VS Code:** Open `CodeExplanation.md` → Markdown PDF extension, or Print → Save as PDF
- **CLI (if you install pandoc):** `pandoc docs/code-explanations/CodeExplanation.md -o docs/code-explanations/CodeExplanation.pdf`

## Index

| Source file | Explanation doc | Status |
|---|---|---|
| `src/infrastructure/llm/embeddings.py` | [embeddings.py.md](src/infrastructure/llm/embeddings.py.md) | Done |
| `src/infrastructure/llm/llm_provider.py` | [llm_provider.py.md](src/infrastructure/llm/llm_provider.py.md) | Done |
| `src/infrastructure/config.py` | — | Pending |
| `src/infrastructure/log.py` | — | Pending |
| `src/infrastructure/models.py` | — | Pending |
| `src/infrastructure/utils.py` | — | Pending |
| `src/infrastructure/observability.py` | [observability.py.md](src/infrastructure/observability.py.md) | Done |

## Conventions

- Docstrings in source may be stale; **`config.py` wins** for model names and constants.
- Paths mirror `src/` so navigation matches the repo.
- Deep-dive FAQ sections live at the bottom of the relevant file doc and in `CodeExplanation.md`.
