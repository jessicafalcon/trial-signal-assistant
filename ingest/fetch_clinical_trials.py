"""Fetch and parse Atopic Dermatitis trials from ClinicalTrials.gov API v2.

Fetching (network) and parsing (pure functions) are kept separate: the dbt
seed layer and the RAG embedder import the parsers without touching the
network.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
QUERY_PARAMS: dict[str, str] = {
    "query.cond": '"Atopic Dermatitis"',
    "pageSize": "1000",
}
REQUEST_TIMEOUT_S = 60

_ISO_DAY = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_ISO_MONTH = re.compile(r"(\d{4})-(\d{2})")


@dataclass(frozen=True)
class TrialRecord:
    nct_id: str | None
    brief_title: str | None
    overall_status: str | None
    phase: str | None
    sponsor_name: str | None
    conditions: list[str]
    interventions: list[str]
    start_date_raw: str | None
    start_date: str | None
    date_precision: str | None  # "day" | "month" | None
    why_stopped: str | None
    has_results: bool


def parse_date(raw: str | None) -> tuple[str | None, str | None]:
    """Return (iso_date, precision) for "YYYY-MM-DD"/"YYYY-MM"; (None, None) otherwise."""
    if raw is None:
        return None, None
    day = _ISO_DAY.fullmatch(raw)
    month = _ISO_MONTH.fullmatch(raw)
    try:
        if day:
            date(int(day[1]), int(day[2]), int(day[3]))  # validates, e.g. no month 13
            return raw, "day"
        if month:
            date(int(month[1]), int(month[2]), 1)
            return f"{raw}-01", "month"
    except ValueError:
        pass
    logger.warning("unrecognized date format, keeping raw only: %r", raw)
    return None, None


def parse_study(study: dict) -> TrialRecord:
    """Parse one raw API study dict into a TrialRecord.

    Pure (dict in, record out). Every module, struct, and array may be
    absent, null, or partial in real payloads — missing anything degrades
    to None / [] rather than raising.
    """
    protocol = study.get("protocolSection") or {}
    identification = protocol.get("identificationModule") or {}
    status = protocol.get("statusModule") or {}
    design = protocol.get("designModule") or {}
    sponsors = protocol.get("sponsorCollaboratorsModule") or {}
    conditions_module = protocol.get("conditionsModule") or {}
    arms = protocol.get("armsInterventionsModule") or {}

    start_struct = status.get("startDateStruct") or {}
    start_date_raw = start_struct.get("date")
    start_date, date_precision = parse_date(start_date_raw)

    phases = design.get("phases") or []
    interventions = arms.get("interventions") or []

    return TrialRecord(
        nct_id=identification.get("nctId"),
        brief_title=identification.get("briefTitle"),
        overall_status=status.get("overallStatus"),
        phase="/".join(phases) if phases else None,
        sponsor_name=(sponsors.get("leadSponsor") or {}).get("name"),
        conditions=list(conditions_module.get("conditions") or []),
        interventions=[i["name"] for i in interventions if i.get("name")],
        start_date_raw=start_date_raw,
        start_date=start_date,
        date_precision=date_precision,
        why_stopped=status.get("whyStopped"),
        has_results=bool(study.get("hasResults")),
    )


def parse_page(payload: dict) -> tuple[list[dict], str | None]:
    """Split a raw response envelope into (studies, next_page_token)."""
    return list(payload.get("studies") or []), payload.get("nextPageToken")


def fetch_pages(max_pages: int = 10) -> list[str]:
    """Fetch raw response bodies from the live API, following nextPageToken."""
    pages: list[str] = []
    params = dict(QUERY_PARAMS)
    for _ in range(max_pages):
        response = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT_S)
        response.raise_for_status()
        pages.append(response.text)
        _, next_token = parse_page(response.json())
        if not next_token:
            break
        params["pageToken"] = next_token
    return pages


def fetch_studies(max_pages: int = 10) -> list[dict]:
    """Fetch raw study dicts from the live API, following nextPageToken."""
    studies: list[dict] = []
    for page in fetch_pages(max_pages):
        page_studies, _ = parse_page(json.loads(page))
        studies.extend(page_studies)
    return studies


def ingest_raw(out_root: str = "data/raw", max_pages: int = 10) -> Path:
    """Land raw pages verbatim under out_root/ingest_date=<UTC today>/.

    Idempotent: a re-run overwrites its own date partition only.
    """
    ingest_date = datetime.now(tz=UTC).date().isoformat()
    partition = Path(out_root) / f"ingest_date={ingest_date}"
    if partition.exists():
        shutil.rmtree(partition)
    partition.mkdir(parents=True)
    total = 0
    for page_num, page in enumerate(fetch_pages(max_pages), start=1):
        (partition / f"page_{page_num:02d}.json").write_text(page)
        total += len(parse_page(json.loads(page))[0])
    logger.info("landed %d studies in %s", total, partition)
    return partition


def main() -> None:
    """CLI entry point for `make ingest`."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--out-root", default="data/raw")
    cli.add_argument("--max-pages", type=int, default=10)
    ingest_args = cli.parse_args()
    ingest_raw(out_root=ingest_args.out_root, max_pages=ingest_args.max_pages)


if __name__ == "__main__":
    main()
