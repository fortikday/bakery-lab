"""The explicit CSV format for daily records: parse, validate, and make templates."""

import csv
from datetime import date, timedelta
import io

from waste_log import validate_entry

MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 2000
EXPORT_FORMAT = "bakery-log-v3"
METADATA_FIELDS = {"id", "revision", "csv_format"}
CSV_FIELDS = ["id", "revision", "record_date", "store", "product", "kind", "opening_stock", "produced",
              "sold", "discounted_sold", "donated", "discarded", "closing_stock", "sold_out_at",
              "closing_time", "waste_kg", "reason", "unit_cost", "currency", "notes", "csv_format"]
REQUIRED_HEADERS = {"record_date", "store", "product", "kind"}


def parse_csv_records(text):
    """Preview every nonblank record; this function never writes to a database.

    Row numbers count CSV records, including the header as row 1. A quoted note
    can contain a newline without creating another record. Empty cells use the
    same optional-field defaults as manual entry; required quantities stay required.
    """
    if not isinstance(text, str):
        raise ValueError("Choose a UTF-8 CSV file to preview.")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError("The CSV must contain valid UTF-8 text.") from exc
    if size > MAX_CSV_BYTES:
        raise ValueError("CSV files must be no larger than 2 MB.")
    rows, errors = [], []
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff"), newline=""), strict=True)
        headers = reader.fieldnames
        if not headers:
            raise ValueError("The CSV is empty. Start with the downloadable template.")
        headers = [name.strip() for name in headers]
        reader.fieldnames = headers
        if len(headers) != len(set(headers)):
            raise ValueError("The CSV contains duplicate column names.")
        missing = REQUIRED_HEADERS - set(headers)
        unknown = set(headers) - set(CSV_FIELDS)
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}.")
        if unknown:
            raise ValueError(f"Unknown CSV columns: {', '.join(sorted(unknown))}. Use the provided template.")
        for row_number, raw in enumerate(reader, start=2):
            if None in raw or any(value is None for value in raw.values()):
                rows.append({"row": row_number, "status": "error", "entry": None,
                             "message": "The number of cells does not match the header. Quote notes containing commas."})
            elif any(value.strip() for value in raw.values()):
                try:
                    marker = raw.get("csv_format", "").strip()
                    if marker and marker != EXPORT_FORMAT:
                        raise ValueError("This CSV uses an unsupported export format.")
                    payload = {}
                    for key, value in raw.items():
                        if key in METADATA_FIELDS or not value.strip():
                            continue
                        # App exports protect spreadsheet cells with a quote.
                        # Only an explicit format marker authorizes decoding it.
                        if marker == EXPORT_FORMAT and value.startswith("'"):
                            remainder = value[1:]
                            if remainder.startswith("'") or remainder.lstrip().startswith(("=", "+", "-", "@")):
                                value = remainder
                        payload[key] = value.strip()
                    entry = validate_entry(payload)
                    rows.append({"row": row_number, "status": "ready", "entry": entry, "message": "Ready to import"})
                except ValueError as exc:
                    rows.append({"row": row_number, "status": "error", "entry": None, "message": str(exc)})
            if len(rows) > MAX_CSV_ROWS:
                raise ValueError(f"Import at most {MAX_CSV_ROWS:,} records in one file.")
        if not rows:
            raise ValueError("The CSV has a header but no records. Add at least one daily entry.")
    except (ValueError, csv.Error) as exc:
        errors.append({"row": None, "message": str(exc)})
    return {"rows": rows, "errors": errors}


def entry_key(entry):
    return (entry["record_date"], entry["store"].casefold(), entry["product"].casefold(), entry["kind"])


def template_csv():
    output = io.StringIO(newline="")
    csv.writer(output).writerow([name for name in CSV_FIELDS if name not in METADATA_FIELDS])
    return output.getvalue()


def example_csv(today=None):
    """Fictional records for two completed weeks, never mixed into data automatically."""
    today = today or date.today()
    last_week = today - timedelta(days=today.weekday() + 7)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=[name for name in CSV_FIELDS if name not in METADATA_FIELDS])
    writer.writeheader()
    for week_offset in (-7, 0):
        for day_offset in range(5):
            when = last_week + timedelta(days=week_offset + day_offset)
            discarded = (8 if week_offset == -7 else 5) if day_offset != 4 else 0
            donated = 2 if day_offset != 4 else 0
            common = {"record_date": when.isoformat(), "store": "Example Bakery (fictional)",
                      "notes": "FICTIONAL EXAMPLE for learning the import workflow; not measured bakery data."}
            writer.writerow(common | {
                "kind": "finished_product", "product": "Example croissant", "produced": 100,
                "sold": 100 - discarded - donated, "donated": donated, "discarded": discarded,
                "reason": "overproduction" if discarded else "", "unit_cost": "0.60", "currency": "GBP",
                "sold_out_at": "16:00" if day_offset == 4 else "", "closing_time": "18:00",
            })
            writer.writerow(common | {"kind": "production_waste", "product": "Example dough",
                "waste_kg": "0.500" if week_offset == -7 else "0.400", "reason": "preparation_error",
                "unit_cost": "4.00", "currency": "GBP"})
    return output.getvalue()
