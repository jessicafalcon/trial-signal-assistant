"""Single source of truth for every pinned RAG parameter.

Determinism policy: the embedding model is pinned by name + revision so
the same corpus always produces the same vector store, and the Claude
model is a dated snapshot id called at temperature 0. Current-generation
models (Opus 5 / Sonnet 5) reject the temperature parameter entirely, so
the pin stays on the newest dated model that accepts temperature=0
(DECISIONS.md 2026-08-15).
"""

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_MODEL_REVISION = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"

CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
CLAUDE_MAX_TOKENS = 1024

TOP_K = 5

DUCKDB_PATH = "dbt_project/trial_signal.duckdb"
CHROMA_PATH = "data/chroma"
COLLECTION_NAME = "trial_documents"

REFUSAL_SENTENCE = "The retrieved context does not contain this information."
