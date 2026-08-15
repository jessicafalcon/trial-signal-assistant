"""Bridge from the tested Python parser to the dbt source.

Reads a raw JSON partition (or the test fixtures with --fixtures), runs
the existing parser, and writes one Parquet file per ingest_date
partition. dbt reads only this output — parsing rules stay in Python.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import re
import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ingest.fetch_clinical_trials import TrialRecord, parse_page, parse_study

logger = logging.getLogger(__name__)

RAW_ROOT = Path("data/raw")
PARSED_ROOT = Path("data/parsed")
FIXTURES_DIR = Path("tests/fixtures")
# capture date of tests/fixtures/ — pinned so fixture runs are deterministic
FIXTURE_INGEST_DATE = "2026-08-14"

SCHEMA = pa.schema(
    [
        ("nct_id", pa.string()),
        ("brief_title", pa.string()),
        ("overall_status", pa.string()),
        ("phase", pa.string()),
        ("sponsor_name", pa.string()),
        ("conditions", pa.list_(pa.string())),
        ("interventions", pa.list_(pa.string())),
        ("start_date_raw", pa.string()),
        ("start_date", pa.string()),
        ("date_precision", pa.string()),
        ("why_stopped", pa.string()),
        ("has_results", pa.bool_()),
        ("ingest_date", pa.string()),
    ]
)


def latest_raw_partition(raw_root: Path = RAW_ROOT) -> str:
    """Return the newest ingest_date present under raw_root."""
    dates = sorted(
        p.name.removeprefix("ingest_date=")
        for p in raw_root.glob("ingest_date=*")
        if p.is_dir()
    )
    if not dates:
        raise FileNotFoundError(f"no ingest_date=* partitions under {raw_root}")
    return dates[-1]


def load_raw_studies(partition: Path) -> list[dict]:
    """Load every study dict from a raw partition's page files.

    Raises FileNotFoundError on a missing partition or one with no page
    files — a mistyped DATE must fail loudly, not write 0 rows.
    """
    page_files = sorted(partition.glob("page_*.json"))
    if not page_files:
        raise FileNotFoundError(f"no page_*.json under {partition}")
    studies: list[dict] = []
    for page_file in page_files:
        page_studies, _ = parse_page(json.loads(page_file.read_text()))
        studies.extend(page_studies)
    return studies


def load_fixture_studies(fixtures_dir: Path = FIXTURES_DIR) -> list[dict]:
    """Load every study from the fixtures: page envelopes, lists, singles."""
    studies: list[dict] = []
    for fixture in sorted(fixtures_dir.glob("*.json")):
        payload = json.loads(fixture.read_text())
        if isinstance(payload, list):
            studies.extend(payload)
        elif "studies" in payload:
            studies.extend(parse_page(payload)[0])
        else:
            studies.append(payload)
    return studies


def dedupe_by_nct_id(records: list[TrialRecord]) -> list[TrialRecord]:
    """Keep the first record per nct_id (fixtures overlap across files).

    None ids are never deduped — each must survive to fail the staging
    not_null test rather than collapse into one row.
    """
    seen: set[str] = set()
    unique: list[TrialRecord] = []
    for record in records:
        if record.nct_id is not None and record.nct_id in seen:
            logger.info("dropping duplicate nct_id %s", record.nct_id)
            continue
        if record.nct_id is not None:
            seen.add(record.nct_id)
        unique.append(record)
    return unique


def records_to_table(records: list[TrialRecord], ingest_date: str) -> pa.Table:
    """Build an Arrow table with one column per TrialRecord field."""
    columns: dict[str, list] = {
        field.name: [] for field in dataclasses.fields(TrialRecord)
    }
    for record in records:
        for name, value in dataclasses.asdict(record).items():
            columns[name].append(value)
    columns["ingest_date"] = [ingest_date] * len(records)
    return pa.table(columns, schema=SCHEMA)


def write_partition(
    records: list[TrialRecord], ingest_date: str, out_root: Path = PARSED_ROOT
) -> Path:
    """Write trials.parquet, overwriting this ingest_date partition only."""
    partition = out_root / f"ingest_date={ingest_date}"
    # rmtree guard: a malformed date must never resolve outside out_root
    if not partition.resolve().is_relative_to(out_root.resolve()):
        raise ValueError(f"ingest_date {ingest_date!r} escapes {out_root}")
    if partition.exists():
        shutil.rmtree(partition)
    partition.mkdir(parents=True)
    out_file = partition / "trials.parquet"
    pq.write_table(records_to_table(records, ingest_date), out_file)
    logger.info("wrote %d records to %s", len(records), out_file)
    return out_file


def main() -> None:
    """CLI entry point for `make parse`."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--date", help="ingest_date partition; default: latest")
    cli.add_argument(
        "--fixtures",
        action="store_true",
        help="parse tests/fixtures/ instead of data/raw/ (CI mode)",
    )
    cli.add_argument("--out-root", default=str(PARSED_ROOT))
    parse_args = cli.parse_args()
    if parse_args.date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", parse_args.date):
        cli.error(f"--date must be YYYY-MM-DD, got {parse_args.date!r}")
    if parse_args.date and parse_args.fixtures:
        cli.error("--date and --fixtures are mutually exclusive")

    if parse_args.fixtures:
        # fixture files overlap; real partitions must NOT be deduped —
        # a duplicate there is a data problem for the unique test to catch
        records = dedupe_by_nct_id([parse_study(s) for s in load_fixture_studies()])
        ingest_date = FIXTURE_INGEST_DATE
    else:
        ingest_date = parse_args.date or latest_raw_partition()
        studies = load_raw_studies(RAW_ROOT / f"ingest_date={ingest_date}")
        records = [parse_study(s) for s in studies]

    write_partition(records, ingest_date, Path(parse_args.out_root))


if __name__ == "__main__":
    main()
