# Bakery guide

## Open Bakery Lab

**Portable Windows package:** extract the whole folder, then double-click
`BakeryLab.exe`. Keep the support files beside it. This package includes Python;
you do not need to install Python or type a command. Bakery Lab opens your
browser and a running window. Keep that window open while using the app;
you can minimize it. Close it when finished. The window shows the browser
address and the data folder if you need to find either again.

**Source download from GitHub:** this is the code, not the portable package.
Install Python 3.11 or newer. On Windows, double-click **Start Bakery Lab.cmd**.
You can also run `python serve.py` from the project folder on any supported
computer. The daily log needs no extra packages. The desktop launcher requires
Tk, which is normally included with the Windows Python installer.

## Keep your records safe

Use **Download full backup** in the app's backup section. Choose a place you can
find again, such as an external drive or your own protected backup folder. This
download contains the complete database, including archived records, record IDs,
and current revision numbers. It does not contain a history of every past edit.
It contains private bakery data; share it only deliberately.

The app also updates a recovery copy for the current calendar day after a
successful save, edit, archive, restore, or CSV import. Earlier days' copies are
kept. These copies are on the same computer and do not protect against losing
the device. Check the status in the app; if an automatic copy fails, your saved
record remains saved and the app shows a warning.

No automatic deletion is performed in this version. Keep an eye on disk space
as daily recovery copies accumulate.

To recover a full backup:

1. Exit Bakery Lab and close every other running copy. If you started
   `serve.py`, stop it with Ctrl+C. Open the data folder listed below by
   pasting its address into File Explorer's address bar.
2. Make a separate copy of the existing `waste-log.sqlite3` before replacing it.
   This preserves the records you have now.
3. Copy your chosen downloaded backup into the data folder and name it
   `waste-log.sqlite3`. Restore only a backup made by Bakery Lab that you trust.
4. Reopen Bakery Lab and check the expected dates, stores, and archived entries.

Recovery replaces the complete log with the saved snapshot; it does not merge
two logs. CSV import adds records and is a different operation. An in-app full
backup recovery screen is not included in this version.

For the portable Windows app, the data folder is
`%LOCALAPPDATA%\BakeryLab\local`. Source mode uses the project's `local/` folder.
Daily recovery files are beside the database in `waste-log.sqlite3-backups/`.
An explicit custom database path uses the corresponding adjacent backup folder.

## Review a week

Choose a week and a store if needed. Check **Days recorded** before interpreting
totals. A date without an entry can be a closed day, a future day, or a missing
record; it does not establish zero waste. Several entries on one date still
count as one recorded date. A recorded day need not cover every product.

Use discarded-item counts, production-waste kg, reasons, and recorded early
sellouts to choose a question for your team. Compare weeks with similar
recording coverage. A smaller recorded total alone is not proof that waste
fell or money was saved.

## Record the day

Open **Daily log** in the app. Your own log starts empty and stays separate
from the public forecasting experiment. Records remain after refreshing the
page or reopening the app. The data locations are listed above; your database
and recovery copies are excluded from shared source and app downloads.

- **Finished products:** record opening stock, baked, sold, donated, discarded,
  and closing stock in whole items. Discounted sales are a subset of sold.
- **Production waste:** record discarded materials, such as excess dough, in kg.
- **Sellout time:** optionally record the final same-day sellout and closing time.
  The report flags a sellout before closing only when both times are supplied.
  It does not estimate missed sales or automatically change production targets.
- **Weekly report:** choose a week and optionally a store. See discarded items,
  production waste kg, waste reasons, and recorded sellouts. These measurements
  are never added together into a mixed-unit total.
- **Optional costs:** enter production cost per item or per kg and its currency
  code. Estimated cost uses only recorded discarded quantities. Missing costs
  remain unknown, and different currencies are reported separately.
- **Corrections:** edit entries with mistakes. Archiving hides a record from
  reports; use Show archived entries and Restore to recover it, even after a
  refresh. Duplicate daily entries for the same store, product and type are
  rejected. If an entry changed in another tab, refresh before editing it.
- **Import and export:** preview past daily records from CSV before saving them.
  Export downloads active records for the selected week and store filter. See
  the import and backup instructions below.

For finished products, the form checks this equation before saving:

```text
Opening stock + baked = sold + donated + discarded + closing stock
```

Carry-over stock is entered manually; this is not a full inventory system. New
logs do not retrain the demonstration model. There are no accounts, shared cloud
storage, or payments in this local version.

## Import past records from CSV

With the local app running, open **Import records**:

1. Download the blank template and add your records, or download the explicitly
   **fictional example CSV** to practise. The example is not loaded automatically;
   importing it will add clearly named example records to your local log.
2. Choose your UTF-8, comma-separated CSV file, then select **Preview import**.
   Files can contain at most **2 MB and 2,000 records**. Choosing or previewing a
   file does not save entries.
3. Review the row checks and correct every issue in the file. The preview table
   shows up to 20 rows, but the server checks the whole file.
4. Select **Save entries** after all rows pass. The whole file is saved together,
   or no rows are saved. Changing the file requires a new preview. If another
   entry changes while you are reviewing, preview again before saving.

Use one row per date, store, product or material, and entry type. Column names
and `kind` values use the spellings below:

| Rows | Required headers and values |
| --- | --- |
| Every row | `record_date` in `YYYY-MM-DD` format, `store`, `product`, and `kind`. |
| Finished products | `kind` is `finished_product`; supply `produced` and `sold` as nonnegative whole-item counts, including zero when appropriate. |
| Production waste | `kind` is `production_waste`; supply positive `waste_kg` with up to three decimal places and a `reason`. |

Optional finished-product fields are `opening_stock`, `discounted_sold`,
`donated`, `discarded`, `closing_stock`, `sold_out_at`, and `closing_time`.
Blank optional counts become zero. Times use 24-hour `HH:MM`; leave unknown times
blank. Leave fields belonging to the other entry type blank. The same quantity
reconciliation and sellout rules used by the daily form apply to imported rows.

The reason codes are `overproduction`, `low_demand`, `damage`, `expiry`,
`preparation_error`, and `other`. A reason is required when finished products
were discarded, and for every production-waste record. Both entry types can
include `notes`, optional `unit_cost` with up to four decimal places, and a
three-letter `currency` code when a cost is provided. Blank cost stays unknown;
an entered zero cost is a known zero.

Duplicate records within the file or already in the log are rejected, including
differences in name capitalisation or surrounding spaces. Imports add new
records; correct existing records with **Edit**. Use the app's daily-log format,
not the differently structured, scaled sales file in `data/train.csv`.

## Compare weeks and keep backups

The weekly report compares the selected Monday-to-Sunday week with the previous
calendar week using the same store filter. It shows entry and recorded-day
coverage, plus separate changes for discarded finished items, production kg,
and recorded sellouts before closing. Sellout comparison needs both sellout and
closing times; the waste measures each need records of their own type in both
weeks. Missing records are unknown, not measured zero waste. Percentage changes
are omitted when coverage is missing or the earlier measured total is zero.

These are **changes in recorded totals**, not proof of savings or prevented
waste. Weeks can cover different days, products, or production volumes.

An app-exported CSV can be previewed and imported, but it contains only the
active records for its selected week and store filter. Imported records receive
new IDs; CSV does not restore archive or revision history. Keep app export
metadata unchanged. For a complete backup, use **Download full backup** in the app.
It includes all stores, weeks, archived records, IDs, and revisions. The backup
can be downloaded while the app is running. See the backup steps above.

