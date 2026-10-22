# Changes

## 0.2.0 — usability preview

- Portable 64-bit Windows launcher with Python included. It opens the browser;
  keep its running window open while using the app.
- Source Windows launcher with a browser-only fallback when Tk is unavailable.
- Full SQLite backup downloads and automatic daily recovery snapshots.
  Snapshots coordinate across app instances; delayed responses cannot hide a
  newer backup warning. No recovery-copy retention deletion is performed.
- Weekly recording coverage, explicit unknown measurements, and a descriptive
  product review prompt.
- Short README, separate bakery and Python/forecasting guides, and a proposed
  pilot plan. No bakery pilot or measured savings are claimed.

Validation: 134 Python tests, browser-state checks, browser backup download
with fictional records, and a packaged backend smoke check on Windows 11 x64.
The portable preview is unsigned; the native launch window has not been
interactively tested on other Windows installations.

## First public prototype

Daily recording, CSV preview/import, weekly comparisons, archive recovery,
and a separate historical forecasting learning experiment. MIT licensed.
