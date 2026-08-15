"""Gap tests from the phase-5 review round (owner ruling) — CI-safe.

build() runs against fake chromadb / sentence_transformers modules
injected into sys.modules (its imports are function-local, so the fakes
are picked up without the real packages installed). No network, no
model downloads, no API.
"""

import sys
import types
from types import SimpleNamespace

import duckdb
import pytest

import rag.embed_and_store as embed
from ingest.fetch_clinical_trials import parse_study
from rag import query_llm
from rag.constants import COLLECTION_NAME


class FakeCollection:
    def __init__(self) -> None:
        self.store: dict[str, tuple] = {}

    def get(self, include=None):
        ids = list(self.store)
        return {"ids": ids, "metadatas": [self.store[i][2] for i in ids]}

    def upsert(self, ids, embeddings, documents, metadatas):
        for id_, emb, doc, meta in zip(
            ids, embeddings, documents, metadatas, strict=True
        ):
            self.store[id_] = (emb, doc, meta)

    def delete(self, ids):
        for id_ in ids:
            self.store.pop(id_, None)

    def count(self) -> int:
        return len(self.store)


class FakeChromaModule(types.ModuleType):
    """Module-shaped fake; collections persist across PersistentClient calls."""

    def __init__(self) -> None:
        super().__init__("chromadb")
        self.collections: dict[str, FakeCollection] = {}
        outer = self

        class PersistentClient:
            def __init__(self, path=None) -> None:
                self._collections = outer.collections

            def get_or_create_collection(self, name, metadata=None):
                return self._collections.setdefault(name, FakeCollection())

            def list_collections(self):
                return [SimpleNamespace(name=n) for n in self._collections]

            def delete_collection(self, name):
                del self._collections[name]

        self.PersistentClient = PersistentClient


class FakeSTModule(types.ModuleType):
    """Fake sentence_transformers; records every text it encodes."""

    def __init__(self) -> None:
        super().__init__("sentence_transformers")
        self.encoded: list[str] = []
        outer = self

        class SentenceTransformer:
            def __init__(self, name, revision=None) -> None:
                pass

            def encode(self, texts, batch_size=None, show_progress_bar=None):
                outer.encoded.extend(texts)
                return SimpleNamespace(tolist=lambda: [[0.0, 1.0] for _ in texts])

        self.SentenceTransformer = SentenceTransformer


def _row(nct_id: str, doc_field: str, text: str, content_hash: str) -> dict:
    return {
        "nct_id": nct_id,
        "doc_field": doc_field,
        "doc_text": text,
        "overall_status": "TERMINATED",
        "phase": "",
        "sponsor_name": "Acme",
        "has_results": False,
        "conditions_flat": "Atopic Dermatitis",
        "content_hash": content_hash,
        "ingest_date": "2026-08-14",
    }


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeChromaModule, FakeSTModule]:
    chroma, st = FakeChromaModule(), FakeSTModule()
    monkeypatch.setitem(sys.modules, "chromadb", chroma)
    monkeypatch.setitem(sys.modules, "sentence_transformers", st)
    return chroma, st


class TestBuildIncremental:
    # gap test 1: build() end-to-end — n, then 0, then only the change
    def test_full_then_noop_then_single_change(
        self, fakes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chroma, st = fakes
        rows = [
            _row("NCT00000001", "brief_summary", "text a", "aaa"),
            _row("NCT00000001", "why_stopped", "text b", "bbb"),
        ]
        monkeypatch.setattr(embed, "read_documents", lambda: rows)
        assert embed.build() == 2
        assert embed.build() == 0  # unchanged mart: embeds 0, deletes 0
        assert chroma.collections[COLLECTION_NAME].count() == 2

        rows[1] = _row("NCT00000001", "why_stopped", "text b2", "b2")
        assert embed.build() == 1
        assert st.encoded == ["text a", "text b", "text b2"]  # no re-encode
        stored = chroma.collections[COLLECTION_NAME].store
        assert stored["NCT00000001:why_stopped"][2]["content_hash"] == "b2"

    # gap test 4: a document that leaves the mart leaves the store
    def test_stale_document_is_deleted(
        self, fakes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chroma, _ = fakes
        rows = [
            _row("NCT00000001", "brief_summary", "text a", "aaa"),
            _row("NCT00000001", "why_stopped", "text b", "bbb"),
        ]
        monkeypatch.setattr(embed, "read_documents", lambda: rows)
        embed.build()
        monkeypatch.setattr(embed, "read_documents", lambda: rows[:1])
        assert embed.build() == 0  # nothing re-embedded...
        collection = chroma.collections[COLLECTION_NAME]
        assert collection.count() == 1  # ...but the stale doc is gone
        assert "NCT00000001:why_stopped" not in collection.store

    def test_full_rebuild_drops_and_reembeds(
        self, fakes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, st = fakes
        rows = [_row("NCT00000001", "brief_summary", "text a", "aaa")]
        monkeypatch.setattr(embed, "read_documents", lambda: rows)
        embed.build()
        assert embed.build(full=True) == 1  # re-embeds despite matching hash
        assert st.encoded == ["text a", "text a"]


class TestCliExitCodes:
    # gap test 2: exit code 1 paths (only exit 2 was covered before)
    def test_retrieval_failure_exits_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
        monkeypatch.setattr(sys, "argv", ["query_llm", "why?"])

        def boom(*args, **kwargs):
            raise RuntimeError("collection not found")

        monkeypatch.setattr(query_llm, "retrieve", boom)
        with pytest.raises(SystemExit) as exc:
            query_llm.main()
        assert exc.value.code == 1

    def test_empty_retrieval_exits_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
        monkeypatch.setattr(sys, "argv", ["query_llm", "why?"])
        monkeypatch.setattr(query_llm, "retrieve", lambda *a, **k: [])
        with pytest.raises(SystemExit) as exc:
            query_llm.main()
        assert exc.value.code == 1


class TestMartTextRules:
    # gap test 3: the mart's blank-exclusion + trim-before-hash rules,
    # run as the exact expressions over an in-memory duckdb relation
    def test_blank_rows_excluded_and_text_trimmed(self) -> None:
        rows = duckdb.sql(
            "select trim(doc_text) as doc_text, md5(trim(doc_text)) as h"
            " from (values (''), ('   '), (cast(null as varchar)), ('  D  '))"
            " t(doc_text)"
            " where trim(coalesce(doc_text, '')) != ''"
        ).fetchall()
        assert rows == [("D", duckdb.sql("select md5('D')").fetchone()[0])]


class TestParserDescriptionEdges:
    # gap test 5: descriptionModule explicitly null; briefSummary ""
    def test_null_description_module(self) -> None:
        record = parse_study({"protocolSection": {"descriptionModule": None}})
        assert record.brief_summary is None
        assert record.detailed_description is None

    def test_empty_string_brief_summary_survives_parser(self) -> None:
        # the parser stays verbatim ("" not coerced); the mart's blank
        # filter is what keeps it out of the RAG corpus
        record = parse_study(
            {"protocolSection": {"descriptionModule": {"briefSummary": ""}}}
        )
        assert record.brief_summary == ""


class TestGoldenSetValidation:
    # gap test 6: malformed questions fail at load, before any API call
    def test_missing_key_raises_value_error(self, tmp_path) -> None:
        from rag.eval.run_eval import load_questions

        bad = tmp_path / "golden.yml"
        bad.write_text(
            "questions:\n"
            "  - id: q_bad\n"
            "    question: 'incomplete'\n"
            "    expected_nct_ids: []\n"
            "    id_match: all\n"  # expected_phrases missing
        )
        with pytest.raises(ValueError, match="q_bad.*expected_phrases"):
            load_questions(bad)

    def test_bad_id_match_raises_value_error(self, tmp_path) -> None:
        from rag.eval.run_eval import load_questions

        bad = tmp_path / "golden.yml"
        bad.write_text(
            "questions:\n"
            "  - id: q_bad\n"
            "    question: 'x'\n"
            "    expected_nct_ids: []\n"
            "    expected_phrases: []\n"
            "    id_match: some\n"
        )
        with pytest.raises(ValueError, match="all.*any"):
            load_questions(bad)
