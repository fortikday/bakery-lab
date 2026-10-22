"""Small, reproducible weekly sales-forecasting experiment.

All reported values stay in the source dataset's scaled sales units. We cannot
reverse its transformation, measure discarded food, or infer baking quantities.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "train.csv"
SOURCE_URL = "https://github.com/Green-AI-Hub-Mittelstand/Reduce-Foodwaste-Dataset"
SOURCE_COMMIT = "3bde2d0f9b256ffc800932ac8574a695909f59a5"
MODEL_NAME = "Random forest"
FEATURES = [
    "lag_7", "lag_14", "lag_21", "lag_28", "same_weekday_mean",
    "previous_week_mean", "previous_four_weeks_mean",
    "weekday_sin", "weekday_cos", "year_sin", "year_cos", "trend_days",
    "state_holiday", "before_state_holiday", "after_state_holiday",
    "school_holiday", "special_day", "before_special_day",
]


def load_data(path: str | Path | None = None) -> pd.DataFrame:
    """Read observations without changing negative values or filling missing days."""
    data = pd.read_csv(Path(path) if path is not None else DATA_PATH)
    required = {"date", "store", "sales", "unsold", "ordered",
                "is_state_holiday", "is_school_holiday", "is_special_day"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"The CSV is missing required columns: {', '.join(sorted(missing))}")
    data["date"] = pd.to_datetime(data["date"], format="%Y-%m-%d", errors="raise")
    if data[["date", "store"]].isna().any().any():
        raise ValueError("Every observation must have a date and a store.")
    if data.duplicated(["date", "store"]).any():
        raise ValueError("There must be at most one observation per store and date.")
    for name in ["sales", "unsold", "ordered"]:
        data[name] = pd.to_numeric(data[name], errors="raise")
        if np.isinf(data[name].to_numpy(dtype=float)).any():
            raise ValueError(f"Column {name} contains an infinite value.")
    if data.empty or data["sales"].notna().sum() == 0:
        raise ValueError("The CSV contains no observed sales.")
    return data.sort_values(["store", "date"]).reset_index(drop=True)


def make_features(store_data: pd.DataFrame) -> pd.DataFrame:
    """Create features available when forecasting up to seven days ahead.

    Reindexing makes a lag of seven mean seven CALENDAR days. Missing dates stay
    missing. The most recent sales input for target day t is t-7, so no sales
    from inside the week being predicted can enter that week's predictions.
    Calendar labels are known in advance; actual future weather is excluded.
    """
    if store_data.empty:
        raise ValueError("No observations were supplied for this store.")
    if store_data["store"].nunique() != 1:
        raise ValueError("Feature construction requires exactly one store.")
    daily = store_data.set_index("date").sort_index()
    daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max(), freq="D"))
    daily.index.name = "date"
    out = pd.DataFrame(index=daily.index)
    out["actual"] = daily["sales"]
    for lag in (7, 14, 21, 28):
        out[f"lag_{lag}"] = daily["sales"].shift(lag)
    out["same_weekday_mean"] = out[[f"lag_{lag}" for lag in (7, 14, 21, 28)]].mean(axis=1)
    # Shift BEFORE rolling: each window ends at t-7, never on target day t.
    previous = daily["sales"].shift(7)
    out["previous_week_mean"] = previous.rolling(7, min_periods=4).mean()
    out["previous_four_weeks_mean"] = previous.rolling(28, min_periods=14).mean()
    weekday = out.index.dayofweek
    year_day = out.index.dayofyear
    out["weekday_sin"] = np.sin(2 * np.pi * weekday / 7)
    out["weekday_cos"] = np.cos(2 * np.pi * weekday / 7)
    out["year_sin"] = np.sin(2 * np.pi * year_day / 365.25)
    out["year_cos"] = np.cos(2 * np.pi * year_day / 365.25)
    out["trend_days"] = (out.index - pd.Timestamp("2021-01-01")).days
    flags = {
        "state_holiday": ("is_state_holiday", "state_holiday"),
        "before_state_holiday": ("is_state_holiday", "day_before"),
        "after_state_holiday": ("is_state_holiday", "day_after"),
        "school_holiday": ("is_school_holiday", "school_holiday"),
        "special_day": ("is_special_day", "special_day"),
        "before_special_day": ("is_special_day", "day_before"),
    }
    for name, (column, value) in flags.items():
        # Preserve unknown calendar labels as missing; the training-only imputer
        # handles them. An absent source date never becomes a zero-sales day.
        out[name] = daily[column].eq(value).astype(float).where(daily[column].notna())
    return out


def new_model():
    """Fixed parameters, chosen before evaluating the held-out weeks."""
    return make_pipeline(
        SimpleImputer(strategy="median", keep_empty_features=True),
        RandomForestRegressor(
            n_estimators=120, max_depth=10, min_samples_leaf=5,
            random_state=42, n_jobs=1,
        ),
    )


def error_scores(actual, predicted) -> dict[str, float]:
    """MAE and RMSE in scaled points; percentage errors do not suit this target."""
    residual = np.asarray(actual, dtype=float) - np.asarray(predicted, dtype=float)
    if len(residual) == 0 or not np.isfinite(residual).all():
        raise ValueError("Metrics need nonempty, finite paired observations.")
    return {"mae": float(np.abs(residual).mean()),
            "rmse": float(np.sqrt(np.square(residual).mean()))}


def evaluate_store(
    data: pd.DataFrame, store_id: str, holdout_days: int = 56,
    min_train_rows: int = 90,
) -> dict:
    """Issue independent seven-day forecasts across the final holdout period.

    At each issue date fit only on observed earlier days, then predict the whole
    following week at once. Actual sales from that week become available only
    at the NEXT issue date. Both methods are scored on exactly the same dates.
    """
    if holdout_days < 7 or holdout_days % 7:
        raise ValueError("holdout_days must be a positive multiple of seven (at least 7).")
    store = data.loc[data["store"] == store_id].copy()
    if store.empty:
        raise ValueError(f"Unknown store: {store_id}")
    if not store["sales"].notna().any():
        raise ValueError(f"Store {store_id} has no observed sales to evaluate.")
    features = make_features(store)
    last_day = store.loc[store["sales"].notna(), "date"].max()
    first_test = last_day - pd.Timedelta(days=holdout_days - 1)
    usable = features["actual"].notna() & features["lag_7"].notna()
    first_training = features.loc[usable & (features.index < first_test)]
    evaluation = {
        "eligible": False, "status": "Insufficient history", "reason": "",
        "test_start": first_test.strftime("%Y-%m-%d"),
        "test_end": last_day.strftime("%Y-%m-%d"),
        "n_predictions": 0, "baseline_mae": None, "ml_mae": None,
        "baseline_rmse": None, "ml_rmse": None, "improvement_pct": None,
        "issue_count": 0,
    }
    empty = pd.DataFrame(columns=["date", "origin", "horizon", "actual", "baseline", "ml"])
    if len(first_training) < min_train_rows:
        evaluation["reason"] = (
            f"Needs {min_train_rows} usable training observations before the {holdout_days}-day "
            f"check; this store has {len(first_training)}. Explore its sales instead."
        )
        return {"evaluation": evaluation, "predictions": empty}
    batches = []
    for start in pd.date_range(first_test, last_day, freq="7D"):
        origin = start - pd.Timedelta(days=1)
        end = min(start + pd.Timedelta(days=6), last_day)
        training = features.loc[usable & (features.index <= origin)]
        testing = features.loc[usable & (features.index >= start) & (features.index <= end)]
        if testing.empty:
            continue
        model = new_model()
        model.fit(training[FEATURES], training["actual"])
        batch = pd.DataFrame(index=testing.index)
        batch["date"] = testing.index
        batch["origin"] = origin
        batch["horizon"] = (testing.index - origin).days
        batch["actual"] = testing["actual"]
        batch["baseline"] = testing["lag_7"]
        batch["ml"] = model.predict(testing[FEATURES])
        batches.append(batch.reset_index(drop=True))
    if not batches:
        evaluation["reason"] = "No dates have both an actual sale and a seven-day lag."
        return {"evaluation": evaluation, "predictions": empty}
    predictions = pd.concat(batches, ignore_index=True)
    baseline = error_scores(predictions["actual"], predictions["baseline"])
    ml = error_scores(predictions["actual"], predictions["ml"])
    improvement = (100 * (1 - ml["mae"] / baseline["mae"])) if baseline["mae"] > 0 else None
    evaluation.update({
        "eligible": True, "status": "Historical check complete", "reason": "",
        "n_predictions": len(predictions), "baseline_mae": baseline["mae"],
        "ml_mae": ml["mae"], "baseline_rmse": baseline["rmse"], "ml_rmse": ml["rmse"],
        "improvement_pct": improvement, "issue_count": predictions["origin"].nunique(),
    })
    return {"evaluation": evaluation, "predictions": predictions}


def _number(value):
    return None if pd.isna(value) else float(value)


def build_payload(data: pd.DataFrame, holdout_days: int = 56) -> dict:
    """Build JSON-safe chart data and a transparent experiment summary."""
    stores = []
    all_predictions = []
    for store_id in sorted(data["store"].unique()):
        selected = data.loc[data["store"] == store_id].copy()
        result = evaluate_store(data, store_id, holdout_days=holdout_days)
        predictions = result["predictions"]
        if not predictions.empty:
            all_predictions.append(predictions.assign(store=store_id))
        start, end = selected["date"].min(), selected["date"].max()
        weekday_series = selected.groupby(selected["date"].dt.dayofweek)["sales"]
        means, counts = weekday_series.mean(), weekday_series.count()
        weekdays = [
            {"weekday": day, "mean": _number(means.get(i, np.nan)), "count": int(counts.get(i, 0))}
            for i, day in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
        ]
        prediction_records = []
        for row in predictions.itertuples(index=False):
            prediction_records.append({
                "date": row.date.strftime("%Y-%m-%d"), "origin": row.origin.strftime("%Y-%m-%d"),
                "horizon": int(row.horizon), "actual": float(row.actual),
                "baseline": float(row.baseline), "ml": float(row.ml),
            })
        stores.append({
            "id": store_id, "label": store_id.replace("store_", "Store "),
            "rows": len(selected), "start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d"),
            "missing_calendar_days": int((end - start).days + 1 - len(selected)),
            "unsold_recorded": int(selected["unsold"].notna().sum()),
            "unsold_coverage_pct": float(100 * selected["unsold"].notna().mean()),
            "history": [{"date": row.date.strftime("%Y-%m-%d"), "sales": _number(row.sales),
                         "unsold": _number(row.unsold)} for row in selected.itertuples(index=False)],
            "weekdays": weekdays, "evaluation": result["evaluation"], "predictions": prediction_records,
        })
    combined = pd.concat(all_predictions, ignore_index=True) if all_predictions else pd.DataFrame()
    overall = {"n_predictions": len(combined), "eligible_stores": len(all_predictions),
               "baseline_mae": None, "ml_mae": None, "improvement_pct": None}
    if len(combined):
        baseline = error_scores(combined["actual"], combined["baseline"])["mae"]
        ml = error_scores(combined["actual"], combined["ml"])["mae"]
        overall.update({"baseline_mae": baseline, "ml_mae": ml,
                        "improvement_pct": 100 * (1 - ml / baseline) if baseline else None})
    return {
        "meta": {
            "title": "Bakery Lab", "data_source_url": SOURCE_URL, "source_commit": SOURCE_COMMIT,
            "sample_start": data["date"].min().strftime("%Y-%m-%d"),
            "sample_end": data["date"].max().strftime("%Y-%m-%d"),
            "records": len(data), "stores_count": data["store"].nunique(),
            "model_name": MODEL_NAME, "holdout_days": holdout_days,
            "evaluation_mode": "Seven-day forecasts, reissued weekly using only earlier observations",
            "unit_label": "Scaled sales",
            "limitations": [
                "Sales, ordered and unsold values are scaled signals, not item counts, money or kilograms. Negative values are valid.",
                "Unsold records are incomplete. Unsold does not mean discarded, so this demo does not measure waste or savings.",
                "Historical sales can be limited by stockouts. Stockout times and true unmet demand are unavailable.",
                "The source scaling process is not documented well enough to audit how it was fitted or recover original quantities.",
                "Calendar and lagged sales features are used. Actual target-week weather, unsold and ordered values are excluded.",
                "This is a historical learning experiment. Its last observation is in 2023; predictions are not current production advice.",
                "One held-out period is an initial check, not evidence of business demand or measured environmental impact.",
            ],
        },
        "overall": overall, "stores": stores,
    }
