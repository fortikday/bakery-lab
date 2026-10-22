"""Check import review/commit boundaries and honest week-to-week reporting.

These tests use only temporary SQLite files. They never import example records
into the user's database or interpret a change in recorded totals as an impact
measurement.
"""

from concurrent.futures import ThreadPoolExecutor
import csv
from decimal import Decimal
import io
from pathlib import Path
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from waste_log import ConflictError, LogStore


CSV_FIELDS = [
    "id", "revision", "record_date", "store", "product", "kind",
    "opening_stock", "produced", "sold", "discounted_sold", "donated",
    "discarded", "closing_stock", "sold_out_at", "closing_time", "waste_kg",
    "reason", "unit_cost", "currency", "notes",
]


def finished(**changes):
    payload = {
        "record_date": "2026-10-19", "store": "High Street", "product": "Croissant",
        "kind": "finished_product", "opening_stock": 0, "produced": 10,
        "sold": 7, "discounted_sold": 2, "donated": 1, "discarded": 2,
        "closing_stock": 0, "sold_out_at": "", "closing_time": "",
        "reason": "overproduction", "unit_cost": "0.25", "currency": "GBP", "notes": "",
    }
    payload.update(changes)
    return payload


def production(**changes):
    payload = {
        "record_date": "2026-10-19", "store": "High Street", "product": "Excess dough",
        "kind": "production_waste", "waste_kg": "0.500", "reason": "preparation_error",
        "unit_cost": "4", "currency": "GBP", "notes": "",
    }
    payload.update(changes)
    return payload


def csv_text(rows, fields=CSV_FIELDS):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def invalid_preview(store, text):
    result = store.preview_import(text)
    assert result["valid"] is False
    assert result["errors"]
    assert result["preview_token"] is None
    return result


@pytest.fixture
def store(tmp_path):
    return LogStore(tmp_path / "imports.sqlite3")


def test_preview_validates_mixed_units_without_saving_any_records(store):
    text = csv_text([finished(), production(record_date="2026-10-12")])
    preview = store.preview_import(text)
    assert preview["valid"] is True
    assert preview["row_count"] == preview["ready_count"] == 2
    assert preview["errors"] == []
    assert [row["status"] for row in preview["rows"]] == ["ready", "ready"]
    assert preview["date_start"] == "2026-10-12"
    assert preview["date_end"] == "2026-10-19"
    assert isinstance(preview["preview_token"], str) and preview["preview_token"]
    assert store.list_entries(include_archived=True) == []


def test_commit_saves_all_reviewed_records_and_cannot_be_replayed(store):
    text = csv_text([finished(), production()])
    preview = store.preview_import(text)
    result = store.commit_import(text, preview["preview_token"])
    assert result["imported_count"] == 2
    assert len({entry["id"] for entry in result["entries"]}) == 2
    assert all(entry["revision"] == 1 for entry in result["entries"])
    report = store.weekly_report("2026-10-19")
    assert report["totals"]["finished_discarded"] == 2
    assert Decimal(report["totals"]["production_waste_kg"]) == Decimal("0.500")
    assert report["costs"] == [{"currency": "GBP", "estimated_cost": "2.50"}]
    with pytest.raises(ConflictError):
        store.commit_import(text, preview["preview_token"])
    assert len(store.list_entries()) == 2


def test_changing_the_file_after_preview_cannot_import_unreviewed_data(store):
    original = csv_text([finished()])
    token = store.preview_import(original)["preview_token"]
    changed = csv_text([finished(product="Changed product")])
    with pytest.raises(ConflictError):
        store.commit_import(changed, token)
    assert store.list_entries() == []


def test_one_invalid_row_prevents_the_whole_batch_from_being_saved(store):
    text = csv_text([finished(), production(waste_kg="-0.5")])
    preview = invalid_preview(store, text)
    assert preview["row_count"] == 2
    assert any(error["row"] == 3 for error in preview["errors"])
    with pytest.raises(ValueError):
        store.commit_import(text, preview["preview_token"])
    assert store.list_entries(include_archived=True) == []


def test_duplicate_keys_inside_the_csv_are_case_and_whitespace_insensitive(store):
    preview = invalid_preview(store, csv_text([
        finished(), finished(store="  HIGH STREET ", product="croissant"),
    ]))
    assert preview["row_count"] == 2
    assert store.list_entries() == []


def test_existing_records_are_never_overwritten_or_partially_imported(store):
    existing = store.create(finished(notes="Keep this original record"))
    text = csv_text([
        production(), finished(store="HIGH STREET", product="croissant", notes="Overwrite attempt"),
    ])
    preview = invalid_preview(store, text)
    with pytest.raises(ValueError):
        store.commit_import(text, preview["preview_token"])
    entries = store.list_entries()
    assert len(entries) == 1
    assert entries[0]["id"] == existing["id"]
    assert entries[0]["notes"] == "Keep this original record"
    assert entries[0]["revision"] == existing["revision"]


def test_database_changes_in_another_session_make_a_preview_stale(store):
    text = csv_text([production()])
    token = store.preview_import(text)["preview_token"]
    other_session = LogStore(store.path)
    other_session.create(finished())
    with pytest.raises(ConflictError):
        store.commit_import(text, token)
    assert len(store.list_entries()) == 1
    assert store.list_entries()[0]["kind"] == "finished_product"


@pytest.mark.parametrize("action", ["edit", "archive", "restore"])
def test_preview_snapshot_tracks_revisions_and_archive_changes(store, action):
    existing = store.create(finished())
    if action == "restore":
        existing = store.archive(existing["id"], existing["revision"])
    text = csv_text([production()])
    token = store.preview_import(text)["preview_token"]
    other_session = LogStore(store.path)
    if action == "edit":
        other_session.update(existing["id"], finished(notes="Changed after review", revision=existing["revision"]))
    elif action == "archive":
        other_session.archive(existing["id"], existing["revision"])
    else:
        other_session.restore(existing["id"], existing["revision"])
    with pytest.raises(ConflictError):
        store.commit_import(text, token)
    assert all(entry["kind"] == "finished_product" for entry in store.list_entries(include_archived=True))


def test_two_simultaneous_commits_do_not_accept_the_same_database_snapshot(tmp_path):
    path = tmp_path / "race.sqlite3"
    sessions = [LogStore(path), LogStore(path)]
    texts = [csv_text([finished(product="First import")]), csv_text([finished(product="Second import")])]
    tokens = [session.preview_import(text)["preview_token"] for session, text in zip(sessions, texts)]
    barrier = threading.Barrier(2)

    def commit(index):
        barrier.wait(timeout=5)
        try:
            sessions[index].commit_import(texts[index], tokens[index])
            return "saved"
        except ConflictError:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(commit, range(2)))
    assert sorted(outcomes) == ["saved", "stale"]
    assert len(LogStore(path).list_entries()) == 1


def test_utf8_bom_quoted_commas_and_multiline_notes_are_preserved(store):
    original = finished(store="North, Market", product="Roll, seeded", notes='One tray\nReviewed by "Sam"')
    text = "\ufeff" + csv_text([original])
    preview = store.preview_import(text)
    assert preview["valid"]
    store.commit_import(text, preview["preview_token"])
    saved = store.list_entries()[0]
    assert saved["store"] == original["store"]
    assert saved["product"] == original["product"]
    assert saved["notes"] == original["notes"]


def test_export_metadata_does_not_override_new_record_identity(store):
    row = finished(id="old-exported-id", revision="99")
    text = csv_text([row])
    preview = store.preview_import(text)
    assert preview["valid"]
    saved = store.commit_import(text, preview["preview_token"])["entries"][0]
    assert saved["id"] != "old-exported-id"
    assert saved["revision"] == 1


def test_optional_blank_cost_and_explicit_zero_cost_remain_distinct(store):
    text = csv_text([
        finished(product="Unknown", unit_cost="", currency=""),
        finished(product="Known zero", unit_cost="0", currency="GBP"),
    ])
    preview = store.preview_import(text)
    assert preview["valid"]
    store.commit_import(text, preview["preview_token"])
    by_product = {row["product"]: row for row in store.list_entries()}
    assert by_product["Unknown"]["unit_cost"] is None
    assert Decimal(by_product["Known zero"]["unit_cost"]) == 0
    report = store.weekly_report("2026-10-19")
    assert report["uncosted_waste_entries"] == 1
    assert report["costs"] == [{"currency": "GBP", "estimated_cost": "0.00"}]


def test_minimal_finished_columns_default_optional_counts_to_zero(store):
    fields = ["record_date", "store", "product", "kind", "produced", "sold"]
    text = csv_text([{
        "record_date": "2026-10-19", "store": "High Street", "product": "Bread",
        "kind": "finished_product", "produced": "10", "sold": "10",
    }], fields)
    preview = store.preview_import(text)
    assert preview["valid"]
    entry = preview["rows"][0]["entry"]
    assert entry["opening_stock"] == entry["donated"] == entry["discarded"] == entry["closing_stock"] == 0
    assert entry["unit_cost"] is None


@pytest.mark.parametrize("text", [
    "",
    "record_date,store,product,kind\n",
    "record_date,store,kind,produced,sold\n2026-10-19,High Street,finished_product,1,1\n",
    "record_date,store,product,kind,unexpected\n2026-10-19,High Street,Bread,finished_product,1\n",
    "record_date,store,product,kind,store\n2026-10-19,High Street,Bread,finished_product,High Street\n",
    "record_date,store,product,kind\n2026-10-19,High Street,Bread,finished_product,extra\n",
    "record_date,store,product,kind\n2026-10-19,High Street\n",
], ids=["empty", "header-only", "missing-header", "unknown-header", "duplicate-header", "extra-cell", "missing-cells"])
def test_empty_bad_headers_and_misaligned_rows_are_rejected(store, text):
    invalid_preview(store, text)
    assert store.list_entries(include_archived=True) == []


@pytest.mark.parametrize("row", [
    finished(sold_out_at="9:30"),
    finished(sold_out_at="19:00", closing_time="18:00"),
    finished(produced=11, closing_stock=1, sold_out_at="14:00"),
    finished(produced=""),
    finished(sold=""),
    finished(discarded="NaN"),
    production(waste_kg="0.0001"),
    production(produced=1),
])
def test_import_reuses_daily_entry_validation_for_each_stream(store, row):
    invalid_preview(store, csv_text([row]))
    assert store.list_entries() == []


@pytest.mark.parametrize("text", [
    csv_text([finished(product=f"Product {index}") for index in range(2001)]),
    "x" * (2 * 1024 * 1024 + 1),
], ids=["too-many-rows", "too-large-file"])
def test_import_limits_do_not_write_any_records(store, text):
    try:
        result = store.preview_import(text)
    except ValueError:
        pass
    else:
        assert result["valid"] is False and result["errors"]
    assert store.list_entries(include_archived=True) == []


def test_comparison_uses_previous_calendar_week_and_the_same_store_filter(store):
    store.create(finished(record_date="2026-10-12", sold=5, discarded=4,
                          sold_out_at="14:00", closing_time="18:00"))
    store.create(production(record_date="2026-10-12", waste_kg="1.000"))
    store.create(finished())
    store.create(production(waste_kg="0.250"))
    store.create(finished(store="Other store", sold=1, discounted_sold=0, donated=0, discarded=9))
    comparison = store.weekly_report("2026-10-21", store=" HIGH STREET ")["comparison"]
    assert comparison["previous_week_start"] == "2026-10-12"
    assert comparison["previous_week_end"] == "2026-10-18"
    assert comparison["current_entry_count"] == comparison["previous_entry_count"] == 2
    assert comparison["current_days"] == comparison["previous_days"] == 1
    assert comparison["comparable"] is True
    metric = comparison["metrics"]["finished_discarded"]
    assert metric["current"] == 2 and metric["previous"] == 4 and metric["change"] == -2
    assert metric["change_pct"] == pytest.approx(-50.0)
    assert metric["current_records"] == metric["previous_records"] == 1
    assert metric["comparable"] is True
    weight = comparison["metrics"]["production_waste_kg"]
    assert Decimal(str(weight["current"])) == Decimal("0.250")
    assert Decimal(str(weight["previous"])) == Decimal("1.000")
    assert Decimal(str(weight["change"])) == Decimal("-0.750")
    assert weight["change_pct"] == pytest.approx(-75)
    assert weight["current_records"] == weight["previous_records"] == 1
    assert weight["comparable"] is True
    early = comparison["metrics"]["early_sellout_entries"]
    assert early["current"] == 0 and early["previous"] == 1 and early["change"] == -1
    assert comparison["note"]


def test_comparison_shows_recorded_day_coverage_instead_of_assuming_complete_weeks(store):
    store.create(finished(record_date="2026-10-12"))
    store.create(production(record_date="2026-10-12"))
    store.create(finished())
    store.create(finished(record_date="2026-10-20"))
    store.create(production(record_date="2026-10-20"))
    comparison = store.weekly_report("2026-10-19")["comparison"]
    assert comparison["current_entry_count"] == 3 and comparison["previous_entry_count"] == 2
    assert comparison["current_days"] == 2 and comparison["previous_days"] == 1
    assert comparison["comparable"] is True
    assert "record" in comparison["note"].lower()


def test_previous_zero_waste_has_no_percentage_change_even_when_both_weeks_have_records(store):
    store.create(finished(record_date="2026-10-12", sold=10, donated=0,
                          discounted_sold=0, discarded=0, reason=""))
    store.create(finished())
    comparison = store.weekly_report("2026-10-19")["comparison"]
    assert comparison["comparable"] is True
    discarded = comparison["metrics"]["finished_discarded"]
    assert discarded["previous"] == 0 and discarded["current"] == discarded["change"] == 2
    assert discarded["change_pct"] is None


def test_no_previous_records_are_not_presented_as_a_zero_waste_baseline(store):
    store.create(finished())
    comparison = store.weekly_report("2026-10-19")["comparison"]
    assert comparison["comparable"] is False
    assert comparison["previous_entry_count"] == comparison["previous_days"] == 0
    assert all(metric["change_pct"] is None for metric in comparison["metrics"].values())
    assert comparison["note"]


def test_archived_previous_week_records_do_not_contribute_to_comparison(store):
    old = store.create(finished(record_date="2026-10-12"))
    store.archive(old["id"], old["revision"])
    store.create(finished())
    comparison = store.weekly_report("2026-10-19")["comparison"]
    assert comparison["previous_entry_count"] == 0
    assert comparison["metrics"]["finished_discarded"]["previous"] == 0
    assert comparison["comparable"] is False


def test_a_missing_measurement_stream_is_not_a_zero_waste_observation(store):
    # Both weeks contain records, but they do not measure the same waste stream.
    store.create(finished(record_date="2026-10-12"))
    store.create(production())
    comparison = store.weekly_report("2026-10-19")["comparison"]
    assert comparison["comparable"] is True
    items = comparison["metrics"]["finished_discarded"]
    assert items["current_records"] == 0 and items["previous_records"] == 1
    assert items["comparable"] is False and items["change_pct"] is None
    kilograms = comparison["metrics"]["production_waste_kg"]
    assert kilograms["current_records"] == 1 and kilograms["previous_records"] == 0
    assert kilograms["comparable"] is False and kilograms["change_pct"] is None


def test_early_sellout_comparison_needs_both_times_in_each_week(store):
    store.create(finished(record_date="2026-10-12", sold_out_at="12:00", closing_time="18:00"))
    store.create(finished(sold_out_at="12:00", closing_time=""))
    metric = store.weekly_report("2026-10-19")["comparison"]["metrics"]["early_sellout_entries"]
    assert metric["previous_records"] == 1 and metric["current_records"] == 0
    assert metric["comparable"] is False and metric["change_pct"] is None


def test_known_sellout_times_allow_an_arithmetic_comparison(store):
    store.create(finished(record_date="2026-10-12", sold_out_at="12:00", closing_time="18:00"))
    store.create(finished(sold_out_at="18:00", closing_time="18:00"))
    metric = store.weekly_report("2026-10-19")["comparison"]["metrics"]["early_sellout_entries"]
    assert metric["current_records"] == metric["previous_records"] == 1
    assert metric["comparable"] is True
    assert metric["previous"] == 1 and metric["current"] == 0
    assert metric["change_pct"] == pytest.approx(-100)
