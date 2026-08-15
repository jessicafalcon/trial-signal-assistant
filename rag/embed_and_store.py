"""Build the Chroma vector store from mart_trial_documents.

Incremental by content_hash (the F8 change key): a document is
re-embedded only when its stored hash no longer matches the mart's, and
ids that left the mart are deleted from the store. A re-run over an
unchanged mart embeds 0 documents and deletes 0. --full drops the
collection and rebuilds from scratch.

Logs counts only — never document text. Heavy imports (duckdb, chroma,
sentence-transformers) are deferred into functions so importing this
module needs nothing beyond the standard library (CI runs unit tests
against the pure helpers with fakes).
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

from rag.constants import (
    CHROMA_PATH,
    COLLECTION_NAME,
    DUCKDB_PATH,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_REVISION,
)

logger = logging.getLogger(__name__)

# the mart's scalar columns that become Chroma metadata (all non-null by
# schema contract; Chroma rejects null metadata values)
METADATA_COLUMNS = (
    "nct_id",
    "doc_field",
    "overall_status",
    "phase",
    "sponsor_name",
    "has_results",
    "conditions_flat",
    "content_hash",
    "ingest_date",
)


def doc_id(row: dict[str, Any]) -> str:
    """Stable Chroma id: one document per (nct_id, doc_field)."""
    return f"{row['nct_id']}:{row['doc_field']}"


def metadata_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Scalar metadata for one document; ingest_date coerced to str."""
    meta = {col: row[col] for col in METADATA_COLUMNS}
    meta["ingest_date"] = str(meta["ingest_date"])
    return meta


def select_changed(
    rows: list[dict[str, Any]], stored_hashes: dict[str, str]
) -> list[dict[str, Any]]:
    """Rows whose content_hash is missing from or differs in the store."""
    return [r for r in rows if stored_hashes.get(doc_id(r)) != r["content_hash"]]


def read_documents(db_path: str = DUCKDB_PATH) -> list[dict[str, Any]]:
    """Read mart_trial_documents rows as dicts (read-only connection)."""
    import duckdb

    con = duckdb.connect(db_path, read_only=True)
    try:
        # explicit column list: the mart contract this module depends on
        cursor = con.sql(
            "select nct_id, doc_field, doc_text, overall_status, phase,"
            " sponsor_name, has_results, conditions_flat, content_hash,"
            " ingest_date"
            " from main.mart_trial_documents order by nct_id, doc_field"
        )
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, values, strict=True)) for values in cursor.fetchall()]
    finally:
        con.close()


def build(full: bool = False) -> int:
    """Embed changed documents into Chroma; return the embedded count."""
    import chromadb
    from sentence_transformers import SentenceTransformer

    rows = read_documents()
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    # existence check instead of a broad except: --full on a fresh store
    # is normal; any other delete failure must surface loudly
    if full and COLLECTION_NAME in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION_NAME)
    collection = client.get_or_create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )

    existing = collection.get(include=["metadatas"])
    stored_hashes = {
        id_: meta.get("content_hash", "")
        for id_, meta in zip(existing["ids"], existing["metadatas"], strict=True)
    }
    # stale ids (document left the mart) are deleted so they can no
    # longer be retrieved or cited (phase-5 review ruling C2/F1)
    stale = sorted(set(stored_hashes) - {doc_id(r) for r in rows})
    if stale:
        collection.delete(ids=stale)
    changed = select_changed(rows, stored_hashes)
    logger.info(
        "mart documents: %d total, %d changed, %d unchanged, %d stale",
        len(rows),
        len(changed),
        len(rows) - len(changed),
        len(stale),
    )

    if changed:
        model = SentenceTransformer(
            EMBEDDING_MODEL_NAME, revision=EMBEDDING_MODEL_REVISION
        )
        embeddings = model.encode(
            [r["doc_text"] for r in changed],
            batch_size=64,
            show_progress_bar=False,
        )
        collection.upsert(
            ids=[doc_id(r) for r in changed],
            embeddings=embeddings.tolist(),
            documents=[r["doc_text"] for r in changed],
            metadatas=[metadata_from_row(r) for r in changed],
        )

    logger.info(
        "embedded %d documents, deleted %d stale (store now holds %d)",
        len(changed),
        len(stale),
        collection.count(),
    )
    return len(changed)


def main() -> None:
    """CLI entry point for `make rag-build`."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument(
        "--full",
        action="store_true",
        help="drop the collection and re-embed everything",
    )
    build_args = cli.parse_args()
    build(full=build_args.full)


if __name__ == "__main__":
    main()
