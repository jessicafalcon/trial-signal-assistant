"""Bridge tests: fixtures in, Parquet partition out. No network."""

import dataclasses
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pytest

import ingest.parse_to_parquet as bridge
from ingest.fetch_clinical_trials import TrialRecord, parse_study
from ingest.parse_to_parquet import (
    FIXTURE_INGEST_DATE,
    SCHEMA,
    dedupe_by_nct_id,
    latest_raw_partition,
    load_fixture_studies,
    load_raw_studies,
    records_to_table,
    write_partition,
)


@pytest.fixture(scope="module")
def fixture_records() -> list[TrialRecord]:
    return dedupe_by_nct_id([parse_study(s) for s in load_fixture_studies()])


def test_fixture_studies_cover_all_files(fixture_records: list[TrialRecord]) -> None:
    # 12 studies across the 5 fixture files; one cross-file duplicate
    # (NCT06361992) leaves 11 after dedupe
    assert len(load_fixture_studies()) == 12
    assert len(fixture_records) == 11


def test_fixture_nct_ids_unique(fixture_records: list[TrialRecord]) -> None:
    nct_ids = [r.nct_id for r in fixture_records]
    assert len(nct_ids) == len(set(nct_ids))


def test_written_parquet_matches_schema(
    tmp_path: Path, fixture_records: list[TrialRecord]
) -> None:
    out_file = write_partition(fixture_records, FIXTURE_INGEST_DATE, tmp_path)
    table = pq.read_table(out_file)
    assert table.schema.equals(SCHEMA)
    assert table.num_rows == len(fixture_records)
    ingest_dates = set(table.column("ingest_date").to_pylist())
    assert ingest_dates == {FIXTURE_INGEST_DATE}


def test_list_fields_round_trip(
    tmp_path: Path, fixture_records: list[TrialRecord]
) -> None:
    out_file = write_partition(fixture_records, FIXTURE_INGEST_DATE, tmp_path)
    conditions = pq.read_table(out_file).column("conditions").to_pylist()
    assert all(isinstance(c, list) for c in conditions)
    assert any(c for c in conditions)  # at least one non-empty list


def test_description_fields_round_trip(
    tmp_path: Path, fixture_records: list[TrialRecord]
) -> None:
    out_file = write_partition(fixture_records, FIXTURE_INGEST_DATE, tmp_path)
    rows = pq.read_table(out_file).to_pylist()
    by_id = {r["nct_id"]: r for r in rows}
    assert by_id["NCT06727552"]["brief_summary"].startswith(
        "The purpose of this study is to assess"
    )
    assert by_id["NCT06727552"]["detailed_description"] is not None
    assert by_id["NCT00098150"]["detailed_description"] is None


def test_rerun_overwrites_own_partition_only(
    tmp_path: Path, fixture_records: list[TrialRecord]
) -> None:
    other = write_partition(fixture_records, "2020-01-01", tmp_path)
    write_partition(fixture_records, FIXTURE_INGEST_DATE, tmp_path)
    write_partition(fixture_records[:2], FIXTURE_INGEST_DATE, tmp_path)
    own = tmp_path / f"ingest_date={FIXTURE_INGEST_DATE}" / "trials.parquet"
    assert pq.read_table(own).num_rows == 2
    assert pq.read_table(other).num_rows == len(fixture_records)


def test_latest_raw_partition_picks_max_date(tmp_path: Path) -> None:
    for d in ["2026-01-02", "2026-01-10", "2025-12-31"]:
        (tmp_path / f"ingest_date={d}").mkdir()
    assert latest_raw_partition(tmp_path) == "2026-01-10"


def test_latest_raw_partition_raises_when_empty(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        latest_raw_partition(tmp_path)


def test_write_partition_rejects_escaping_date(
    tmp_path: Path, fixture_records: list[TrialRecord]
) -> None:
    with pytest.raises(ValueError, match="escapes"):
        write_partition(fixture_records, "../../../evil", tmp_path)


def test_dedupe_keeps_first_occurrence(fixture_records: list[TrialRecord]) -> None:
    doubled = list(fixture_records) + list(fixture_records)
    assert dedupe_by_nct_id(doubled) == list(fixture_records)


def test_dedupe_never_collapses_null_ids(fixture_records: list[TrialRecord]) -> None:
    nulled = [dataclasses.replace(r, nct_id=None) for r in fixture_records[:3]]
    assert dedupe_by_nct_id(nulled) == nulled


def test_load_raw_studies_missing_partition_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="page"):
        load_raw_studies(tmp_path / "ingest_date=1999-01-01")


def test_load_raw_studies_empty_partition_raises(tmp_path: Path) -> None:
    (tmp_path / "ingest_date=1999-01-01").mkdir()
    with pytest.raises(FileNotFoundError, match="page"):
        load_raw_studies(tmp_path / "ingest_date=1999-01-01")


def test_main_rejects_malformed_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["parse_to_parquet", "--date", "2026/08/14"])
    with pytest.raises(SystemExit) as exc:
        bridge.main()
    assert exc.value.code == 2


def test_main_rejects_date_with_fixtures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["parse_to_parquet", "--fixtures", "--date", "2026-08-14"],
    )
    with pytest.raises(SystemExit) as exc:
        bridge.main()
    assert exc.value.code == 2


def test_raw_path_never_dedupes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a duplicated study in raw data must reach dbt's unique test, not be
    # silently repaired by the bridge
    study = json.loads((Path("tests/fixtures") / "fixture_complete.json").read_text())
    raw_root = tmp_path / "raw"
    partition = raw_root / "ingest_date=2020-01-01"
    partition.mkdir(parents=True)
    (partition / "page_01.json").write_text(json.dumps({"studies": [study, study]}))
    monkeypatch.setattr(bridge, "RAW_ROOT", raw_root)
    out_root = tmp_path / "parsed"
    monkeypatch.setattr(
        sys,
        "argv",
        ["parse_to_parquet", "--date", "2020-01-01", "--out-root", str(out_root)],
    )
    bridge.main()
    table = pq.read_table(out_root / "ingest_date=2020-01-01" / "trials.parquet")
    assert table.num_rows == 2
    nct_ids = table.column("nct_id").to_pylist()
    assert nct_ids[0] == nct_ids[1]


def test_fixtures_mode_never_touches_real_partitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # fixtures mode lands in its own root — a real partition with the
    # same ingest_date must survive byte-identical
    real_root = tmp_path / "parsed"
    fixtures_root = tmp_path / "parsed_fixtures"
    sentinel = real_root / f"ingest_date={FIXTURE_INGEST_DATE}" / "trials.parquet"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_bytes(b"real partition, do not touch")
    monkeypatch.setattr(bridge, "PARSED_ROOT", real_root)
    monkeypatch.setattr(bridge, "FIXTURES_PARSED_ROOT", fixtures_root)
    monkeypatch.setattr(sys, "argv", ["parse_to_parquet", "--fixtures"])
    bridge.main()
    assert sentinel.read_bytes() == b"real partition, do not touch"
    out = fixtures_root / f"ingest_date={FIXTURE_INGEST_DATE}" / "trials.parquet"
    assert pq.read_table(out).num_rows == 11


def test_records_to_table_empty_lists_and_odd_date() -> None:
    # parser contract: unrecognized date keeps raw, precision None; empty
    # arrays stay [] — both must survive the bridge unchanged
    record = TrialRecord(
        nct_id="NCT00000001",
        brief_title=None,
        overall_status="COMPLETED",
        phase=None,
        sponsor_name=None,
        conditions=[],
        interventions=[],
        start_date_raw="Q3 2024",
        start_date=None,
        date_precision=None,
        why_stopped=None,
        brief_summary=None,
        detailed_description=None,
        has_results=False,
    )
    row = records_to_table([record], "2020-01-01").to_pylist()[0]
    assert row["conditions"] == []
    assert row["interventions"] == []
    assert row["start_date_raw"] == "Q3 2024"
    assert row["start_date"] is None
    assert row["date_precision"] is None


def test_fixture_partition_bytes_deterministic(
    tmp_path: Path, fixture_records: list[TrialRecord]
) -> None:
    a = write_partition(fixture_records, FIXTURE_INGEST_DATE, tmp_path / "a")
    b = write_partition(fixture_records, FIXTURE_INGEST_DATE, tmp_path / "b")
    assert a.read_bytes() == b.read_bytes()
