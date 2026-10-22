# Bakery Lab

A local prototype for recording bakery production and waste, reviewing weekly reports, and learning sales forecasting with Python.

**Open source · MIT licence · Python 3.11+ · Local data storage**

[Source code and issues](https://github.com/fortikday/bakery-lab)

Anyone can use, modify, and share this project under the [MIT licence](LICENSE).
Each installation keeps its own bakery records on its computer. This version
runs locally; a shared hosted service is a separate future project.

![Bakery Lab daily log](daily-log-preview.png)

## Get started

On GitHub, choose **Code → Download ZIP**, extract the archive, and open a
terminal in the extracted project folder. Install Python 3.11 or newer if
needed, then run `python serve.py` (`py serve.py` also works on Windows).
The daily log needs no extra packages. The steps below explain the optional
forecasting experiment and notebook.

The app follows your computer's local date and timezone. Your bakery records
stay in `local/`, which is excluded from the source repository and release ZIP.

## Join the project

Bug reports, practical bakery feedback, documentation improvements, and code
contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) to get started.
Use fictional examples in public issues and pull requests. Read
[SECURITY.md](SECURITY.md) for security reporting and local-use limits.

The bundled public dataset has its own retained MIT notice; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution.

## Use the daily log

Run this command from the project folder:

```powershell
python serve.py
```

On Windows, `py serve.py` also works if that is how Python is installed. This
part uses Python's standard library and needs no package installation. It opens
the daily log at `http://127.0.0.1:8765/log.html`. Keep the terminal running and
stop it with Ctrl+C when finished.

The daily log starts empty. Your entries are saved on this computer in
`local/waste-log.sqlite3`, separately from the public forecasting data. Records
remain after refreshing the page or restarting the server. The downloadable
project archive excludes this local database.

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
metadata unchanged. For a complete backup, stop the server and copy
`local/waste-log.sqlite3` to a safe location.

## See the prototype

Open **index.html** in your browser, or follow Sales experiment from the daily
log. The sales dashboard contains the results already calculated from the
bundled data. It works offline and lets you choose a store, explore sales
patterns, and compare forecasts with what actually happened. Opening the daily
log as a file shows instructions to start the local Python server.

The numbers are **scaled sales values**, not item counts, kilograms, or money. Negative values are valid. The dashboard measures forecast error; it does not measure waste prevented or money saved.

## Run the Python project

Use Python 3.11 or newer. Open a terminal in this project folder, where `run.py` is located.

On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

If your Windows installation uses `py`, use `py -m venv .venv` for the first command. The remaining commands stay the same. You do not need to activate the environment.

On macOS or Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

The first installation needs internet access. The dataset is included, so running the analysis afterward works offline.

Running the project refreshes:

- `index.html`: the browser dashboard.
- `results/summary.json`: data coverage, results, and the dashboard's data.
- `results/predictions.csv`: the historical forecasts and observed values.
- `results/metrics.csv`: the comparison for every store, including stores without enough history.

The same local server serves both the daily log and the historical sales
dashboard. Opening `index.html` directly still works without a Python process;
saving daily entries requires the local server.

## Learn with the notebook

Open `starter.ipynb` in VS Code with Jupyter support, or start JupyterLab:

```powershell
.\.venv\Scripts\python -m jupyterlab starter.ipynb
```

On macOS or Linux, replace the executable above with `.venv/bin/python`.

Choose the project's Python environment and run the notebook cells from top to bottom. The notebook explains how to load the data, check missing information, draw charts, make a baseline forecast, and compare it with a machine-learning model.

## What the experiment tests

The question is: can a small model predict the next week's scaled sales better than repeating the previous week's values?

- The **baseline** repeats sales from the same weekday one week earlier.
- The **ML model** is a Random Forest with fixed settings. It learns from earlier sales and calendar information.
- Each store's final **56 calendar days** form the evaluation period. Predictions are issued in seven-day blocks, and the model is retrained as earlier weeks become observed.
- Both methods are scored on the same dates. Stores with too little training history are shown as ineligible rather than given a misleading comparison.
- **MAE** is the average absolute distance between a prediction and the observed value. Lower is better. Its units here are scaled sales points. RMSE is another error measure that gives large mistakes more weight.
- A positive `improvement_pct` means the ML model reduced MAE relative to the baseline. A negative value means it performed worse. This is not an accuracy score or a percentage of food saved.

The model uses sales lags of at least seven calendar days and rolling features shifted back seven days. This keeps the whole forecast week independent of sales observed during that week. Calendar flags are known in advance. Actual weather from forecast dates, unsold quantities, and order quantities are excluded from the predictors.

This is a historical evaluation using the supplied transformed data. The original scaling procedure is not documented sufficiently to reconstruct raw sales or audit its fitting period. Sales also differ from true demand when a store sells out. Forecast results alone cannot establish how much food would have been discarded or whether an owner would pay for the product.

## Data and attribution

Source: [Green AI Hub Mittelstand — Reduce Foodwaste Dataset](https://github.com/Green-AI-Hub-Mittelstand/Reduce-Foodwaste-Dataset).

This project bundles `train.csv` from source commit `3bde2d0f9b256ffc800932ac8574a695909f59a5`. It contains 5,142 store-day observations from nine stores, from August 2, 2021 to November 30, 2023. The source project's wider description also covers later data, but this prototype uses only the training file.

The original repository's MIT licence notice is preserved in `data/LICENSE`, and its description is in `data/README.md`. Download details and the file checksum are recorded in `data/source.json`. Keep these notices when sharing the bundled data.

Some `unsold` and `ordered` values are missing. These columns are scaled too. Unsold items might be donated, carried forward, discounted, or discarded; do not treat all unsold items as waste. Do not divide transformed `unsold` and `ordered` values to calculate a physical waste rate.

## Where to look in the code

| File | Purpose |
| --- | --- |
| `analysis.py` | Load and validate data, create features, run the historical forecast comparison. |
| `run.py` | Run the analysis and write the dashboard and result files. |
| `serve.py` | Serve the daily log and its local API, plus the historical dashboard. |
| `waste_log.py` | Validate records, save them in SQLite, and calculate weekly reports. |
| `csv_records.py` | Parse the daily-log CSV format and create the blank template and fictional example. |
| `log.html` | Daily entries, CSV preview/import, corrections, archive recovery, and week comparisons. |
| `fetch_data.py` | Restore the exact original data snapshot with `python fetch_data.py --force`. |
| `starter.ipynb` | Learn the analysis step by step. |
| `templates/dashboard.html` | Browser dashboard layout and interactions. |
| `data/` | Bundled source data and attribution. |
| `results/` | Generated evaluation results. |

## Verification

Developer checks cover calendar gaps, preserving negative values, missing history,
input validation, and whether changing sales inside a forecast week can affect
that week's predictions. Import checks cover preview without writes, row
validation, duplicate prevention, all-or-nothing saving, stale previews, and
simultaneous imports. Comparison checks cover store filters, recorded-day and
measurement coverage, missing data, and zero percentage denominators.
To run them in your environment:

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest tests -q
```

The supplied notebook has also been run from top to bottom; its saved outputs
show the first experiment. `results/environment.json` records the library
versions used for the delivered results.

## A useful next experiment

Start with one store. Explain its weekly pattern, inspect the dates with the largest forecast errors, and decide what extra information would have helped. Keep the original evaluation dates when comparing changes.

To develop this into a business, the next research step is finding bakery owners willing to discuss their ordering process and test a prototype. A real pilot would need raw production, sales, sellout, and discard records before making production recommendations or measuring waste reduction. Accounts, payments, deployment, and operational baking recommendations are outside this first prototype.
