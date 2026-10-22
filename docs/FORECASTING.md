# Python learning and forecasting experiment

Run the commands below from the project root, one directory above this guide.
The experiment is separate from the bakery's daily log. It uses a public,
scaled historical dataset and does not train on your local entries.

## Explore the historical sales experiment

Open **index.html** in your browser, or follow Sales experiment from the daily
log. The sales dashboard contains the results already calculated from the
bundled data. It works offline and lets you choose a store, explore sales
patterns, and compare forecasts with what actually happened. Opening the daily
log as a file shows instructions to start the local Python server.

The numbers are **scaled sales values**, not item counts, kilograms, or money. Negative values are valid. The dashboard measures forecast error; it does not measure waste prevented or money saved.

## Run the analysis

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

The original repository's MIT licence notice is preserved in `data/LICENSE` (in the project root), and its description is in `data/README.md`. Download details and the file checksum are recorded in `data/source.json`. Keep these notices when sharing the bundled data.

Some `unsold` and `ordered` values are missing. These columns are scaled too. Unsold items might be donated, carried forward, discounted, or discarded; do not treat all unsold items as waste. Do not divide transformed `unsold` and `ordered` values to calculate a physical waste rate.


## Limits of the current comparison

The current evaluation covers nine source stores, with eight eligible for the
final held-out comparison. It uses one 56-day period per eligible store. There
are no confidence intervals or significance tests in this version, so the
reported improvement is a descriptive result on these dates, not a reliable
estimate of the benefit at another bakery.

Model settings are fixed. The experiment currently compares the Random Forest
with one seasonal naive baseline. Stronger simple baselines, multiple time
windows, and uncertainty estimates remain research work. Tuning a model must
use earlier training/validation periods rather than the reported holdout.

Raw production, sales, discard, and sellout records from a real pilot are needed
before evaluating baking decisions or any measured waste reduction.
