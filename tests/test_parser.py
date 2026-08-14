import json
import logging
import pathlib

import pytest

from ingest.fetch_clinical_trials import parse_date, parse_page, parse_study

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(scope="session")
def complete() -> dict:
    return load("fixture_complete.json")


@pytest.fixture(scope="session")
def dates_mixed() -> list[dict]:
    return load("fixture_dates_mixed.json")


class TestCompleteRecord:
    def test_exact_values(self, complete: dict) -> None:
        record = parse_study(complete)
        assert record.nct_id == "NCT06727552"
        assert (
            record.brief_title
            == "A Study of Barzolvolimab in Patients With Atopic Dermatitis"
        )
        assert record.overall_status == "ACTIVE_NOT_RECRUITING"
        assert record.phase == "PHASE2"
        assert record.sponsor_name == "Celldex Therapeutics"
        assert record.conditions == ["Atopic Dermatitis"]
        assert record.interventions == ["Barzolvolimab", "Matching placebo"]
        assert record.start_date_raw == "2024-12-18"
        assert record.start_date == "2024-12-18"
        assert record.date_precision == "day"
        assert record.why_stopped is None
        assert record.has_results is False


class TestSparseRecord:
    def test_arrays_default_to_empty(self) -> None:
        record = parse_study(load("fixture_sparse.json"))
        assert record.nct_id == "NCT00098150"
        assert record.conditions == ["Atopic Dermatitis"]
        assert record.interventions == []
        assert record.phase is None

    def test_empty_study_does_not_raise(self) -> None:
        record = parse_study({})
        assert record.nct_id is None
        assert record.conditions == []
        assert record.interventions == []
        assert record.start_date is None


class TestDates:
    def test_iso_day(self, dates_mixed: list[dict]) -> None:
        record = parse_study(dates_mixed[0])  # NCT06361992
        assert record.nct_id == "NCT06361992"
        assert record.start_date_raw == "2022-03-15"
        assert record.start_date == "2022-03-15"
        assert record.date_precision == "day"

    def test_iso_month_resolves_to_first_of_month(
        self, dates_mixed: list[dict]
    ) -> None:
        record = parse_study(dates_mixed[1])  # NCT01138761
        assert record.nct_id == "NCT01138761"
        assert record.start_date_raw == "2010-06"
        assert record.start_date == "2010-06-01"
        assert record.date_precision == "month"

    def test_partial_struct_without_type_key(self, dates_mixed: list[dict]) -> None:
        # NCT01138761: startDateStruct is {"date": "2010-06"} with no "type" key
        struct = dates_mixed[1]["protocolSection"]["statusModule"]["startDateStruct"]
        assert "type" not in struct
        record = parse_study(dates_mixed[1])
        assert record.start_date == "2010-06-01"
        assert record.date_precision == "month"

    def test_absent_date_struct(self, dates_mixed: list[dict]) -> None:
        record = parse_study(dates_mixed[3])  # NCT01179529, no startDateStruct
        assert record.nct_id == "NCT01179529"
        assert record.start_date_raw is None
        assert record.start_date is None
        assert record.date_precision is None

    def test_unknown_format_keeps_raw_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        study = {
            "protocolSection": {
                "statusModule": {"startDateStruct": {"date": "January 2024"}}
            }
        }
        with caplog.at_level(logging.WARNING):
            record = parse_study(study)
        assert record.start_date_raw == "January 2024"
        assert record.start_date is None
        assert record.date_precision is None
        assert any("January 2024" in message for message in caplog.messages)

    def test_parse_date_direct(self) -> None:
        assert parse_date("2024-01-15") == ("2024-01-15", "day")
        assert parse_date("2024-01") == ("2024-01-01", "month")
        assert parse_date(None) == (None, None)
        assert parse_date("not a date") == (None, None)


class TestWhyStopped:
    def test_present_on_withdrawn(self) -> None:
        record = parse_study(load("fixture_withdrawn.json"))
        assert record.nct_id == "NCT04965233"
        assert record.overall_status == "WITHDRAWN"
        assert record.why_stopped == (
            "Due to protocol changes, and the observational design of this "
            "study (not an ACT), the study registry is withdrawn from "
            "clinicaltrials.gov."
        )

    def test_absent_elsewhere(self, complete: dict) -> None:
        assert parse_study(complete).why_stopped is None


class TestPagination:
    def test_envelope_yields_studies_and_token(self) -> None:
        studies, next_token = parse_page(load("fixture_page.json"))
        assert len(studies) == 5
        assert next_token == "ZVt07cGHkvI2wRk2CJf6_LLqy5DbMtMod7KrgP4blD-Wv_E"

    def test_envelope_without_token(self) -> None:
        studies, next_token = parse_page({"studies": []})
        assert studies == []
        assert next_token is None


class TestRoundTrip:
    def test_every_page_study_parses(self) -> None:
        studies, _ = parse_page(load("fixture_page.json"))
        for study in studies:
            record = parse_study(study)
            assert record.nct_id and record.nct_id.startswith("NCT")
            assert isinstance(record.conditions, list)
            assert isinstance(record.interventions, list)

    def test_every_dates_mixed_study_parses(self, dates_mixed: list[dict]) -> None:
        assert len([parse_study(s) for s in dates_mixed]) == 4
