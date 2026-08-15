"""Score the RAG layer against the golden question set.

Two halves per question (SPEC-05):
  (a) retrieval hit-rate — expected NCT ids vs the retrieved set,
      per the question's id_match rule. Deterministic, no API.
  (b) citation correctness — expected ids in cited_nct_ids plus every
      expected phrase in the answer (refusal questions: the exact
      refusal sentence and no citations). One API call per question.

--retrieval-only runs just (a). Exit non-zero below thresholds
(retrieval >= 0.8; citation >= 0.7 when the API half runs). Prints
ids, pass/fail, and scores — never document text.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from rag.constants import REFUSAL_SENTENCE, TOP_K
from rag.query_llm import answer_question, retrieve

logger = logging.getLogger(__name__)

GOLDEN_PATH = Path(__file__).parent / "golden_questions.yml"
RETRIEVAL_THRESHOLD = 0.8
CITATION_THRESHOLD = 0.7


REQUIRED_KEYS = ("id", "question", "expected_nct_ids", "id_match", "expected_phrases")


def load_questions(path: Path = GOLDEN_PATH) -> list[dict]:
    """Load and validate the golden set — fail BEFORE any paid API call."""
    import yaml

    questions = yaml.safe_load(path.read_text())["questions"]
    for q in questions:
        missing = [k for k in REQUIRED_KEYS if k not in q]
        if missing:
            raise ValueError(f"{q.get('id', '<no id>')}: missing keys {missing}")
        if q["id_match"] not in ("all", "any"):
            raise ValueError(f"{q['id']}: id_match must be 'all' or 'any'")
    return questions


def ids_match(expected: list[str], found: set[str], id_match: str) -> bool:
    """Apply the question's all/any rule; empty expected always matches."""
    if not expected:
        return True
    matcher = all if id_match == "all" else any
    return matcher(nct_id in found for nct_id in expected)


def score_retrieval(question: dict, retrieved_ids: list[str]) -> bool:
    """(a): expected ids vs the retrieved set (doc ids are nct:field).

    Refusal questions are never scored here — run() excludes them from
    the retrieval denominator entirely (review ruling C5).
    """
    retrieved_nct = {doc_id.split(":")[0] for doc_id in retrieved_ids}
    return ids_match(question["expected_nct_ids"], retrieved_nct, question["id_match"])


def aggregate(
    rows: list[tuple[str, bool | None, bool | None]],
) -> tuple[float, float | None]:
    """Scores over scored questions only (None = not scored, excluded)."""
    retrieval = [r for _, r, _ in rows if r is not None]
    retrieval_score = sum(retrieval) / len(retrieval)
    citations = [c for _, _, c in rows if c is not None]
    citation_score = sum(citations) / len(citations) if citations else None
    return retrieval_score, citation_score


def score_citation(question: dict, output: dict) -> bool:
    """(b): citations + phrases; refusal questions demand the exact sentence."""
    if question.get("expect_refusal"):
        return (
            output["answer"].strip() == REFUSAL_SENTENCE
            and output["cited_nct_ids"] == []
        )
    cited = ids_match(
        question["expected_nct_ids"],
        set(output["cited_nct_ids"]),
        question["id_match"],
    )
    answer_lower = output["answer"].lower()
    phrases = all(p.lower() in answer_lower for p in question["expected_phrases"])
    return cited and phrases


def run(retrieval_only: bool) -> int:
    """Run the eval; return the process exit code."""
    questions = load_questions()
    client = None
    if not retrieval_only:
        import anthropic

        client = anthropic.Anthropic()

    rows: list[tuple[str, bool | None, bool | None]] = []
    for question in questions:
        filters = question.get("filters") or {}
        retrieved = retrieve(
            question["question"],
            k=TOP_K,
            status=filters.get("status"),
            phase=filters.get("phase"),
        )
        retrieval_ok: bool | None = None
        if not question.get("expect_refusal"):
            retrieval_ok = score_retrieval(question, [d["id"] for d in retrieved])
        citation_ok: bool | None = None
        if not retrieval_only:
            output = answer_question(question["question"], retrieved, client)
            citation_ok = score_citation(question, output)
        rows.append((question["id"], retrieval_ok, citation_ok))

    def cell(ok: bool | None) -> str:
        return "n/a" if ok is None else ("PASS" if ok else "FAIL")

    print(f"{'question':<34} {'retrieval':<10} citation")
    for qid, retrieval_ok, citation_ok in rows:
        cite = "-" if retrieval_only else cell(citation_ok)
        print(f"{qid:<34} {cell(retrieval_ok):<10} {cite}")

    retrieval_score, citation_score = aggregate(rows)
    scored = sum(1 for _, r, _ in rows if r is not None)
    print(
        f"\nretrieval hit-rate: {retrieval_score:.2f} over {scored} questions"
        f" (threshold {RETRIEVAL_THRESHOLD}; refusal question excluded)"
    )
    failed = retrieval_score < RETRIEVAL_THRESHOLD
    if citation_score is not None:
        print(
            f"citation correctness: {citation_score:.2f} over {len(rows)}"
            f" questions (threshold {CITATION_THRESHOLD})"
        )
        failed = failed or citation_score < CITATION_THRESHOLD
    return 1 if failed else 0


def main() -> None:
    """CLI entry point for `make eval`."""
    logging.basicConfig(level=logging.WARNING)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument(
        "--retrieval-only",
        action="store_true",
        help="run only the deterministic retrieval half (no API calls)",
    )
    eval_args = cli.parse_args()

    if not eval_args.retrieval_only and not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY not set. Load it first, or run "
            "with --retrieval-only.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(run(retrieval_only=eval_args.retrieval_only))


if __name__ == "__main__":
    main()
