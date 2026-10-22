"""Validate and store a bakery's own daily records, separately from demo sales.

Finished products are counted as items. Production waste is weighed in kg.
Neither is inferred from the historical dataset's transformed sales values.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

REASONS = {"overproduction", "low_demand", "damage", "expiry", "preparation_error", "other"}
COUNTS = ("opening_stock", "produced", "sold", "discounted_sold", "donated", "discarded", "closing_stock")
COMMON = {"record_date", "store", "product", "kind", "reason", "notes", "unit_cost", "currency", "id", "revision"}


class ConflictError(ValueError):
    """A duplicate entry or a newer revision needs the user's attention."""


class NotFoundError(LookupError):
    """The requested entry does not exist."""


def _text(value, label, *, required=False, limit=120):
    if not isinstance(value, str):
        if value is None and not required:
            return ""
        raise ValueError(f"{label} must be text.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{label} is required.")
    if len(value) > limit:
        raise ValueError(f"{label} must be at most {limit} characters.")
    return value


def _date(value, label="Date"):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{label} must use YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid calendar date.") from exc


def _decimal(value, label, *, places, required=False, positive=False, maximum="1000000"):
    if value is None or value == "":
        if required:
            raise ValueError(f"{label} is required.")
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number.")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number > Decimal(maximum):
            raise ValueError(f"{label} must be a finite number between 0 and {maximum}.")
        if positive and number == 0:
            raise ValueError(f"{label} must be greater than zero.")
        quantized = number.quantize(Decimal(1).scaleb(-places))
        if number != quantized:
            raise ValueError(f"{label} can have at most {places} decimal places.")
        return quantized
    except InvalidOperation as exc:
        raise ValueError(f"{label} must be a valid number.") from exc


def _count(payload, name):
    value = payload.get(name, None if name in {"produced", "sold"} else 0)
    number = _decimal(value, name.replace("_", " ").capitalize(), places=0,
                      required=True, maximum="10000000")
    return int(number)


def _time(value, label):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError(f"{label} must use 24-hour HH:MM, or be left blank.")
    return value


def validate_entry(payload: dict) -> dict:
    """Return a clean record or a useful error; missing cost remains unknown."""
    if not isinstance(payload, dict):
        raise ValueError("An entry must be a JSON object.")
    kind = payload.get("kind")
    if not isinstance(kind, str) or kind not in {"finished_product", "production_waste"}:
        raise ValueError("Choose finished product or production waste.")
    allowed = COMMON | (set(COUNTS) | {"sold_out_at", "closing_time"} if kind == "finished_product" else {"waste_kg"})
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"Unexpected fields for this entry type: {', '.join(sorted(unknown))}.")
    record = {
        "record_date": _date(payload.get("record_date")).isoformat(),
        "store": _text(payload.get("store"), "Store", required=True, limit=80),
        "product": _text(payload.get("product"), "Product or material", required=True),
        "kind": kind,
        "reason": _text(payload.get("reason", ""), "Reason", limit=40),
        "notes": _text(payload.get("notes", ""), "Notes", limit=1000),
    }
    if record["reason"] and record["reason"] not in REASONS:
        raise ValueError("Choose one of the listed waste reasons.")
    cost = _decimal(payload.get("unit_cost"), "Production cost", places=4)
    currency = _text(payload.get("currency", ""), "Currency", limit=3).upper()
    if (cost is not None or currency) and not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("Enter a three-letter currency code when providing a cost, for example GBP.")
    record.update(unit_cost=format(cost, ".4f") if cost is not None else None, currency=currency)
    if kind == "finished_product":
        record.update({name: _count(payload, name) for name in COUNTS})
        if record["discounted_sold"] > record["sold"]:
            raise ValueError("Discounted sales are part of total sales and cannot exceed total sold.")
        available = record["opening_stock"] + record["produced"]
        accounted = record["sold"] + record["donated"] + record["discarded"] + record["closing_stock"]
        if available != accounted:
            raise ValueError(
                f"Quantities do not reconcile: {available} available, {accounted} accounted for. "
                "Opening stock + baked must equal sold + donated + discarded + closing stock."
            )
        record["sold_out_at"] = _time(payload.get("sold_out_at"), "Sellout time")
        record["closing_time"] = _time(payload.get("closing_time"), "Closing time")
        if record["sold_out_at"] and record["closing_stock"]:
            raise ValueError("A final sellout time cannot be recorded while closing stock remains.")
        if record["sold_out_at"] and record["sold"] == 0:
            raise ValueError("A sellout time requires at least one recorded sale.")
        if record["sold_out_at"] and record["closing_time"] and record["sold_out_at"] > record["closing_time"]:
            raise ValueError("Final sellout time cannot be after the same-day closing time.")
        has_waste = record["discarded"] > 0
    else:
        record["waste_kg"] = format(_decimal(payload.get("waste_kg"), "Production waste (kg)",
                                              places=3, required=True, positive=True), ".3f")
        has_waste = True
    if has_waste and not record["reason"]:
        raise ValueError("Choose a reason for the discarded product or production waste.")
    return record


def _revision(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("A valid entry revision is required. Refresh and try again.")
    return value


class LogStore:
    """One SQLite connection per operation keeps threaded requests independent."""

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS entries (
                id TEXT PRIMARY KEY, record_date TEXT NOT NULL,
                store_key TEXT NOT NULL, product_key TEXT NOT NULL, kind TEXT NOT NULL,
                payload TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
                deleted INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
            connection.execute("""CREATE UNIQUE INDEX IF NOT EXISTS active_daily_product
                ON entries(record_date, store_key, product_key, kind) WHERE deleted = 0""")

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _row(row):
        result = json.loads(row["payload"])
        result.update(id=row["id"], revision=row["revision"], deleted=bool(row["deleted"]),
                      created_at=row["created_at"], updated_at=row["updated_at"])
        return result

    def _get(self, entry_id, connection):
        row = connection.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            raise NotFoundError("This entry was not found. Refresh the daily log.")
        return row

    def create(self, payload):
        record = validate_entry(payload)
        entry_id, now = str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as connection:
                connection.execute("""INSERT INTO entries
                    (id, record_date, store_key, product_key, kind, payload, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (
                    entry_id, record["record_date"], record["store"].casefold(), record["product"].casefold(),
                    record["kind"], json.dumps(record), now, now,
                ))
                return self._row(self._get(entry_id, connection))
        except sqlite3.IntegrityError as exc:
            raise ConflictError("An entry already exists for this date, store, product and type. Edit it instead.") from exc

    def update(self, entry_id, payload):
        record = validate_entry(payload)
        expected = _revision(payload.get("revision"))
        try:
            with self._connect() as connection:
                cursor = connection.execute("""UPDATE entries SET record_date=?, store_key=?, product_key=?,
                    kind=?, payload=?, revision=revision+1, updated_at=? WHERE id=? AND revision=? AND deleted=0""", (
                    record["record_date"], record["store"].casefold(), record["product"].casefold(), record["kind"],
                    json.dumps(record), datetime.now(timezone.utc).isoformat(), entry_id, expected,
                ))
                if cursor.rowcount != 1:
                    self._get(entry_id, connection)
                    raise ConflictError("This entry changed or was archived. Refresh before editing it.")
                return self._row(self._get(entry_id, connection))
        except sqlite3.IntegrityError as exc:
            raise ConflictError("Another entry already uses this date, store, product and type.") from exc

    def _set_archived(self, entry_id, revision, deleted):
        expected = _revision(revision)
        try:
            with self._connect() as connection:
                cursor = connection.execute("""UPDATE entries SET deleted=?, revision=revision+1, updated_at=?
                    WHERE id=? AND revision=? AND deleted=?""", (
                    int(deleted), datetime.now(timezone.utc).isoformat(), entry_id, expected, int(not deleted),
                ))
                if cursor.rowcount != 1:
                    self._get(entry_id, connection)
                    raise ConflictError("This entry changed. Refresh before trying again.")
                return self._row(self._get(entry_id, connection))
        except sqlite3.IntegrityError as exc:
            raise ConflictError("An active record already exists for this date, store, product and type. Edit it instead.") from exc

    def archive(self, entry_id, revision):
        return self._set_archived(entry_id, revision, True)

    def restore(self, entry_id, revision):
        return self._set_archived(entry_id, revision, False)

    def _preview_import(self, text, connection):
        from csv_records import entry_key, parse_csv_records

        parsed = parse_csv_records(text)
        rows = parsed["rows"]
        existing = {tuple(row) for row in connection.execute(
            "SELECT record_date, store_key, product_key, kind FROM entries WHERE deleted=0"
        )}
        seen = {}
        for row in rows:
            if row["status"] != "ready":
                continue
            key = entry_key(row["entry"])
            if key in seen:
                first = seen[key]
                first.update(status="error", message=f"Duplicate daily record also appears in CSV row {row['row']}.")
                row.update(status="error", message=f"Duplicate daily record also appears in CSV row {first['row']}.")
            else:
                seen[key] = row
            if key in existing:
                row.update(status="error", message="This daily record already exists. Edit the saved entry instead of importing it again.")
        errors = parsed["errors"] + [{"row": row["row"], "message": row["message"]}
                                     for row in rows if row["status"] == "error"]
        valid = bool(rows) and not errors
        token = None
        if valid:
            snapshot = [tuple(row) for row in connection.execute("SELECT id, revision, deleted FROM entries ORDER BY id")]
            material = json.dumps({"format": 1, "csv": text, "snapshot": snapshot}, sort_keys=True)
            token = hashlib.sha256(material.encode("utf-8")).hexdigest()
        dates = [row["entry"]["record_date"] for row in rows if row["entry"]]
        return {"valid": valid, "row_count": len(rows), "ready_count": sum(row["status"] == "ready" for row in rows),
                "errors": errors, "rows": rows, "preview_token": token,
                "date_start": min(dates) if dates else None, "date_end": max(dates) if dates else None}

    def preview_import(self, csv_text):
        """Validate the file and check duplicates, without saving any records."""
        with self._connect() as connection:
            # One snapshot covers both duplicate checks and the preview token.
            connection.execute("BEGIN")
            return self._preview_import(csv_text, connection)

    def commit_import(self, csv_text, preview_token):
        """Recheck the preview under a write lock, then save all rows together."""
        if not isinstance(preview_token, str) or not re.fullmatch(r"[a-f0-9]{64}", preview_token):
            raise ConflictError("Preview the CSV before saving it.")
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                preview = self._preview_import(csv_text, connection)
                if not preview["valid"]:
                    # Duplicate changes can occur after a valid preview. Require
                    # another preview rather than skipping or overwriting rows.
                    if any("already exists" in error["message"] for error in preview["errors"]):
                        raise ConflictError("Saved records changed or duplicates were found. Preview the file again.")
                    raise ValueError("The CSV has errors. Preview it again and correct every flagged row.")
                if preview["preview_token"] != preview_token:
                    raise ConflictError("The file or saved records changed after preview. Preview the file again.")
                saved = []
                now = datetime.now(timezone.utc).isoformat()
                for row in preview["rows"]:
                    entry = row["entry"]
                    entry_id = str(uuid.uuid4())
                    connection.execute("""INSERT INTO entries
                        (id,record_date,store_key,product_key,kind,payload,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?)""", (
                        entry_id, entry["record_date"], entry["store"].casefold(), entry["product"].casefold(),
                        entry["kind"], json.dumps(entry), now, now,
                    ))
                    saved.append(self._row(self._get(entry_id, connection)))
                return {"imported_count": len(saved), "entries": saved,
                        "date_start": preview["date_start"], "date_end": preview["date_end"]}
        except sqlite3.IntegrityError as exc:
            raise ConflictError("Saved records changed. No rows were imported; preview the file again.") from exc

    def list_entries(self, week=None, store=None, include_archived=False):
        where, values = [], []
        if not include_archived:
            where.append("deleted=0")
        if week:
            start, end = week_dates(week)
            where.append("record_date BETWEEN ? AND ?")
            values.extend([start.isoformat(), end.isoformat()])
        if store:
            where.append("store_key=?")
            values.append(_text(store, "Store", required=True, limit=80).casefold())
        query = "SELECT * FROM entries" + (" WHERE " + " AND ".join(where) if where else "")
        query += " ORDER BY record_date DESC, store_key, product_key, kind"
        with self._connect() as connection:
            return [self._row(row) for row in connection.execute(query, values)]

    def weekly_report(self, week, store=None):
        start, end = week_dates(week)
        try:
            previous_start, previous_end = start - timedelta(days=7), start - timedelta(days=1)
        except OverflowError as exc:
            raise ValueError("Choose a week after the first week of year 1 to compare it with an earlier week.") from exc
        where, values = ["deleted=0", "record_date BETWEEN ? AND ?"], [previous_start.isoformat(), end.isoformat()]
        if store:
            where.append("store_key=?")
            values.append(_text(store, "Store", required=True, limit=80).casefold())
        with self._connect() as connection:
            # A single SELECT gives both weeks one consistent database snapshot.
            query = "SELECT * FROM entries WHERE " + " AND ".join(where)
            query += " ORDER BY record_date DESC, store_key, product_key, kind"
            records = [self._row(row) for row in connection.execute(query, values)]
        entries = [entry for entry in records if entry["record_date"] >= start.isoformat()]
        previous_entries = [entry for entry in records if entry["record_date"] < start.isoformat()]
        current = self._summarize_week(entries, start, end)
        previous = self._summarize_week(previous_entries, previous_start, previous_end)
        metrics = {}
        for metric, kind in [("finished_discarded", "finished_product"),
                             ("production_waste_kg", "production_waste"),
                             ("early_sellout_entries", "finished_product")]:
            def coverage(items):
                return sum(entry["kind"] == kind and (
                    metric != "early_sellout_entries" or bool(entry.get("sold_out_at") and entry.get("closing_time"))
                ) for entry in items)
            current_records, previous_records = coverage(entries), coverage(previous_entries)
            current_value, previous_value = Decimal(str(current["totals"][metric])), Decimal(str(previous["totals"][metric]))
            change = current_value - previous_value
            comparable = bool(current_records and previous_records)
            kg = metric == "production_waste_kg"
            metrics[metric] = {
                "current": format(current_value, ".3f") if kg else int(current_value),
                "previous": format(previous_value, ".3f") if kg else int(previous_value),
                "change": format(change, ".3f") if kg else int(change),
                "change_pct": float(100 * change / previous_value) if comparable and previous_value != 0 else None,
                "current_records": current_records, "previous_records": previous_records, "comparable": comparable,
            }
        current["comparison"] = {
            "previous_week_start": previous_start.isoformat(), "previous_week_end": previous_end.isoformat(),
            "current_entry_count": len(entries), "previous_entry_count": len(previous_entries),
            "current_days": len({entry["record_date"] for entry in entries}),
            "previous_days": len({entry["record_date"] for entry in previous_entries}),
            "comparable": bool(entries and previous_entries), "metrics": metrics,
            "note": ("Change in recorded totals only. Weeks may cover different days, products or production volumes; "
                     "a change does not establish waste reduction or savings. Missing records are not measured zeros."),
        }
        return current

    @staticmethod
    def _summarize_week(entries, start, end):
        totals = {"finished_produced": 0, "finished_sold": 0, "finished_donated": 0,
                  "finished_discarded": 0, "production_waste_kg": Decimal(0),
                  "sellout_entries": 0, "early_sellout_entries": 0}
        costs, reasons, sellouts = {}, {}, []
        unknown = 0
        for entry in entries:
            if entry["kind"] == "finished_product":
                for target, source in [("finished_produced", "produced"), ("finished_sold", "sold"),
                                       ("finished_donated", "donated"), ("finished_discarded", "discarded")]:
                    totals[target] += entry[source]
                quantity = Decimal(entry["discarded"])
                if entry["sold_out_at"]:
                    early = entry["sold_out_at"] < entry["closing_time"] if entry["closing_time"] else None
                    totals["sellout_entries"] += 1
                    totals["early_sellout_entries"] += int(early is True)
                    sellouts.append({key: entry[key] for key in (
                        "record_date", "store", "product", "sold_out_at", "closing_time"
                    )} | {"early": early})
            else:
                quantity = Decimal(entry["waste_kg"])
                totals["production_waste_kg"] += quantity
            if quantity > 0:
                key = (entry["kind"], entry["reason"])
                reason = reasons.setdefault(key, {"kind": entry["kind"], "reason": entry["reason"],
                    "discarded_items": 0, "production_waste_kg": Decimal(0), "entry_count": 0})
                reason["entry_count"] += 1
                if entry["kind"] == "finished_product":
                    reason["discarded_items"] += entry["discarded"]
                else:
                    reason["production_waste_kg"] += quantity
                if entry["unit_cost"] is None:
                    unknown += 1
                else:
                    code = entry["currency"]
                    costs[code] = costs.get(code, Decimal(0)) + quantity * Decimal(entry["unit_cost"])
        totals["production_waste_kg"] = format(totals["production_waste_kg"], ".3f")
        reason_list = []
        for _, value in sorted(reasons.items()):
            value["production_waste_kg"] = format(value["production_waste_kg"], ".3f")
            reason_list.append(value)
        return {
            "week_start": start.isoformat(), "week_end": end.isoformat(), "entry_count": len(entries),
            "totals": totals,
            "costs": [{"currency": currency, "estimated_cost": format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")}
                      for currency, value in sorted(costs.items())],
            "uncosted_waste_entries": unknown, "reasons": reason_list,
            "sellouts": sellouts, "entries": entries,
        }


def week_dates(value):
    day = _date(value, "Week date")
    start = day - timedelta(days=day.weekday())
    try:
        return start, start + timedelta(days=6)
    except OverflowError as exc:
        raise ValueError("Choose a week within the supported calendar range.") from exc
