"""Business-rule checks for the local production and waste log.

These examples deliberately keep item counts, kilograms, sales and currencies
distinct. They also check that corrections cannot silently replace newer data.
"""

from decimal import Decimal
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from waste_log import ConflictError, LogStore, validate_entry


def finished(**changes):
    payload = {
        "kind": "finished_product", "record_date": "2026-10-19",
        "store": "High Street", "product": "Croissant",
        "opening_stock": 0, "produced": 10, "sold": 7,
        "discounted_sold": 2, "donated": 1, "discarded": 2,
        "closing_stock": 0, "sold_out_at": "", "closing_time": "",
        "reason": "overproduction", "notes": "",
        "unit_cost": "0.25", "currency": "GBP",
    }
    payload.update(changes)
    return payload


def production(**changes):
    payload = {
        "kind": "production_waste", "record_date": "2026-10-19",
        "store": "High Street", "product": "Excess dough",
        "waste_kg": "0.500", "reason": "preparation_error", "notes": "",
        "unit_cost": "4", "currency": "GBP",
    }
    payload.update(changes)
    return payload


@pytest.fixture
def store(tmp_path):
    return LogStore(tmp_path / "waste-log.sqlite3")


def test_quantity_reconciliation_counts_discounted_sales_once():
    # 10 available = 7 sold (including 2 discounted) + 1 donated + 2 discarded.
    result = validate_entry(finished())
    assert result["sold"] == 7
    assert result["discounted_sold"] == 2
    with pytest.raises(ValueError):
        validate_entry(finished(sold=6))
    with pytest.raises(ValueError):
        validate_entry(finished(discounted_sold=8))


def test_opening_stock_and_carry_forward_are_part_of_reconciliation():
    result = validate_entry(finished(opening_stock=3, closing_stock=3))
    assert result["opening_stock"] == 3
    assert result["closing_stock"] == 3
    with pytest.raises(ValueError):
        validate_entry(finished(opening_stock=3, closing_stock=2))


def test_sellout_cannot_be_claimed_without_any_sales():
    with pytest.raises(ValueError, match="at least one recorded sale"):
        validate_entry(finished(produced=0, sold=0, donated=0, discarded=0,
                                discounted_sold=0, sold_out_at="16:00"))


@pytest.mark.parametrize("field,value", [
    ("produced", -1), ("sold", 1.5), ("discarded", True),
    ("donated", float("nan")), ("closing_stock", float("inf")),
    ("opening_stock", "many"),
])
def test_invalid_item_quantities_are_rejected(field, value):
    with pytest.raises(ValueError):
        validate_entry(finished(**{field: value}))


def test_balanced_totals_do_not_make_fractional_or_boolean_item_counts_valid():
    with pytest.raises(ValueError):
        validate_entry(finished(produced=10.5, sold=7.5))
    with pytest.raises(ValueError):
        validate_entry(finished(sold=8, discarded=True))


@pytest.mark.parametrize("changes", [
    {"record_date": "2026-02-30"}, {"record_date": "19/10/2026"},
    {"store": "  "}, {"product": ""}, {"kind": "sales_forecast"},
    {"sold_out_at": "9:30"}, {"sold_out_at": "24:00"},
    {"closing_time": "18:"}, {"closing_time": "12:60"},
    {"reason": ""},
])
def test_invalid_identity_time_or_waste_reason_is_rejected(changes):
    with pytest.raises(ValueError):
        validate_entry(finished(**changes))


def test_sellout_time_is_optional_and_incompatible_with_remaining_stock():
    validate_entry(finished(sold_out_at=""))
    validate_entry(finished(sold_out_at="14:30", closing_time="18:00"))
    with pytest.raises(ValueError):
        validate_entry(finished(produced=11, closing_stock=1, sold_out_at="14:30"))


def test_zero_discard_does_not_require_a_waste_reason():
    result = validate_entry(finished(sold=10, donated=0, discarded=0, reason=""))
    assert result["discarded"] == 0


@pytest.mark.parametrize("value", ["-0.1", "0", "NaN", "Infinity", "0.0001", True])
def test_production_waste_requires_positive_finite_kilograms(value):
    with pytest.raises(ValueError):
        validate_entry(production(waste_kg=value))


def test_production_waste_is_a_separate_measurement_stream():
    result = validate_entry(production())
    assert Decimal(str(result["waste_kg"])) == Decimal("0.5")
    with pytest.raises(ValueError):
        validate_entry(production(reason=""))
    with pytest.raises(ValueError):
        validate_entry(production(produced=10, sold=8, discarded=2))


@pytest.mark.parametrize("changes", [
    {"unit_cost": "-1"}, {"unit_cost": "NaN"},
    {"unit_cost": "Infinity"}, {"unit_cost": "0.12345"},
    {"unit_cost": True}, {"currency": ""}, {"currency": "GB"},
    {"currency": "123"},
])
def test_optional_cost_must_be_finite_and_have_a_currency(changes):
    with pytest.raises(ValueError):
        validate_entry(finished(**changes))


def test_weekly_report_keeps_units_and_currencies_separate(store):
    store.create(finished())
    store.create(finished(product="Muffin", sold=8, donated=0,
                          discounted_sold=0, unit_cost="2", currency="USD"))
    store.create(finished(product="Roll", donated=0, discarded=3,
                          unit_cost="", currency=""))
    store.create(production())
    report = store.weekly_report("2026-10-21")
    assert report["week_start"] == "2026-10-19"
    assert report["week_end"] == "2026-10-25"
    assert report["entry_count"] == 4
    totals = report["totals"]
    assert totals["finished_produced"] == 30
    assert totals["finished_sold"] == 22
    assert totals["finished_donated"] == 1
    assert totals["finished_discarded"] == 7
    assert Decimal(str(totals["production_waste_kg"])) == Decimal("0.5")
    costs = {row["currency"]: Decimal(str(row["estimated_cost"])) for row in report["costs"]}
    assert costs == {"GBP": Decimal("2.50"), "USD": Decimal("4.00")}
    assert report["uncosted_waste_entries"] == 1


def test_missing_cost_is_unknown_but_explicit_zero_is_known(store):
    store.create(finished(product="Unknown cost", unit_cost=None, currency=""))
    store.create(finished(product="Known zero", unit_cost="0", currency="GBP"))
    report = store.weekly_report("2026-10-19")
    assert report["uncosted_waste_entries"] == 1
    assert {r["currency"]: Decimal(str(r["estimated_cost"])) for r in report["costs"]} == {
        "GBP": Decimal("0")
    }


def test_sellout_reporting_only_calls_it_early_when_closing_time_is_known(store):
    store.create(finished(product="Early", sold_out_at="12:30", closing_time="18:00"))
    store.create(finished(product="At closing", sold_out_at="18:00", closing_time="18:00"))
    store.create(finished(product="Unknown closing", sold_out_at="12:30", closing_time=""))
    report = store.weekly_report("2026-10-19")
    assert report["totals"]["sellout_entries"] == 3
    assert report["totals"]["early_sellout_entries"] == 1
    by_product = {row["product"]: row["early"] for row in report["sellouts"]}
    assert by_product == {"Early": True, "At closing": False, "Unknown closing": None}


def test_records_persist_and_week_store_filters_apply(tmp_path):
    path = tmp_path / "persist.sqlite3"
    original = LogStore(path)
    original.create(finished())
    original.create(finished(store="Riverside"))
    original.create(finished(record_date="2026-10-12"))
    reopened = LogStore(path)
    assert len(reopened.list_entries()) == 3
    assert len(reopened.list_entries(week="2026-10-21", store="High Street")) == 1
    assert reopened.weekly_report("2026-10-21", store="Riverside")["entry_count"] == 1


def test_duplicate_store_product_day_is_rejected_and_editing_retains_identity(store):
    saved = store.create(finished())
    with pytest.raises(ConflictError):
        store.create(finished(store="  HIGH STREET  ", product="croissant"))
    updated = store.update(saved["id"], finished(notes="Reviewed", revision=saved["revision"]))
    assert updated["id"] == saved["id"]
    assert updated["revision"] > saved["revision"]
    assert updated["notes"] == "Reviewed"
    assert len(store.list_entries()) == 1
    with pytest.raises(ConflictError):
        store.update(saved["id"], finished(notes="Older tab", revision=saved["revision"]))


def test_archiving_is_recoverable_and_removes_entry_from_report(store):
    saved = store.create(finished())
    archived = store.archive(saved["id"], saved["revision"])
    assert store.list_entries() == []
    assert store.weekly_report("2026-10-19")["entry_count"] == 0
    assert len(store.list_entries(include_archived=True)) == 1
    restored = store.restore(saved["id"], archived["revision"])
    assert restored["id"] == saved["id"]
    assert store.weekly_report("2026-10-19")["entry_count"] == 1
